"""Бизнес-логика модуля склада (Функции 13–14)."""

import logging

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging_config import log_action
from app.core.status_flow import FINAL_STATUSES
from app.dependencies import PaginationParams
from app.models.enums import REQUEST_STATUS_LABELS, HistoryEventType, UserRole
from app.models.request import Request, StatusHistory
from app.models.spare_part import SparePart, SparePartUsage
from app.models.user import User
from app.schemas.spare_part import SparePartCreate, SparePartUpdate, WriteOffRequest
from app.services import notification_service
from app.services.exceptions import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)

logger = logging.getLogger(__name__)

SORTABLE_FIELDS = {
    "name": SparePart.name,
    "article": SparePart.article,
    "quantity": SparePart.quantity,
    "price": SparePart.price,
    "created_at": SparePart.created_at,
}


async def get_part_or_404(session: AsyncSession, part_id: int) -> SparePart:
    """Возвращает позицию номенклатуры или выбрасывает NotFoundError."""
    part = await session.get(SparePart, part_id)
    if part is None:
        raise NotFoundError("Запчасть не найдена")
    return part


async def list_spare_parts(
    session: AsyncSession,
    pagination: PaginationParams,
    search: str | None = None,
    low_stock_only: bool = False,
    sort_by: str = "name",
    sort_desc: bool = False,
) -> tuple[list[SparePart], int]:
    """Список номенклатуры с поиском по названию и артикулу."""
    stmt = select(SparePart)

    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(or_(SparePart.name.ilike(term), SparePart.article.ilike(term)))
    if low_stock_only:
        stmt = stmt.where(SparePart.quantity <= SparePart.min_quantity)

    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    column = SORTABLE_FIELDS.get(sort_by, SparePart.name)
    stmt = stmt.order_by(column.desc() if sort_desc else column.asc())
    stmt = stmt.offset(pagination.offset).limit(pagination.limit)

    return list((await session.execute(stmt)).scalars().all()), total


async def create_spare_part(
    session: AsyncSession, data: SparePartCreate, actor: User
) -> SparePart:
    """Создаёт позицию номенклатуры с проверкой уникальности артикула."""
    duplicate = await session.scalar(
        select(SparePart).where(SparePart.article == data.article)
    )
    if duplicate is not None:
        raise ConflictError(f"Запчасть с артикулом {data.article} уже существует")

    part = SparePart(**data.model_dump())
    session.add(part)
    await session.commit()
    await session.refresh(part)

    log_action("spare_part.created", user_id=actor.id, spare_part_id=part.id, article=part.article)
    if part.is_low_stock:
        notification_service.notify_low_stock(part)
    return part


async def update_spare_part(
    session: AsyncSession, part_id: int, data: SparePartUpdate, actor: User
) -> SparePart:
    """Редактирует позицию номенклатуры (в т.ч. приход товара)."""
    part = await get_part_or_404(session, part_id)
    payload = data.model_dump(exclude_unset=True)

    new_article = payload.get("article")
    if new_article and new_article != part.article:
        duplicate = await session.scalar(
            select(SparePart).where(
                SparePart.article == new_article, SparePart.id != part.id
            )
        )
        if duplicate is not None:
            raise ConflictError(f"Артикул {new_article} уже занят")

    for field, value in payload.items():
        setattr(part, field, value)

    await session.commit()
    await session.refresh(part)

    log_action(
        "spare_part.updated",
        user_id=actor.id,
        spare_part_id=part.id,
        fields=sorted(payload.keys()),
    )
    if part.is_low_stock:
        notification_service.notify_low_stock(part)
    return part


async def delete_spare_part(session: AsyncSession, part_id: int, actor: User) -> None:
    """Удаляет позицию номенклатуры, если по ней не было списаний."""
    part = await get_part_or_404(session, part_id)
    used = await session.scalar(
        select(func.count(SparePartUsage.id)).where(SparePartUsage.spare_part_id == part.id)
    )
    if used:
        raise ConflictError(
            "Запчасть использовалась в заявках и не может быть удалена. "
            "Обнулите остаток вместо удаления."
        )
    await session.delete(part)
    await session.commit()
    log_action("spare_part.deleted", user_id=actor.id, spare_part_id=part_id)


async def write_off(
    session: AsyncSession, part_id: int, data: WriteOffRequest, actor: User
) -> SparePartUsage:
    """Списывает запчасть на заявку (Функция 14).

    Проверяется достаточность остатка и статус заявки: списание на выданную
    или отменённую заявку запрещено.
    """
    request = await session.get(Request, data.request_id)
    if request is None:
        raise NotFoundError("Заявка не найдена")

    # Мастер списывает запчасти только на свои заявки.
    if actor.role == UserRole.MASTER and request.master_id != actor.id:
        raise PermissionDeniedError("Заявка не назначена на вас")

    if request.status in FINAL_STATUSES:
        raise BusinessRuleError(
            f"Списание на заявку в статусе «{REQUEST_STATUS_LABELS[request.status]}» запрещено"
        )

    # SELECT ... FOR UPDATE: блокируем строку остатка на время транзакции,
    # чтобы два одновременных списания не ушли «в минус».
    part = await session.scalar(
        select(SparePart).where(SparePart.id == part_id).with_for_update()
    )
    if part is None:
        raise NotFoundError("Запчасть не найдена")

    if part.quantity < data.quantity:
        raise BusinessRuleError(
            f"Недостаточно остатка: доступно {part.quantity}, запрошено {data.quantity}"
        )

    part.quantity -= data.quantity
    usage = SparePartUsage(
        request_id=request.id,
        spare_part_id=part.id,
        quantity=data.quantity,
        price_at_use=part.price,
        used_by=actor.id,
    )
    session.add(usage)

    # Списание отражается в ленте событий заявки.
    session.add(
        StatusHistory(
            request_id=request.id,
            event_type=HistoryEventType.COMMENT,
            changed_by=actor.id,
            comment=(
                data.comment
                or f"Списана запчасть «{part.name}» ({part.article}) × {data.quantity}"
            ),
        )
    )

    await session.commit()

    usage = (
        await session.execute(
            select(SparePartUsage)
            .where(SparePartUsage.id == usage.id)
            .options(selectinload(SparePartUsage.author), selectinload(SparePartUsage.spare_part))
        )
    ).scalars().one()

    log_action(
        "spare_part.written_off",
        user_id=actor.id,
        spare_part_id=part.id,
        request_id=request.id,
        quantity=data.quantity,
        remaining=part.quantity,
    )
    if part.is_low_stock:
        notification_service.notify_low_stock(part)
    return usage


async def list_usages_for_request(
    session: AsyncSession, request_id: int
) -> list[SparePartUsage]:
    """Возвращает список запчастей, списанных на заявку."""
    stmt = (
        select(SparePartUsage)
        .where(SparePartUsage.request_id == request_id)
        .options(selectinload(SparePartUsage.author), selectinload(SparePartUsage.spare_part))
        .order_by(SparePartUsage.used_at.asc())
    )
    return list((await session.execute(stmt)).scalars().all())
