"""Бизнес-логика модуля заявок (Функции 7–12)."""

import logging
from datetime import date, datetime, timezone

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.logging_config import log_action
from app.core.status_flow import (
    CLIENT_NOTIFICATION_STATUSES,
    FINAL_STATUSES,
    allowed_targets,
    can_role_set_status,
    is_transition_allowed,
)
from app.dependencies import PaginationParams
from app.models.client import Device
from app.models.enums import (
    REQUEST_STATUS_LABELS,
    HistoryEventType,
    RequestPriority,
    RequestStatus,
    UserRole,
)
from app.models.request import Request, StatusHistory
from app.models.user import User
from app.schemas.request import AssignMasterRequest, RequestCreate, RequestUpdate, StatusChangeRequest
from app.services import notification_service
from app.services.client_service import get_client_or_404
from app.services.exceptions import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from app.services.user_service import count_active_requests

settings = get_settings()
logger = logging.getLogger(__name__)

#: Поля, доступные менеджеру и администратору (Функция 8).
MANAGER_EDITABLE_FIELDS = frozenset({"problem_description", "priority", "deadline", "work_cost"})
#: Поля, доступные мастеру, — только связанные с выполнением работ.
MASTER_EDITABLE_FIELDS = frozenset({"diagnosis", "work_description", "work_cost"})

#: Сопоставление имён из схемы с именами колонок модели.
FIELD_TO_COLUMN = {"problem_description": "description"}

#: Поля, по которым разрешена сортировка списка заявок.
SORTABLE_FIELDS = {
    "created_at": Request.created_at,
    "deadline": Request.deadline,
    "priority": Request.priority,
    "status": Request.status,
    "number": Request.number,
}


# --------------------------------------------------------------------------
# Вспомогательные функции
# --------------------------------------------------------------------------
async def generate_request_number(session: AsyncSession) -> str:
    """Генерирует номер заявки формата SC-YYYY-NNNN (Функция 7).

    Нумерация сквозная в пределах календарного года. Гонки при одновременном
    создании заявок отсекаются уникальным индексом на колонке ``number``:
    вызывающий код повторяет попытку.
    """
    year = datetime.now(tz=timezone.utc).year
    prefix = f"SC-{year}-"
    last_number = await session.scalar(
        select(func.max(Request.number)).where(Request.number.like(f"{prefix}%"))
    )
    next_seq = 1
    if last_number:
        try:
            next_seq = int(last_number.rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):  # номер повреждён — начинаем заново
            logger.error("Некорректный формат номера заявки: %s", last_number)
    return f"{prefix}{next_seq:04d}"


async def _get_or_create_device(session: AsyncSession, data: RequestCreate) -> Device:
    """Находит устройство клиента по серийному номеру либо создаёт новое."""
    if data.serial_number:
        device = await session.scalar(
            select(Device).where(
                Device.client_id == data.client_id,
                Device.serial_number == data.serial_number,
            )
        )
        if device is not None:
            # Модель/тип могли уточнить при повторном приёме.
            device.device_type = data.device_type
            device.model = data.device_model
            return device

    device = Device(
        client_id=data.client_id,
        device_type=data.device_type,
        model=data.device_model,
        serial_number=data.serial_number,
    )
    session.add(device)
    await session.flush()
    return device


def _add_history(
    session: AsyncSession,
    request: Request,
    event_type: HistoryEventType,
    author: User,
    old_status: RequestStatus | None = None,
    new_status: RequestStatus | None = None,
    comment: str | None = None,
) -> None:
    """Добавляет запись в журнал изменений заявки (Функция 12)."""
    session.add(
        StatusHistory(
            request_id=request.id,
            event_type=event_type,
            old_status=old_status,
            new_status=new_status,
            changed_by=author.id,
            comment=comment,
        )
    )


def _ensure_request_access(request: Request, user: User) -> None:
    """Проверяет право пользователя на работу с заявкой (Функция 4).

    Мастер видит только назначенные на него заявки.
    """
    if user.role in (UserRole.ADMIN, UserRole.MANAGER):
        return
    if user.role == UserRole.MASTER and request.master_id == user.id:
        return
    raise PermissionDeniedError("Заявка недоступна для вашей роли")


def _apply_role_scope(stmt: Select, user: User) -> Select:
    """Ограничивает выборку заявок в соответствии с ролью пользователя."""
    if user.role == UserRole.MASTER:
        return stmt.where(Request.master_id == user.id)
    return stmt


async def _reload(session: AsyncSession, request_id: int) -> Request:
    """Перечитывает заявку вместе со связанными объектами.

    В асинхронном режиме «ленивая» подгрузка связей при обращении к атрибуту
    невозможна, поэтому после изменений объект перечитывается явно с
    selectinload — иначе сериализация ответа упадёт с MissingGreenlet.
    """
    stmt = (
        select(Request)
        .where(Request.id == request_id)
        .options(
            selectinload(Request.client),
            selectinload(Request.device),
            selectinload(Request.manager),
            selectinload(Request.master),
        )
    )
    return (await session.execute(stmt)).scalars().one()


