"""Точка входа приложения «Управление сервисным центром».

Здесь собирается FastAPI-приложение: подключаются роутеры, middleware,
обработчики ошибок и выполняются стартовые процедуры.
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import get_settings
from app.core.logging_config import setup_logging
from app.database import AsyncSessionFactory, engine
from app.models import Base
from app.routers import api_router
from app.services.exceptions import ServiceError
from app.services.user_service import ensure_first_admin

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Стартовые и завершающие процедуры приложения."""
    setup_logging()
    logger.info("Запуск %s v%s", settings.APP_NAME, settings.APP_VERSION)

    if settings.AUTO_CREATE_TABLES:
        # Удобно для разработки и демонстрации. В продуктивной среде схему
        # разворачивает Alembic: `alembic upgrade head`.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Схема БД синхронизирована")

    async with AsyncSessionFactory() as session:
        await ensure_first_admin(session)

    yield

    await engine.dispose()
    logger.info("Приложение остановлено")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "REST API информационной системы «Управление сервисным центром»: "
        "учёт заявок на ремонт, клиентов, устройств, склада запчастей и отчётности.\n\n"
        "**Аутентификация:** JWT Bearer. Получите токен через `POST /api/v1/auth/login` "
        "и нажмите «Authorize»."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Присваивает запросу идентификатор и логирует его выполнение."""
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
    started = time.perf_counter()

    response = await call_next(request)

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "%s %s -> %s (%s мс)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    response.headers["X-Request-ID"] = request_id
    return response


# --------------------------------------------------------------------------
# Обработчики ошибок — единый формат {"detail": "сообщение"} (требование 4.2)
# --------------------------------------------------------------------------
@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    """Преобразует доменное исключение в HTTP-ответ."""
    logger.info(
        "Бизнес-ошибка: %s",
        exc.message,
        extra={"path": request.url.path, "status_code": exc.status_code},
    )
    headers = (
        {"WWW-Authenticate": "Bearer"}
        if exc.status_code == status.HTTP_401_UNAUTHORIZED
        else None
    )
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.message}, headers=headers
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Приводит ошибки валидации Pydantic к читаемому виду (422)."""
    messages = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"] if part != "body")
        messages.append(f"{location}: {error['msg']}" if location else error["msg"])
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "; ".join(messages)},
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """Нарушение ограничений целостности — конфликт данных (409)."""
    logger.warning("Нарушение целостности данных", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Операция нарушает ограничения целостности данных"},
    )


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Прочие ошибки БД — 500 без раскрытия деталей клиенту."""
    logger.error("Ошибка базы данных", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Внутренняя ошибка сервера"},
    )


app.include_router(api_router)


@app.get("/health", tags=["Служебные"], summary="Проверка работоспособности")
async def health() -> dict[str, str]:
    """Health check для docker-compose и балансировщика."""
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/", tags=["Служебные"], summary="Корневой эндпоинт", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "api": settings.API_V1_PREFIX,
    }
