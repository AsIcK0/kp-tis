"""Конфигурация приложения.

Все настройки читаются из переменных окружения (или файла .env) с помощью
pydantic-settings. Это позволяет менять параметры развёртывания без правки кода.
"""

from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Набор настроек информационной системы «Управление сервисным центром»."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Общие параметры приложения -------------------------------------
    APP_NAME: str = "Service Center API"
    APP_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    # Автоматическое создание таблиц при старте (удобно для разработки).
    # В продуктивной среде миграции выполняет Alembic.
    AUTO_CREATE_TABLES: bool = True

    # --- Подключение к PostgreSQL ---------------------------------------
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "service_center"
    POSTGRES_PASSWORD: str = "service_center"
    POSTGRES_DB: str = "service_center"

    # --- Параметры JWT ---------------------------------------------------
    JWT_SECRET_KEY: str = "please-change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # требование: 30 минут
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # требование: 7 дней

    # --- Бизнес-правила --------------------------------------------------
    # Разрешена ли самостоятельная регистрация (роль всегда «менеджер»).
    ALLOW_SELF_REGISTRATION: bool = True
    # Максимальное количество активных заявок на одного мастера (Функция 9).
    MAX_ACTIVE_REQUESTS_PER_MASTER: int = 10

    # --- Ограничение частоты запросов к /auth ----------------------------
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 60

    # --- Пагинация -------------------------------------------------------
    DEFAULT_PAGE_SIZE: int = 20  # требование: по 20 записей
    MAX_PAGE_SIZE: int = 100

    # --- Первый администратор (создаётся при старте, если БД пуста) ------
    FIRST_ADMIN_USERNAME: str = "admin"
    FIRST_ADMIN_PASSWORD: str = "admin12345"
    FIRST_ADMIN_EMAIL: str = "admin@service-center.local"

    # --- Логирование -----------------------------------------------------
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True

    # --- CORS ------------------------------------------------------------
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Асинхронный DSN для SQLAlchemy (драйвер asyncpg)."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_url(self) -> str:
        """Синхронный DSN — нужен Alembic и утилитам администрирования."""
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    """Возвращает singleton настроек (кэшируется на время жизни процесса)."""
    return Settings()
