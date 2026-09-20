"""Бизнес-логика модуля клиентов (Функции 5–6)."""

import logging

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import log_action
from app.dependencies import PaginationParams
from app.models.client import Client
from app.models.user import User
from app.schemas.client import ClientCreate, ClientUpdate
from app.services.exceptions import ConflictError, NotFoundError

logger = logging.getLogger(__name__)

#: Поля, по которым разрешена сортировка списка клиентов (Функция 6).
SORTABLE_FIELDS = {
    "created_at": Client.created_at,
    "full_name": Client.full_name,
}


async def get_client_or_404(session: AsyncSession, client_id: int) -> Client:
    """Возвращает клиента или выбрасывает NotFoundError."""
    client = await session.get(Client, client_id)
    if client is None:
        raise NotFoundError("Клиент не найден")
    return client


async def create_client(session: AsyncSession, data: ClientCreate, actor: User) -> Client:
    """Создаёт клиента с проверкой дублирования по телефону."""
    duplicate = await session.scalar(select(Client).where(Client.phone == data.phone))
    if duplicate is not None:
        raise ConflictError(
            f"Клиент с телефоном {data.phone} уже зарегистрирован (id={duplicate.id})"
        )

    client = Client(**data.model_dump())
    session.add(client)
    await session.commit()
    await session.refresh(client)

    log_action("client.created", user_id=actor.id, client_id=client.id, phone=client.phone)
    return client


async def update_client(
    session: AsyncSession, client_id: int, data: ClientUpdate, actor: User
) -> Client:
    """Частично обновляет карточку клиента."""
    client = await get_client_or_404(session, client_id)
    payload = data.model_dump(exclude_unset=True)

    new_phone = payload.get("phone")
    if new_phone and new_phone != client.phone:
        duplicate = await session.scalar(
            select(Client).where(Client.phone == new_phone, Client.id != client.id)
        )
        if duplicate is not None:
            raise ConflictError(f"Телефон {new_phone} уже занят клиентом id={duplicate.id}")

    for field, value in payload.items():
        setattr(client, field, value)

    await session.commit()
    await session.refresh(client)

    log_action(
        "client.updated",
        user_id=actor.id,
        client_id=client.id,
        fields=sorted(payload.keys()),
    )
    return client


async def list_clients(
    session: AsyncSession,
    pagination: PaginationParams,
    search: str | None = None,
    sort_by: str = "created_at",
    sort_desc: bool = True,
) -> tuple[list[Client], int]:
    """Список клиентов с поиском по ФИО, телефону и email."""
    stmt = select(Client)

    if search:
        term = search.strip()
        # Для поиска по телефону оставляем только цифры: пользователь может
        # ввести номер в любом формате.
        digits = "".join(ch for ch in term if ch.isdigit())
        conditions = [
            Client.full_name.ilike(f"%{term}%"),
            Client.email.ilike(f"%{term}%"),
        ]
        if digits:
            conditions.append(Client.phone.ilike(f"%{digits}%"))
        stmt = stmt.where(or_(*conditions))

    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    column = SORTABLE_FIELDS.get(sort_by, Client.created_at)
    stmt = stmt.order_by(column.desc() if sort_desc else column.asc())
    stmt = stmt.offset(pagination.offset).limit(pagination.limit)

    clients = list((await session.execute(stmt)).scalars().unique().all())
    return clients, total
