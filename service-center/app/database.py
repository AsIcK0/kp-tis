"""Подключение к базе данных PostgreSQL.

Используется асинхронный движок SQLAlchemy 2.0 (драйвер asyncpg), что хорошо
сочетается с асинхронной природой FastAPI: обработчик не блокирует event loop
на время ожидания ответа СУБД.
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()

# pool_pre_ping=True — проверка «живости» соединения перед выдачей из пула:
# защищает от ошибок после перезапуска контейнера с БД.
engine = create_async_engine(
    settings.database_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# expire_on_commit=False — после commit() объекты остаются пригодными для чтения,
# иначе в асинхронном режиме обращение к атрибуту вызовет неявную загрузку.
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-зависимость: выдаёт сессию БД на время обработки запроса."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# Короткий псевдоним для аннотаций в роутерах и сервисах.
SessionDep = Annotated[AsyncSession, Depends(get_session)]
