"""Pydantic-схемы модуля управления клиентами."""

import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel

_NON_DIGITS = re.compile(r"\D")


def normalize_phone(value: str) -> str:
    """Приводит телефон к каноническому виду +7XXXXXXXXXX.

    Нормализация нужна для корректной проверки дублирования клиентов
    (Функция 5): «+7 (999) 123-45-67» и «8 999 123 45 67» — один и тот же номер.
    """
    digits = _NON_DIGITS.sub("", value)
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    if len(digits) == 10:  # номер без кода страны
        digits = "7" + digits
    if not 11 <= len(digits) <= 15:
        raise ValueError("Некорректный номер телефона")
    return "+" + digits


class ClientBase(BaseModel):
    """Общие поля клиента."""

    full_name: str = Field(min_length=2, max_length=255, examples=["Иванов Иван Иванович"])
    phone: str = Field(examples=["+7 (999) 123-45-67"])
    email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=500)
    notes: str | None = None

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str) -> str:
        return normalize_phone(value)


class ClientCreate(ClientBase):
    """Создание клиента."""


class ClientUpdate(BaseModel):
    """Частичное редактирование клиента."""

    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=500)
    notes: str | None = None

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value is not None else None


class DeviceRead(ORMModel):
    """Устройство клиента."""

    id: int
    client_id: int
    device_type: str
    model: str
    serial_number: str | None


class ClientRead(ORMModel):
    """Представление клиента в ответах API."""

    id: int
    full_name: str
    phone: str
    email: EmailStr | None
    address: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ClientWithDevices(ClientRead):
    """Клиент вместе со списком его устройств."""

    devices: list[DeviceRead] = []


class ClientShort(ORMModel):
    """Краткое представление клиента для вложенных объектов."""

    id: int
    full_name: str
    phone: str
