"""Эндпоинты управления пользователями. Доступны только администратору."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.database import SessionDep
from app.dependencies import AdminUser, Pagination
from app.models.enums import UserRole
from app.schemas.common import COMMON_ERROR_RESPONSES, MessageResponse, Page
from app.schemas.user import MasterWorkload, UserCreate, UserRead, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["Пользователи"], responses=COMMON_ERROR_RESPONSES)


@router.get(
    "",
    response_model=Page[UserRead],
    summary="Список пользователей",
)
async def list_users(
    session: SessionDep,
    _admin: AdminUser,
    pagination: Pagination,
    role: Annotated[UserRole | None, Query(description="Фильтр по роли")] = None,
    is_active: Annotated[bool | None, Query(description="Только активные/неактивные")] = None,
    search: Annotated[str | None, Query(description="Поиск по логину, email, ФИО")] = None,
) -> Page[UserRead]:
    users, total = await user_service.list_users(session, pagination, role, is_active, search)
    return Page[UserRead].create(
        items=[UserRead.model_validate(u) for u in users],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.get(
    "/masters",
    response_model=list[MasterWorkload],
    summary="Мастера и их загруженность",
    description="Используется при назначении мастера на заявку (Функция 9).",
)
async def list_masters(session: SessionDep, _admin: AdminUser) -> list[MasterWorkload]:
    rows = await user_service.list_masters_with_workload(session)
    return [MasterWorkload.model_validate(row) for row in rows]


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создание пользователя",
)
async def create_user(session: SessionDep, admin: AdminUser, data: UserCreate) -> UserRead:
    user = await user_service.create_user(session, data, admin)
    return UserRead.model_validate(user)


@router.get("/{user_id}", response_model=UserRead, summary="Просмотр пользователя")
async def get_user(session: SessionDep, _admin: AdminUser, user_id: int) -> UserRead:
    user = await user_service.get_user_or_404(session, user_id)
    return UserRead.model_validate(user)


@router.patch("/{user_id}", response_model=UserRead, summary="Редактирование пользователя")
async def update_user(
    session: SessionDep, admin: AdminUser, user_id: int, data: UserUpdate
) -> UserRead:
    user = await user_service.update_user(session, user_id, data, admin)
    return UserRead.model_validate(user)


@router.delete(
    "/{user_id}",
    response_model=MessageResponse,
    summary="Деактивация пользователя",
    description=(
        "Физическое удаление не выполняется: учётная запись деактивируется, "
        "чтобы сохранить авторство заявок и записей журнала."
    ),
)
async def deactivate_user(
    session: SessionDep, admin: AdminUser, user_id: int
) -> MessageResponse:
    await user_service.deactivate_user(session, user_id, admin)
    return MessageResponse(message="Пользователь деактивирован")
