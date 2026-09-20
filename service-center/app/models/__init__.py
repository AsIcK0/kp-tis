"""Пакет ORM-моделей.

Импорт всех моделей здесь обязателен: без него ``Base.metadata`` не будет знать
о таблицах в момент вызова ``create_all`` или автогенерации миграций Alembic.
"""

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.client import Client, Device
from app.models.enums import (
    HistoryEventType,
    RequestPriority,
    RequestStatus,
    UserRole,
)
from app.models.request import Request, StatusHistory
from app.models.spare_part import SparePart, SparePartUsage
from app.models.token import RefreshToken
from app.models.user import User

__all__ = [
    "Base",
    "Client",
    "Device",
    "HistoryEventType",
    "IdMixin",
    "RefreshToken",
    "Request",
    "RequestPriority",
    "RequestStatus",
    "SparePart",
    "SparePartUsage",
    "StatusHistory",
    "TimestampMixin",
    "User",
    "UserRole",
]
