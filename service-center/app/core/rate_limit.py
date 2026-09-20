"""Ограничение частоты запросов (требование 4.3).

Реализация — «скользящее окно» в памяти процесса. Этого достаточно для одного
экземпляра приложения (учебный/небольшой продуктивный стенд). При горизонтальном
масштабировании счётчики следует вынести в Redis (например, библиотекой
``slowapi`` или ``fastapi-limiter``) — интерфейс зависимости при этом не изменится.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.config import get_settings

settings = get_settings()


class SlidingWindowRateLimiter:
    """Ограничитель «не более N запросов за окно в S секунд» по ключу."""

    def __init__(self, attempts: int, window_seconds: int) -> None:
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Регистрирует попытку.

        :return: (разрешено ли, сколько секунд ждать до следующей попытки).
        """
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            # Выбрасываем отметки, вышедшие за пределы окна.
            while bucket and now - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.attempts:
                retry_after = int(self.window_seconds - (now - bucket[0])) + 1
                return False, retry_after
            bucket.append(now)
            return True, 0

    def reset(self, key: str) -> None:
        """Сбрасывает счётчик (например, после успешного входа)."""
        with self._lock:
            self._hits.pop(key, None)


class RateLimitDependency:
    """FastAPI-зависимость, ограничивающая частоту обращений по IP клиента."""

    def __init__(self, attempts: int | None = None, window_seconds: int | None = None) -> None:
        self._limiter = SlidingWindowRateLimiter(
            attempts=attempts or settings.LOGIN_RATE_LIMIT_ATTEMPTS,
            window_seconds=window_seconds or settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        )

    async def __call__(self, request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"{request.url.path}:{client_ip}"
        allowed, retry_after = self._limiter.check(key)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много попыток. Повторите позже.",
                headers={"Retry-After": str(retry_after)},
            )


#: Общий ограничитель для эндпоинтов аутентификации.
login_rate_limit = RateLimitDependency()
