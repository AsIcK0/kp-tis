"""Настройка логирования (требование 4.5).

Поддерживаются два формата: структурированный JSON (для сбора в ELK/Loki)
и обычный текст с временными метками — переключается настройкой LOG_JSON.
"""

import json
import logging
import logging.config
import sys
from typing import Any

from app.config import get_settings

settings = get_settings()

# Стандартные атрибуты LogRecord — всё, что не входит в этот набор,
# считаем пользовательским контекстом и выносим в JSON.
_RESERVED_ATTRS = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "taskName", "thread", "threadName",
    }
)


class JsonFormatter(logging.Formatter):
    """Форматтер, превращающий запись лога в одну JSON-строку."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Дополнительный контекст, переданный через logger.info(..., extra={...}).
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging() -> None:
    """Конфигурирует корневой логгер и логгеры uvicorn."""
    formatter = "json" if settings.LOG_JSON else "text"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {"()": JsonFormatter},
                "text": {
                    "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": formatter,
                    "stream": sys.stdout,
                }
            },
            "root": {"handlers": ["console"], "level": settings.LOG_LEVEL},
            "loggers": {
                "uvicorn": {"handlers": ["console"], "level": settings.LOG_LEVEL, "propagate": False},
                "uvicorn.access": {
                    "handlers": ["console"],
                    "level": settings.LOG_LEVEL,
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["console"],
                    "level": settings.LOG_LEVEL,
                    "propagate": False,
                },
                # SQL-запросы показываем только в режиме отладки.
                "sqlalchemy.engine": {
                    "handlers": ["console"],
                    "level": "INFO" if settings.DEBUG else "WARNING",
                    "propagate": False,
                },
            },
        }
    )


#: Отдельный логгер аудита: «кто, что, когда» изменил в данных.
audit_logger = logging.getLogger("app.audit")


def log_action(action: str, user_id: int | None = None, **context: Any) -> None:
    """Записывает в аудит-лог факт изменения данных.

    :param action: краткий код операции, например ``request.status_changed``.
    :param user_id: идентификатор инициатора операции.
    :param context: произвольные дополнительные поля (id сущности, значения и т.п.).
    """
    audit_logger.info(action, extra={"action": action, "user_id": user_id, **context})
