"""Эндпоинты модуля управления клиентами (Функции 5–6)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.database import SessionDep
from app.dependencies import ManagerUser, Pagination
from app.schemas.client import ClientCreate, ClientRead, ClientUpdate, ClientWithDevices
from app.schemas.common import COMMON_ERROR_RESPONSES, Page
from app.services import client_service

router = APIRouter(prefix="/clients", tags=["Клиенты"], responses=COMMON_ERROR_RESPONSES)


@router.get(
    "",
    response_model=Page[ClientRead],
    summary="Список клиентов",
    description="Поиск по ФИО, телефону и email. Пагинация — 20 записей по умолчанию.",
)
async def list_clients(
    session: SessionDep,
    _user: ManagerUser,
    pagination: Pagination,
    search: Annotated[str | None, Query(description="ФИО, телефон или email")] = None,
    sort_by: Annotated[Literal["created_at", "full_name"], Query()] = "created_at",
    sort_desc: Annotated[bool, Query(description="Сортировка по убыванию")] = True,
) -> Page[ClientRead]:
    clients, total = await client_service.list_clients(
        session, pagination, search, sort_by, sort_desc
    )
    return Page[ClientRead].create(
        items=[ClientRead.model_validate(c) for c in clients],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.post(
    "",
    response_model=ClientRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создание клиента",
    description="Телефон нормализуется до +7XXXXXXXXXX; дубликаты отклоняются кодом 409.",
)
async def create_client(
    session: SessionDep, user: ManagerUser, data: ClientCreate
) -> ClientRead:
    client = await client_service.create_client(session, data, user)
    return ClientRead.model_validate(client)


@router.get(
    "/{client_id}",
    response_model=ClientWithDevices,
    summary="Карточка клиента",
    description="Возвращает клиента вместе со списком его устройств.",
)
async def get_client(
    session: SessionDep, _user: ManagerUser, client_id: int
) -> ClientWithDevices:
    client = await client_service.get_client_or_404(session, client_id)
    return ClientWithDevices.model_validate(client)


@router.patch("/{client_id}", response_model=ClientRead, summary="Редактирование клиента")
async def update_client(
    session: SessionDep, user: ManagerUser, client_id: int, data: ClientUpdate
) -> ClientRead:
    client = await client_service.update_client(session, client_id, data, user)
    return ClientRead.model_validate(client)
