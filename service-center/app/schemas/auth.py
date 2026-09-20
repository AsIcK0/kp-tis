"""Pydantic-схемы модуля аутентификации."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.user import UserRead


class LoginRequest(BaseModel):
    """Данные для входа (Функция 2)."""

    username: str = Field(examples=["admin"])
    password: str = Field(examples=["admin12345"])


class TokenPair(BaseModel):
    """Пара токенов, выдаваемая при успешной аутентификации."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: datetime = Field(description="Момент истечения access-токена (UTC)")
    user: UserRead | None = None


class RefreshRequest(BaseModel):
    """Запрос на обновление пары токенов (POST /auth/refresh)."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Запрос на выход: инвалидирует переданный refresh-токен."""

    refresh_token: str
    # Если true — отзываются все refresh-токены пользователя (выход со всех устройств).
    all_devices: bool = False
