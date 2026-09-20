"""Пакет роутеров. Здесь собирается общий роутер версии API v1."""

from fastapi import APIRouter

from app.config import get_settings
from app.routers.auth import router as auth_router
from app.routers.clients import router as clients_router
from app.routers.reports import router as reports_router
from app.routers.requests import router as requests_router
from app.routers.spare_parts import router as spare_parts_router
from app.routers.users import router as users_router

settings = get_settings()

# Версионирование API через префикс /api/v1 (требование 4.2).
api_router = APIRouter(prefix=settings.API_V1_PREFIX)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(clients_router)
api_router.include_router(requests_router)
api_router.include_router(spare_parts_router)
api_router.include_router(reports_router)

__all__ = ["api_router"]
