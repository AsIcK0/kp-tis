"""Эндпоинты модуля управления заявками (Функции 7–12)."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Query, status

from app.core.status_flow import allowed_targets
from app.database import SessionDep
from app.dependencies import ManagerUser, Pagination, RequestUser
from app.models.enums import REQUEST_STATUS_LABELS, RequestPriority, RequestStatus
from app.schemas.common import COMMON_ERROR_RESPONSES, Page
from app.schemas.request import (
    AssignMasterRequest,
    HistoryRead,
    RequestCreate,
    RequestListItem,
    RequestRead,
    RequestUpdate,
    StatusChangeRequest,
)
from app.schemas.spare_part import SparePartUsageRead
from app.services import request_service, spare_part_service

router = APIRouter(prefix="/requests", tags=["Заявки"], responses=COMMON_ERROR_RESPONSES)


@router.get(
    "",
    response_model=Page[RequestListItem],
    summary="Список заявок",
    description=(
        "Фильтры: статус, приоритет, мастер, клиент, диапазон дат создания. "
        "Поиск — по номеру заявки и описанию неисправности. "
        "Мастер видит только назначенные на него заявки."
    ),
)
async def list_requests(
    session: SessionDep,
    user: RequestUser,
    pagination: Pagination,
    status_filter: Annotated[RequestStatus | None, Query(alias="status")] = None,
    priority: Annotated[RequestPriority | None, Query()] = None,
    master_id: Annotated[int | None, Query()] = None,
    client_id: Annotated[int | None, Query()] = None,
    date_from: Annotated[date | None, Query(description="Дата создания, с")] = None,
    date_to: Annotated[date | None, Query(description="Дата создания, по")] = None,
    search: Annotated[str | None, Query(description="Номер заявки или описание")] = None,
    sort_by: Annotated[
        Literal["created_at", "deadline", "priority", "status", "number"], Query()
    ] = "created_at",
    sort_desc: Annotated[bool, Query()] = True,
) -> Page[RequestListItem]:
    requests, total = await request_service.list_requests(
        session,
        user,
        pagination,
        status=status_filter,
        priority=priority,
        master_id=master_id,
        client_id=client_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )
    return Page[RequestListItem].create(
        items=[RequestListItem.model_validate(r) for r in requests],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.post(
    "",
    response_model=RequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создание заявки",
    description=(
        "Номер заявки генерируется автоматически в формате SC-YYYY-NNNN, "
        "начальный статус — «Принята». Заявка привязывается к создавшему менеджеру."
    ),
)
async def create_request(
    session: SessionDep, user: ManagerUser, data: RequestCreate
) -> RequestRead:
    request = await request_service.create_request(session, data, user)
    return RequestRead.model_validate(request)


@router.get("/{request_id}", response_model=RequestRead, summary="Просмотр заявки")
async def get_request(
    session: SessionDep, user: RequestUser, request_id: int
) -> RequestRead:
    request = await request_service.get_request_for_user(session, request_id, user)
    return RequestRead.model_validate(request)


@router.patch(
    "/{request_id}",
    response_model=RequestRead,
    summary="Редактирование заявки",
    description=(
        "Менеджер и администратор изменяют описание, приоритет, срок и стоимость работ. "
        "Мастер — только поля, связанные с выполнением работ (диагностика, описание работ, "
        "стоимость)."
    ),
)
async def update_request(
    session: SessionDep, user: RequestUser, request_id: int, data: RequestUpdate
) -> RequestRead:
    request = await request_service.update_request(session, request_id, data, user)
    return RequestRead.model_validate(request)


@router.post(
    "/{request_id}/assign",
    response_model=RequestRead,
    summary="Назначение мастера",
    description="Проверяет роль исполнителя и его загруженность, уведомляет мастера.",
)
async def assign_master(
    session: SessionDep, user: ManagerUser, request_id: int, data: AssignMasterRequest
) -> RequestRead:
    request = await request_service.assign_master(session, request_id, data, user)
    return RequestRead.model_validate(request)


@router.post(
    "/{request_id}/status",
    response_model=RequestRead,
    summary="Смена статуса заявки",
    description=(
        "Переход проверяется по словарю допустимых переходов. "
        "При переводе в «Готова к выдаче» и «Отменена» уведомляется клиент."
    ),
)
async def change_status(
    session: SessionDep, user: RequestUser, request_id: int, data: StatusChangeRequest
) -> RequestRead:
    request = await request_service.change_status(session, request_id, data, user)
    return RequestRead.model_validate(request)


@router.get(
    "/{request_id}/allowed-statuses",
    response_model=list[dict],
    summary="Доступные статусы",
    description="Список статусов, в которые можно перевести заявку из текущего.",
)
async def get_allowed_statuses(
    session: SessionDep, user: RequestUser, request_id: int
) -> list[dict]:
    request = await request_service.get_request_for_user(session, request_id, user)
    return [
        {"value": target.value, "label": REQUEST_STATUS_LABELS[target]}
        for target in sorted(allowed_targets(request.status), key=lambda s: s.value)
    ]


@router.get(
    "/{request_id}/history",
    response_model=list[HistoryRead],
    summary="История изменений заявки",
    description="Хронологический список событий: создание, смена статуса, назначение, комментарии.",
)
async def get_history(
    session: SessionDep, user: RequestUser, request_id: int
) -> list[HistoryRead]:
    entries = await request_service.get_history(session, request_id, user)
    return [HistoryRead.model_validate(entry) for entry in entries]


@router.post(
    "/{request_id}/comments",
    response_model=HistoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавление комментария",
)
async def add_comment(
    session: SessionDep,
    user: RequestUser,
    request_id: int,
    comment: Annotated[str, Body(embed=True, min_length=1)],
) -> HistoryRead:
    entry = await request_service.add_comment(session, request_id, comment, user)
    return HistoryRead.model_validate(entry)


@router.get(
    "/{request_id}/spare-parts",
    response_model=list[SparePartUsageRead],
    summary="Запчасти, списанные на заявку",
)
async def list_request_spare_parts(
    session: SessionDep, user: RequestUser, request_id: int
) -> list[SparePartUsageRead]:
    await request_service.get_request_for_user(session, request_id, user)
    usages = await spare_part_service.list_usages_for_request(session, request_id)
    return [SparePartUsageRead.model_validate(u) for u in usages]
