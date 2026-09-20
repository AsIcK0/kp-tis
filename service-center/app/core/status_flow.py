"""Машина состояний заявки (требование п.6).

Все правила перехода собраны в одном месте в виде словарей — их легко
просмотреть, изменить и покрыть тестами, не трогая код сервисов.
"""

from app.models.enums import RequestStatus, UserRole

#: Разрешённые переходы: из какого статуса в какие можно перейти.
ALLOWED_STATUS_TRANSITIONS: dict[RequestStatus, frozenset[RequestStatus]] = {
    RequestStatus.ACCEPTED: frozenset(
        {RequestStatus.DIAGNOSTICS, RequestStatus.CANCELLED}
    ),
    RequestStatus.DIAGNOSTICS: frozenset(
        {
            RequestStatus.AWAITING_APPROVAL,
            RequestStatus.IN_REPAIR,
            RequestStatus.AWAITING_PARTS,
            RequestStatus.CANCELLED,
        }
    ),
    RequestStatus.AWAITING_APPROVAL: frozenset(
        {
            RequestStatus.IN_REPAIR,
            RequestStatus.AWAITING_PARTS,
            RequestStatus.CANCELLED,
        }
    ),
    RequestStatus.AWAITING_PARTS: frozenset(
        {RequestStatus.IN_REPAIR, RequestStatus.CANCELLED}
    ),
    RequestStatus.IN_REPAIR: frozenset(
        {
            RequestStatus.AWAITING_PARTS,
            RequestStatus.AWAITING_APPROVAL,
            RequestStatus.READY,
            RequestStatus.CANCELLED,
        }
    ),
    RequestStatus.READY: frozenset(
        {RequestStatus.ISSUED, RequestStatus.IN_REPAIR, RequestStatus.CANCELLED}
    ),
    # Терминальные статусы: выход из них невозможен.
    RequestStatus.ISSUED: frozenset(),
    RequestStatus.CANCELLED: frozenset(),
}

#: Терминальные (закрывающие) статусы.
FINAL_STATUSES: frozenset[RequestStatus] = frozenset(
    {RequestStatus.ISSUED, RequestStatus.CANCELLED}
)

#: Активные статусы — используются при подсчёте загруженности мастера.
ACTIVE_STATUSES: frozenset[RequestStatus] = frozenset(
    status for status in RequestStatus if status not in FINAL_STATUSES
)

#: Статусы, при переходе в которые уведомляется клиент (Функция 10).
CLIENT_NOTIFICATION_STATUSES: frozenset[RequestStatus] = frozenset(
    {RequestStatus.READY, RequestStatus.CANCELLED}
)

#: Кто имеет право устанавливать тот или иной статус.
#: Администратор присутствует во всех наборах — у него полный доступ.
STATUS_ALLOWED_ROLES: dict[RequestStatus, frozenset[UserRole]] = {
    RequestStatus.DIAGNOSTICS: frozenset({UserRole.ADMIN, UserRole.MANAGER, UserRole.MASTER}),
    RequestStatus.AWAITING_APPROVAL: frozenset(
        {UserRole.ADMIN, UserRole.MANAGER, UserRole.MASTER}
    ),
    RequestStatus.IN_REPAIR: frozenset({UserRole.ADMIN, UserRole.MANAGER, UserRole.MASTER}),
    RequestStatus.AWAITING_PARTS: frozenset(
        {UserRole.ADMIN, UserRole.MANAGER, UserRole.MASTER}
    ),
    RequestStatus.READY: frozenset({UserRole.ADMIN, UserRole.MANAGER, UserRole.MASTER}),
    # Выдачу и отмену подтверждает только менеджер или администратор.
    RequestStatus.ISSUED: frozenset({UserRole.ADMIN, UserRole.MANAGER}),
    RequestStatus.CANCELLED: frozenset({UserRole.ADMIN, UserRole.MANAGER}),
    RequestStatus.ACCEPTED: frozenset({UserRole.ADMIN, UserRole.MANAGER}),
}


def is_transition_allowed(current: RequestStatus, target: RequestStatus) -> bool:
    """Проверяет, разрешён ли переход ``current`` -> ``target``."""
    return target in ALLOWED_STATUS_TRANSITIONS.get(current, frozenset())


def allowed_targets(current: RequestStatus) -> frozenset[RequestStatus]:
    """Возвращает множество статусов, доступных из текущего."""
    return ALLOWED_STATUS_TRANSITIONS.get(current, frozenset())


def can_role_set_status(role: UserRole, target: RequestStatus) -> bool:
    """Проверяет, вправе ли роль переводить заявку в указанный статус."""
    return role in STATUS_ALLOWED_ROLES.get(target, frozenset())
