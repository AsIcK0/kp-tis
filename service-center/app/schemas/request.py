"""Pydantic-схемы модуля управления заявками."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, computed_field

from app.models.enums import (
    REQUEST_PRIORITY_LABELS,
    REQUEST_STATUS_LABELS,
    HistoryEventType,
    RequestPriority,
    RequestStatus,
)
from app.schemas.client import ClientShort, DeviceRead
from app.schemas.common import ORMModel
from app.schemas.user import UserShort


class RequestCreate(BaseModel):
    """Создание заявки на ремонт (Функция 7).

    Устройство передаётся полями device_*: сервис найдёт его у клиента
    по серийному номеру или создаст новую карточку устройства.
    """

    client_id: int
    device_type: str = Field(min_length=2, max_length=100, examples=["Ноутбук"])
    device_model: str = Field(min_length=1, max_length=150, examples=["Lenovo IdeaPad 5"])
    serial_number: str | None = Field(default=None, max_length=100)
    problem_description: str = Field(min_length=5, examples=["Не включается, нет реакции на кнопку"])
    priority: RequestPriority = RequestPriority.MEDIUM
    deadline: datetime | None = None


class RequestUpdate(BaseModel):
    """Редактирование заявки (Функция 8).

    Набор полей, доступных конкретному пользователю, ограничивается сервисом:
    менеджер/администратор правят описание, приоритет и срок, мастер —
    только поля выполнения работ.
    """

    problem_description: str | None = Field(default=None, min_length=5)
    priority: RequestPriority | None = None
    deadline: datetime | None = None
    diagnosis: str | None = None
    work_description: str | None = None
    work_cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class AssignMasterRequest(BaseModel):
    """Назначение мастера на заявку (Функция 9)."""

    master_id: int
    comment: str | None = None


class StatusChangeRequest(BaseModel):
    """Смена статуса заявки (Функция 10)."""

    status: RequestStatus
    comment: str | None = Field(default=None, description="Причина или пояснение к переходу")


class SparePartUsageShort(ORMModel):
    """Списанная на заявку запчасть."""

    id: int
    spare_part_id: int
    quantity: int
    price_at_use: Decimal
    used_at: datetime


class RequestRead(ORMModel):
    """Полное представление заявки."""

    id: int
    number: str
    status: RequestStatus
    priority: RequestPriority
    description: str
    diagnosis: str | None
    work_description: str | None
    work_cost: Decimal
    deadline: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    client: ClientShort
    device: DeviceRead
    manager: UserShort
    master: UserShort | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status_label(self) -> str:
        """Человекочитаемое название статуса — для отображения на клиенте."""
        return REQUEST_STATUS_LABELS[self.status]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def priority_label(self) -> str:
        """Человекочитаемое название приоритета."""
        return REQUEST_PRIORITY_LABELS[self.priority]


class RequestListItem(ORMModel):
    """Строка списка заявок — без тяжёлых текстовых полей."""

    id: int
    number: str
    status: RequestStatus
    priority: RequestPriority
    created_at: datetime
    deadline: datetime | None
    client: ClientShort
    master: UserShort | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status_label(self) -> str:
        """Человекочитаемое название статуса."""
        return REQUEST_STATUS_LABELS[self.status]


class HistoryRead(ORMModel):
    """Запись журнала изменений заявки (Функция 12)."""

    id: int
    request_id: int
    event_type: HistoryEventType
    old_status: RequestStatus | None
    new_status: RequestStatus | None
    comment: str | None
    changed_at: datetime
    author: UserShort | None
