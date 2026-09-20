"""Pydantic-схемы модуля управления складом."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.user import UserShort


class SparePartBase(BaseModel):
    """Общие поля номенклатуры (Функция 13)."""

    name: str = Field(min_length=2, max_length=255, examples=["Аккумулятор Lenovo L19"])
    article: str = Field(min_length=1, max_length=64, examples=["BAT-L19-45"])
    quantity: int = Field(ge=0, default=0)
    min_quantity: int = Field(ge=0, default=0, description="Порог уведомления об остатке")
    price: Decimal = Field(ge=0, default=Decimal("0.00"), max_digits=12, decimal_places=2)
    supplier: str | None = Field(default=None, max_length=255)


class SparePartCreate(SparePartBase):
    """Создание позиции номенклатуры."""


class SparePartUpdate(BaseModel):
    """Частичное редактирование позиции номенклатуры."""

    name: str | None = Field(default=None, min_length=2, max_length=255)
    article: str | None = Field(default=None, min_length=1, max_length=64)
    quantity: int | None = Field(default=None, ge=0)
    min_quantity: int | None = Field(default=None, ge=0)
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    supplier: str | None = Field(default=None, max_length=255)


class SparePartRead(ORMModel):
    """Представление позиции склада."""

    id: int
    name: str
    article: str
    quantity: int
    min_quantity: int
    price: Decimal
    supplier: str | None
    is_low_stock: bool
    created_at: datetime
    updated_at: datetime


class WriteOffRequest(BaseModel):
    """Списание запчасти на заявку (Функция 14)."""

    request_id: int
    quantity: int = Field(gt=0, examples=[1])
    comment: str | None = None


class SparePartUsageRead(ORMModel):
    """Факт списания запчасти."""

    id: int
    request_id: int
    spare_part_id: int
    quantity: int
    price_at_use: Decimal
    total_cost: Decimal
    used_at: datetime
    author: UserShort | None
