"""Общие схемы, переиспользуемые всеми модулями API."""

from math import ceil
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """Базовая схема для чтения из ORM-объектов."""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """Страница результатов постраничной выборки."""

    items: list[T] = Field(description="Записи текущей страницы")
    total: int = Field(description="Общее количество записей")
    page: int = Field(description="Номер текущей страницы (с 1)")
    size: int = Field(description="Размер страницы")
    pages: int = Field(description="Всего страниц")

    @classmethod
    def create(cls, items: list[T], total: int, page: int, size: int) -> "Page[T]":
        """Фабрика страницы с автоматическим расчётом количества страниц."""
        return cls(
            items=items,
            total=total,
            page=page,
            size=size,
            pages=ceil(total / size) if size else 0,
        )


class MessageResponse(BaseModel):
    """Простой ответ с текстовым сообщением."""

    message: str


class ErrorResponse(BaseModel):
    """Единый формат ошибки (требование 4.2)."""

    detail: str


# Готовые описания ответов для документации Swagger.
COMMON_ERROR_RESPONSES: dict[int | str, dict] = {
    400: {"model": ErrorResponse, "description": "Некорректный запрос"},
    401: {"model": ErrorResponse, "description": "Требуется аутентификация"},
    403: {"model": ErrorResponse, "description": "Недостаточно прав"},
    404: {"model": ErrorResponse, "description": "Ресурс не найден"},
    409: {"model": ErrorResponse, "description": "Конфликт данных"},
}