# --------------------------------------------------------------------------
# Основные операции
# --------------------------------------------------------------------------
async def get_request_or_404(session: AsyncSession, request_id: int) -> Request:
    """Возвращает заявку или выбрасывает NotFoundError."""
    request = await session.get(Request, request_id)
    if request is None:
        raise NotFoundError("Заявка не найдена")
    return request


async def get_request_for_user(session: AsyncSession, request_id: int, user: User) -> Request:
    """Возвращает заявку с проверкой прав доступа."""
    request = await get_request_or_404(session, request_id)
    _ensure_request_access(request, user)
    return request


async def create_request(session: AsyncSession, data: RequestCreate, manager: User) -> Request:
    """Создаёт заявку на ремонт (Функция 7)."""
    await get_client_or_404(session, data.client_id)
    device = await _get_or_create_device(session, data)

    # До 5 попыток на случай конкурентной выдачи одинакового номера.
    for attempt in range(5):
        request = Request(
            number=await generate_request_number(session),
            client_id=data.client_id,
            device_id=device.id,
            manager_id=manager.id,
            status=RequestStatus.ACCEPTED,  # начальный статус — «Принята»
            priority=data.priority,
            description=data.problem_description,
            deadline=data.deadline,
        )
        session.add(request)
        try:
            await session.flush()
            break
        except IntegrityError:
            await session.rollback()
            if attempt == 4:
                raise ConflictError("Не удалось сгенерировать номер заявки") from None
            # После rollback объекты сессии сброшены — восстанавливаем устройство.
            device = await _get_or_create_device(session, data)
    else:  # pragma: no cover
        raise ConflictError("Не удалось создать заявку")

    _add_history(
        session,
        request,
        HistoryEventType.CREATED,
        manager,
        new_status=RequestStatus.ACCEPTED,
        comment="Заявка зарегистрирована",
    )
    await session.commit()
    request = await _reload(session, request.id)

    log_action(
        "request.created",
        user_id=manager.id,
        request_id=request.id,
        number=request.number,
        client_id=request.client_id,
    )
    return request


