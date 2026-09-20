"""Бизнес-логика управления пользователями (доступно только администратору)."""

import logging

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging_config import log_action
from app.core.security import hash_password
from app.core.status_flow import ACTIVE_STATUSES
from app.dependencies import PaginationParams
from app.models.enums import UserRole
from app.models.request import Request
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.auth_service import _ensure_unique_credentials
from app.services.exceptions import BusinessRuleError, NotFoundError

settings = get_settings()
logger = logging.getLogger(__name__)


async def get_user_or_404(session: AsyncSession, user_id: int) -> User:
    """Возвращает пользователя или выбрасывает NotFoundError."""
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден")
    return user


async def list_users(
    session: AsyncSession,
    pagination: PaginationParams,
    role: UserRole | None = None,
    is_active: bool | None = None,
    search: str | None = None,
) -> tuple[list[User], int]:
    """Список пользователей с фильтрами и пагинацией."""
    stmt = select(User)
    if role is not None:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                User.username.ilike(pattern),
                User.email.ilike(pattern),
                User.full_name.ilike(pattern),
            )
        )

    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(User.created_at.desc()).offset(pagination.offset).limit(pagination.limit)
    users = list((await session.execute(stmt)).scalars().all())
    return users, total


async def create_user(session: AsyncSession, data: UserCreate, actor: User) -> User:
    """Создаёт пользователя с произвольной ролью (только администратор)."""
    await _ensure_unique_credentials(session, data.username, data.email)

    user = User(
        username=data.username,
        email=data.email,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        role=data.role,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    log_action(
        "user.created",
        user_id=actor.id,
        target_user_id=user.id,
        username=user.username,
        role=user.role.value,
    )
    return user


async def update_user(
    session: AsyncSession, user_id: int, data: UserUpdate, actor: User
) -> User:
    """Редактирует пользователя."""
    user = await get_user_or_404(session, user_id)
    payload = data.model_dump(exclude_unset=True)

    # Администратор не должен случайно лишить себя прав или заблокировать себя.
    if user.id == actor.id:
        if payload.get("role") not in (None, UserRole.ADMIN):
            raise BusinessRuleError("Нельзя изменить собственную роль")
        if payload.get("is_active") is False:
            raise BusinessRuleError("Нельзя деактивировать собственную учётную запись")

    new_email = payload.get("email")
    if new_email and new_email != user.email:
        await _ensure_unique_credentials(
            session, user.username, new_email, exclude_user_id=user.id
        )

    if "password" in payload and payload["password"]:
        user.password_hash = hash_password(payload.pop("password"))
    payload.pop("password", None)

    for field, value in payload.items():
        setattr(user, field, value)

    await session.commit()
    await session.refresh(user)

    log_action(
        "user.updated",
        user_id=actor.id,
        target_user_id=user.id,
        fields=sorted(payload.keys()),
    )
    return user


async def deactivate_user(session: AsyncSession, user_id: int, actor: User) -> None:
    """Деактивирует пользователя.

    Физическое удаление не выполняется: на пользователя ссылаются заявки
    и записи истории, их авторство должно сохраниться.
    """
    user = await get_user_or_404(session, user_id)
    if user.id == actor.id:
        raise BusinessRuleError("Нельзя деактивировать собственную учётную запись")

    if user.role == UserRole.MASTER:
        active = await count_active_requests(session, user.id)
        if active:
            raise BusinessRuleError(
                f"У мастера есть незакрытые заявки ({active}). "
                "Переназначьте их перед деактивацией."
            )

    user.is_active = False
    await session.commit()
    log_action("user.deactivated", user_id=actor.id, target_user_id=user.id)


async def count_active_requests(session: AsyncSession, master_id: int) -> int:
    """Считает активные (незакрытые) заявки мастера — для Функции 9."""
    stmt = select(func.count(Request.id)).where(
        Request.master_id == master_id,
        Request.status.in_(ACTIVE_STATUSES),
    )
    return await session.scalar(stmt) or 0


async def list_masters_with_workload(session: AsyncSession) -> list[dict]:
    """Возвращает мастеров и их текущую загруженность."""
    stmt = (
        select(User, func.count(Request.id).label("active_requests"))
        .outerjoin(
            Request,
            (Request.master_id == User.id) & (Request.status.in_(ACTIVE_STATUSES)),
        )
        .where(User.role == UserRole.MASTER, User.is_active.is_(True))
        .group_by(User.id)
        .order_by(func.count(Request.id).asc(), User.username.asc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "active_requests": active,
            "limit": settings.MAX_ACTIVE_REQUESTS_PER_MASTER,
        }
        for user, active in rows
    ]


async def ensure_first_admin(session: AsyncSession) -> None:
    """Создаёт учётную запись администратора при первом запуске системы."""
    exists = await session.scalar(
        select(func.count(User.id)).where(User.role == UserRole.ADMIN)
    )
    if exists:
        return

    admin = User(
        username=settings.FIRST_ADMIN_USERNAME,
        email=settings.FIRST_ADMIN_EMAIL,
        full_name="Администратор системы",
        password_hash=hash_password(settings.FIRST_ADMIN_PASSWORD),
        role=UserRole.ADMIN,
        is_active=True,
    )
    session.add(admin)
    await session.commit()
    logger.warning(
        "Создан первый администратор «%s». Смените пароль сразу после входа!",
        settings.FIRST_ADMIN_USERNAME,
    )
