"""Бизнес-логика аутентификации и управления токенами (Функции 1–3)."""

import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging_config import log_action
from app.core.security import (
    JWTError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.enums import UserRole
from app.models.token import RefreshToken
from app.models.user import User
from app.schemas.auth import TokenPair
from app.schemas.user import UserRead, UserRegister
from app.services.exceptions import AuthenticationError, ConflictError, PermissionDeniedError

settings = get_settings()
logger = logging.getLogger(__name__)


async def _ensure_unique_credentials(
    session: AsyncSession, username: str, email: str, exclude_user_id: int | None = None
) -> None:
    """Проверяет уникальность логина и email (Функция 1)."""
    stmt = select(User).where(or_(User.username == username, User.email == email))
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    existing = (await session.execute(stmt)).scalars().first()
    if existing is None:
        return
    if existing.username == username:
        raise ConflictError("Пользователь с таким логином уже существует")
    raise ConflictError("Пользователь с таким email уже существует")


async def register_user(session: AsyncSession, data: UserRegister) -> User:
    """Самостоятельная регистрация пользователя.

    Роль всегда «менеджер»: создание сотрудников с произвольными ролями —
    прерогатива администратора (POST /api/v1/users).
    """
    if not settings.ALLOW_SELF_REGISTRATION:
        raise PermissionDeniedError(
            "Самостоятельная регистрация отключена. Обратитесь к администратору."
        )

    await _ensure_unique_credentials(session, data.username, data.email)

    user = User(
        username=data.username,
        email=data.email,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        role=UserRole.MANAGER,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    log_action("user.registered", user_id=user.id, username=user.username, role=user.role.value)
    return user


async def authenticate_user(session: AsyncSession, username: str, password: str) -> User:
    """Проверяет пару логин/пароль (Функция 2)."""
    normalized = username.strip().lower()
    stmt = select(User).where(
        or_(User.username == normalized, User.email == username.strip())
    )
    user = (await session.execute(stmt)).scalars().first()

    # Сообщение об ошибке одинаково для несуществующего пользователя и неверного
    # пароля — иначе по ответу можно перебирать существующие логины.
    if user is None or not verify_password(password, user.password_hash):
        logger.warning("Неудачная попытка входа", extra={"username": normalized})
        raise AuthenticationError("Неверный логин или пароль")

    if not user.is_active:
        raise AuthenticationError("Учётная запись деактивирована")

    return user


async def issue_token_pair(
    session: AsyncSession,
    user: User,
    user_agent: str | None = None,
    ip_address: str | None = None,
    include_user: bool = True,
) -> TokenPair:
    """Выпускает пару access/refresh и сохраняет refresh в БД."""
    access_token, access_expires = create_access_token(user.id, user.role.value)
    refresh_token, jti, refresh_expires = create_refresh_token(user.id)

    session.add(
        RefreshToken(
            jti=jti,
            user_id=user.id,
            expires_at=refresh_expires,
            user_agent=(user_agent or "")[:255] or None,
            ip_address=(ip_address or "")[:64] or None,
        )
    )
    await session.commit()

    log_action("auth.login", user_id=user.id, username=user.username, ip=ip_address)
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=access_expires,
        user=UserRead.model_validate(user) if include_user else None,
    )


async def _load_valid_refresh_token(session: AsyncSession, token: str) -> RefreshToken:
    """Декодирует refresh-токен и находит его активную запись в БД."""
    try:
        payload = decode_token(token)
    except JWTError:
        raise AuthenticationError("Недействительный refresh-токен") from None

    if payload.get("type") != "refresh":
        raise AuthenticationError("Передан токен неверного типа")

    jti = payload.get("jti")
    stored = (
        await session.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    ).scalars().first()

    if stored is None:
        raise AuthenticationError("Токен не найден или уже отозван")
    if stored.revoked_at is not None:
        raise AuthenticationError("Токен отозван")
    if stored.expires_at <= datetime.now(tz=timezone.utc):
        raise AuthenticationError("Срок действия токена истёк")
    return stored


async def refresh_token_pair(
    session: AsyncSession,
    refresh_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenPair:
    """Обновляет пару токенов с ротацией refresh-токена.

    Старый refresh отзывается: повторное использование украденного токена
    станет невозможным.
    """
    stored = await _load_valid_refresh_token(session, refresh_token)

    user = await session.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Пользователь не найден или деактивирован")

    stored.revoked_at = datetime.now(tz=timezone.utc)
    await session.flush()

    log_action("auth.token_refreshed", user_id=user.id)
    return await issue_token_pair(
        session, user, user_agent=user_agent, ip_address=ip_address, include_user=False
    )


async def logout(
    session: AsyncSession, refresh_token: str, user: User, all_devices: bool = False
) -> None:
    """Инвалидирует refresh-токен(ы) пользователя (Функция 3)."""
    now = datetime.now(tz=timezone.utc)

    if all_devices:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
    else:
        stored = await _load_valid_refresh_token(session, refresh_token)
        if stored.user_id != user.id:
            raise PermissionDeniedError("Токен принадлежит другому пользователю")
        stored.revoked_at = now

    await session.commit()
    log_action("auth.logout", user_id=user.id, all_devices=all_devices)


async def purge_expired_tokens(session: AsyncSession) -> int:
    """Удаляет просроченные refresh-токены (вызывается по расписанию)."""
    from sqlalchemy import delete

    result = await session.execute(
        delete(RefreshToken).where(RefreshToken.expires_at <= datetime.now(tz=timezone.utc))
    )
    await session.commit()
    return result.rowcount or 0