async def list_requests(
    session: AsyncSession,
    user: User,
    pagination: PaginationParams,
    status: RequestStatus | None = None,
    priority: RequestPriority | None = None,
    master_id: int | None = None,
    client_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    sort_by: str = "created_at",
    sort_desc: bool = True,
) -> tuple[list[Request], int]:
    """Поиск и фильтрация заявок (Функция 11)."""
    stmt = _apply_role_scope(select(Request), user)

    if status is not None:
        stmt = stmt.where(Request.status == status)
    if priority is not None:
        stmt = stmt.where(Request.priority == priority)
    if master_id is not None:
        stmt = stmt.where(Request.master_id == master_id)
    if client_id is not None:
        stmt = stmt.where(Request.client_id == client_id)
    if date_from is not None:
        stmt = stmt.where(Request.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        stmt = stmt.where(Request.created_at <= datetime.combine(date_to, datetime.max.time()))
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(or_(Request.number.ilike(term), Request.description.ilike(term)))

    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    column = SORTABLE_FIELDS.get(sort_by, Request.created_at)
    stmt = stmt.order_by(column.desc() if sort_desc else column.asc())
    stmt = stmt.offset(pagination.offset).limit(pagination.limit)

    requests = list((await session.execute(stmt)).scalars().unique().all())
    return requests, total


async def update_request(
    session: AsyncSession, request_id: int, data: RequestUpdate, user: User
) -> Request:
    """Редактирует заявку с учётом прав роли (Функция 8)."""
    request = await get_request_for_user(session, request_id, user)

    if request.status in FINAL_STATUSES:
        raise BusinessRuleError(
            f"Заявка в статусе «{REQUEST_STATUS_LABELS[request.status]}» не редактируется"
        )

    payload = data.model_dump(exclude_unset=True)
    if not payload:
        return request

    allowed = MASTER_EDITABLE_FIELDS if user.role == UserRole.MASTER else MANAGER_EDITABLE_FIELDS
    forbidden = set(payload) - allowed
    if forbidden:
        raise PermissionDeniedError(
            "Недоступные для изменения поля: " + ", ".join(sorted(forbidden))
        )

    for field, value in payload.items():
        setattr(request, FIELD_TO_COLUMN.get(field, field), value)

    _add_history(
        session,
        request,
        HistoryEventType.COMMENT,
        user,
        comment="Изменены поля: " + ", ".join(sorted(payload.keys())),
    )
    await session.commit()
    request = await _reload(session, request.id)

    log_action(
        "request.updated",
        user_id=user.id,
        request_id=request.id,
        number=request.number,
        fields=sorted(payload.keys()),
    )
    return request


async def assign_master(
    session: AsyncSession, request_id: int, data: AssignMasterRequest, actor: User
) -> Request:
    """Назначает мастера на заявку с проверкой его загруженности (Функция 9)."""
    request = await get_request_or_404(session, request_id)

    if request.status in FINAL_STATUSES:
        raise BusinessRuleError("Нельзя назначить мастера на закрытую заявку")

    master = await session.get(User, data.master_id)
    if master is None:
        raise NotFoundError("Мастер не найден")
    if master.role != UserRole.MASTER:
        raise BusinessRuleError("Выбранный пользователь не является мастером")
    if not master.is_active:
        raise BusinessRuleError("Учётная запись мастера деактивирована")
    if request.master_id == master.id:
        raise ConflictError("Мастер уже назначен на эту заявку")

    active = await count_active_requests(session, master.id)
    if active >= settings.MAX_ACTIVE_REQUESTS_PER_MASTER:
        raise BusinessRuleError(
            f"Мастер перегружен: {active} активных заявок при лимите "
            f"{settings.MAX_ACTIVE_REQUESTS_PER_MASTER}"
        )

    previous_master_id = request.master_id
    request.master_id = master.id

    _add_history(
        session,
        request,
        HistoryEventType.ASSIGNMENT,
        actor,
        comment=data.comment or f"Назначен мастер: {master.full_name or master.username}",
    )
    await session.commit()
    request = await _reload(session, request.id)

    notification_service.notify_master_assigned(master, request)
    log_action(
        "request.master_assigned",
        user_id=actor.id,
        request_id=request.id,
        number=request.number,
        master_id=master.id,
        previous_master_id=previous_master_id,
    )
    return request


async def change_status(
    session: AsyncSession, request_id: int, data: StatusChangeRequest, user: User
) -> Request:
    """Меняет статус заявки с контролем допустимых переходов (Функция 10)."""
    request = await get_request_for_user(session, request_id, user)
    old_status = request.status
    new_status = data.status

    if old_status == new_status:
        raise ConflictError("Заявка уже находится в этом статусе")

    if not is_transition_allowed(old_status, new_status):
        available = ", ".join(
            REQUEST_STATUS_LABELS[s] for s in sorted(allowed_targets(old_status), key=lambda x: x.value)
        )
        raise BusinessRuleError(
            f"Недопустимый переход «{REQUEST_STATUS_LABELS[old_status]}» → "
            f"«{REQUEST_STATUS_LABELS[new_status]}». "
            + (f"Доступны: {available}" if available else "Заявка закрыта.")
        )

    if not can_role_set_status(user.role, new_status):
        raise PermissionDeniedError(
            f"Ваша роль не может переводить заявку в статус "
            f"«{REQUEST_STATUS_LABELS[new_status]}»"
        )

    # Нельзя взять заявку в работу, пока не назначен исполнитель.
    if new_status == RequestStatus.IN_REPAIR and request.master_id is None:
        raise BusinessRuleError("Перед началом ремонта назначьте мастера")

    request.status = new_status
    if new_status in FINAL_STATUSES:
        request.closed_at = datetime.now(tz=timezone.utc)
    elif old_status in FINAL_STATUSES:  # возврат из закрытого статуса недоступен
        request.closed_at = None

    _add_history(
        session,
        request,
        HistoryEventType.STATUS_CHANGE,
        user,
        old_status=old_status,
        new_status=new_status,
        comment=data.comment,
    )
    await session.commit()
    request = await _reload(session, request.id)

    if new_status in CLIENT_NOTIFICATION_STATUSES:
        notification_service.notify_client_status_changed(request.client, request, new_status)

    log_action(
        "request.status_changed",
        user_id=user.id,
        request_id=request.id,
        number=request.number,
        old_status=old_status.value,
        new_status=new_status.value,
    )
    return request


async def get_history(
    session: AsyncSession, request_id: int, user: User
) -> list[StatusHistory]:
    """Возвращает хронологический журнал изменений заявки (Функция 12)."""
    await get_request_for_user(session, request_id, user)
    stmt = (
        select(StatusHistory)
        .where(StatusHistory.request_id == request_id)
        .options(selectinload(StatusHistory.author))
        .order_by(StatusHistory.created_at.asc(), StatusHistory.id.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def add_comment(
    session: AsyncSession, request_id: int, comment: str, user: User
) -> StatusHistory:
    """Добавляет комментарий в журнал заявки."""
    request = await get_request_for_user(session, request_id, user)
    entry = StatusHistory(
        request_id=request.id,
        event_type=HistoryEventType.COMMENT,
        changed_by=user.id,
        comment=comment,
    )
    session.add(entry)
    await session.commit()

    # Перечитываем со связью author — иначе сериализация ответа не сможет
    # подгрузить её «лениво» в асинхронном контексте.
    entry = (
        await session.execute(
            select(StatusHistory)
            .where(StatusHistory.id == entry.id)
            .options(selectinload(StatusHistory.author))
        )
    ).scalars().one()

    log_action("request.comment_added", user_id=user.id, request_id=request.id)
    return entry
