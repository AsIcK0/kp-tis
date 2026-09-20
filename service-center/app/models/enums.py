"""Перечисления предметной области.

Наследование от ``str`` позволяет использовать значения напрямую в Pydantic-схемах
и JSON-ответах, а также сравнивать их со строками.
"""

import enum


class UserRole(str, enum.Enum):
    """Роли пользователей системы (раздел 2 ТЗ)."""

    ADMIN = "admin"  # Администратор — полный доступ
    MANAGER = "manager"  # Менеджер — заявки и клиенты
    MASTER = "master"  # Мастер — только свои заявки
    STOREKEEPER = "storekeeper"  # Кладовщик — только склад


class RequestStatus(str, enum.Enum):
    """Статусы заявки на ремонт (Функция 10)."""

    ACCEPTED = "accepted"  # Принята
    DIAGNOSTICS = "diagnostics"  # Диагностика
    AWAITING_APPROVAL = "awaiting_approval"  # Ожидание согласования
    IN_REPAIR = "in_repair"  # В ремонте
    AWAITING_PARTS = "awaiting_parts"  # Ожидание запчастей
    READY = "ready"  # Готова к выдаче
    ISSUED = "issued"  # Выдана
    CANCELLED = "cancelled"  # Отменена


class RequestPriority(str, enum.Enum):
    """Приоритет заявки (Функция 7)."""

    LOW = "low"  # низкий
    MEDIUM = "medium"  # средний
    HIGH = "high"  # высокий


class HistoryEventType(str, enum.Enum):
    """Тип события в истории заявки (Функция 12)."""

    CREATED = "created"  # заявка создана
    STATUS_CHANGE = "status_change"  # смена статуса
    ASSIGNMENT = "assignment"  # назначение мастера
    COMMENT = "comment"  # комментарий / прочее событие


# Человекочитаемые подписи — используются в отчётах, уведомлениях и на клиенте.
USER_ROLE_LABELS: dict[UserRole, str] = {
    UserRole.ADMIN: "Администратор",
    UserRole.MANAGER: "Менеджер",
    UserRole.MASTER: "Мастер",
    UserRole.STOREKEEPER: "Кладовщик",
}

REQUEST_STATUS_LABELS: dict[RequestStatus, str] = {
    RequestStatus.ACCEPTED: "Принята",
    RequestStatus.DIAGNOSTICS: "Диагностика",
    RequestStatus.AWAITING_APPROVAL: "Ожидание согласования",
    RequestStatus.IN_REPAIR: "В ремонте",
    RequestStatus.AWAITING_PARTS: "Ожидание запчастей",
    RequestStatus.READY: "Готова к выдаче",
    RequestStatus.ISSUED: "Выдана",
    RequestStatus.CANCELLED: "Отменена",
}

REQUEST_PRIORITY_LABELS: dict[RequestPriority, str] = {
    RequestPriority.LOW: "Низкий",
    RequestPriority.MEDIUM: "Средний",
    RequestPriority.HIGH: "Высокий",
}
