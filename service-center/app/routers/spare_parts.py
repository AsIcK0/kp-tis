"""Эндпоинты модуля управления складом (Функции 13–14)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.database import SessionDep
from app.dependencies import Pagination, StaffUser, WarehouseUser
from app.schemas.common import COMMON_ERROR_RESPONSES, MessageResponse, Page
from app.schemas.spare_part import (
    SparePartCreate,
    SparePartRead,
    SparePartUpdate,
    SparePartUsageRead,
    WriteOffRequest,
)
from app.services import spare_part_service

router = APIRouter(prefix="/spare-parts", tags=["Склад"], responses=COMMON_ERROR_RESPONSES)


@router.get(
    "",
    response_model=Page[SparePartRead],
    summary="Список запчастей",
    description=(
        "Доступен всем сотрудникам: мастеру нужно видеть наличие. "
        "Изменять номенклатуру могут только кладовщик и администратор."
    ),
)
async def list_spare_parts(
    session: SessionDep,
    _user: StaffUser,
    pagination: Pagination,
    search: Annotated[str | None, Query(description="Название или артикул")] = None,
    low_stock_only: Annotated[
        bool, Query(description="Только позиции с остатком ниже минимального")
    ] = False,
    sort_by: Annotated[
        Literal["name", "article", "quantity", "price", "created_at"], Query()
    ] = "name",
    sort_desc: Annotated[bool, Query()] = False,
) -> Page[SparePartRead]:
    parts, total = await spare_part_service.list_spare_parts(
        session, pagination, search, low_stock_only, sort_by, sort_desc
    )
    return Page[SparePartRead].create(
        items=[SparePartRead.model_validate(p) for p in parts],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.post(
    "",
    response_model=SparePartRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавление позиции номенклатуры",
)
async def create_spare_part(
    session: SessionDep, user: WarehouseUser, data: SparePartCreate
) -> SparePartRead:
    part = await spare_part_service.create_spare_part(session, data, user)
    return SparePartRead.model_validate(part)


@router.get("/{part_id}", response_model=SparePartRead, summary="Просмотр позиции")
async def get_spare_part(
    session: SessionDep, _user: StaffUser, part_id: int
) -> SparePartRead:
    part = await spare_part_service.get_part_or_404(session, part_id)
    return SparePartRead.model_validate(part)


@router.patch(
    "/{part_id}",
    response_model=SparePartRead,
    summary="Редактирование позиции",
    description="Здесь же оформляется приход товара — увеличением поля quantity.",
)
async def update_spare_part(
    session: SessionDep, user: WarehouseUser, part_id: int, data: SparePartUpdate
) -> SparePartRead:
    part = await spare_part_service.update_spare_part(session, part_id, data, user)
    return SparePartRead.model_validate(part)


@router.delete(
    "/{part_id}",
    response_model=MessageResponse,
    summary="Удаление позиции",
    description="Позицию с историей списаний удалить нельзя (вернётся 409).",
)
async def delete_spare_part(
    session: SessionDep, user: WarehouseUser, part_id: int
) -> MessageResponse:
    await spare_part_service.delete_spare_part(session, part_id, user)
    return MessageResponse(message="Позиция удалена")


@router.post(
    "/{part_id}/write-off",
    response_model=SparePartUsageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Списание запчасти на заявку",
    description=(
        "Проверяет достаточность остатка и статус заявки: списание на выданную "
        "или отменённую заявку запрещено. Мастер списывает только на свои заявки."
    ),
)
async def write_off(
    session: SessionDep, user: StaffUser, part_id: int, data: WriteOffRequest
) -> SparePartUsageRead:
    usage = await spare_part_service.write_off(session, part_id, data, user)
    return SparePartUsageRead.model_validate(usage)
