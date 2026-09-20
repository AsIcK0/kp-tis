"""Pydantic-схемы модуля пользователей."""

import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import UserRole
from app.schemas.common import ORMModel

# Логин: латиница, цифры, точка, дефис, подчёркивание; 3–32 символа (Функция 1).
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,32}$")


def validate_username(value: str) -> str:
    """Проверяет формат логина и приводит его к нижнему регистру."""
    value = value.strip()
    if not USERNAME_PATTERN.fullmatch(value):
        raise ValueError(
            "Логин должен содержать 3–32 символа: латинские буквы, цифры, «.», «-», «_»"
        )
    return value.lower()


def validate_password(value: str) -> str:
    """Проверяет длину и минимальную сложность пароля."""
    if not 8 <= len(value) <= 64:
        raise ValueError("Пароль должен содержать от 8 до 64 символов")
    if value.isdigit() or value.isalpha():
        raise ValueError("Пароль должен содержать и буквы, и цифры")
    return value


class UserBase(BaseModel):
    """Общие поля учётной записи."""

    username: str = Field(min_length=3, max_length=32, examples=["ivanov"])
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=255)

    @field_validator("username")
    @classmethod
    def _check_username(cls, value: str) -> str:
        return validate_username(value)


class UserCreate(UserBase):
    """Создание пользователя администратором (POST /users)."""

    password: str = Field(min_length=8, max_length=64)
    role: UserRole = UserRole.MANAGER

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return validate_password(value)


class UserRegister(UserBase):
    """Самостоятельная регистрация (POST /auth/register).

    Роль здесь не принимается: пользователю всегда назначается «менеджер».
    Создать сотрудника с произвольной ролью может только администратор
    через POST /users (Функция 1).
    """

    password: str = Field(min_length=8, max_length=64)

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return validate_password(value)


class UserUpdate(BaseModel):
    """Частичное редактирование пользователя (PATCH /users/{id})."""

    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=64)

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str | None) -> str | None:
        return validate_password(value) if value is not None else None


class UserRead(ORMModel):
    """Представление пользователя в ответах API (без хеша пароля)."""

    id: int
    username: str
    email: EmailStr
    full_name: str | None
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserShort(ORMModel):
    """Краткое представление пользователя для вложенных объектов."""

    id: int
    username: str
    full_name: str | None
    role: UserRole


class MasterWorkload(ORMModel):
    """Загруженность мастера — используется при назначении на заявку."""

    id: int
    username: str
    full_name: str | None
    active_requests: int
    limit: int
