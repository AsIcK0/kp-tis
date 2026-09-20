"""Криптографические примитивы: хеширование паролей и выпуск JWT."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()

# bcrypt — требование 4.1 ТЗ. deprecated="auto" позволит в будущем
# прозрачно перейти на argon2, не ломая уже сохранённые хеши.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Алгоритм bcrypt обрабатывает не более 72 байт пароля.
BCRYPT_MAX_BYTES = 72

TokenType = Literal["access", "refresh"]


def _truncate_to_bcrypt_limit(password: str) -> str:
    """Безопасно обрезает пароль до 72 байт UTF-8.

    Кириллический пароль из 64 символов занимает 128 байт, и passlib выбросит
    исключение. Обрезаем по границе символа, чтобы не получить битую строку.
    """
    encoded = password.encode("utf-8")
    if len(encoded) <= BCRYPT_MAX_BYTES:
        return password
    return encoded[:BCRYPT_MAX_BYTES].decode("utf-8", errors="ignore")


def hash_password(password: str) -> str:
    """Возвращает bcrypt-хеш пароля."""
    return pwd_context.hash(_truncate_to_bcrypt_limit(password))


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Проверяет соответствие пароля сохранённому хешу."""
    return pwd_context.verify(_truncate_to_bcrypt_limit(plain_password), password_hash)


def _create_token(
    subject: int,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str, datetime]:
    """Собирает и подписывает JWT.

    :return: кортеж (закодированный токен, jti, момент истечения).
    """
    now = datetime.now(tz=timezone.utc)
    expires_at = now + expires_delta
    jti = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, jti, expires_at


def create_access_token(user_id: int, role: str) -> tuple[str, datetime]:
    """Выпускает access-токен (время жизни — 30 минут по умолчанию)."""
    token, _jti, expires_at = _create_token(
        subject=user_id,
        token_type="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims={"role": role},
    )
    return token, expires_at


def create_refresh_token(user_id: int) -> tuple[str, str, datetime]:
    """Выпускает refresh-токен (время жизни — 7 дней по умолчанию)."""
    return _create_token(
        subject=user_id,
        token_type="refresh",
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict[str, Any]:
    """Проверяет подпись и срок действия токена.

    :raises JWTError: если токен повреждён, подделан или просрочен.
    """
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


__all__ = [
    "JWTError",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_password",
    "verify_password",
]
