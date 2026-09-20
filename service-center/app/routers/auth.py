"""Эндпоинты аутентификации и авторизации (Функции 1–3)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.rate_limit import login_rate_limit
from app.database import SessionDep
from app.dependencies import CurrentUser
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, TokenPair
from app.schemas.common import COMMON_ERROR_RESPONSES, MessageResponse
from app.schemas.user import UserRead, UserRegister
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Аутентификация"], responses=COMMON_ERROR_RESPONSES)


def _client_info(request: Request) -> tuple[str | None, str | None]:
    """Извлекает User-Agent и IP клиента для журнала выданных токенов."""
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return user_agent, ip_address


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация пользователя",
    description=(
        "Самостоятельная регистрация. Пользователю всегда назначается роль «менеджер»; "
        "сотрудников с другими ролями создаёт администратор через POST /users."
    ),
    dependencies=[Depends(login_rate_limit)],
)
async def register(session: SessionDep, data: UserRegister) -> UserRead:
    user = await auth_service.register_user(session, data)
    return UserRead.model_validate(user)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Авторизация (JSON)",
    description="Возвращает пару access/refresh токенов.",
    dependencies=[Depends(login_rate_limit)],
)
async def login(session: SessionDep, data: LoginRequest, request: Request) -> TokenPair:
    user = await auth_service.authenticate_user(session, data.username, data.password)
    user_agent, ip_address = _client_info(request)
    return await auth_service.issue_token_pair(session, user, user_agent, ip_address)


@router.post(
    "/token",
    response_model=TokenPair,
    summary="Авторизация (OAuth2 form)",
    description=(
        "Совместимый с OAuth2 вариант входа через form-data. "
        "Используется кнопкой Authorize в Swagger UI."
    ),
    dependencies=[Depends(login_rate_limit)],
)
async def login_form(
    session: SessionDep,
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenPair:
    user = await auth_service.authenticate_user(session, form_data.username, form_data.password)
    user_agent, ip_address = _client_info(request)
    return await auth_service.issue_token_pair(session, user, user_agent, ip_address)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Обновление токенов",
    description="Выдаёт новую пару токенов и отзывает переданный refresh-токен (ротация).",
)
async def refresh(session: SessionDep, data: RefreshRequest, request: Request) -> TokenPair:
    user_agent, ip_address = _client_info(request)
    return await auth_service.refresh_token_pair(
        session, data.refresh_token, user_agent, ip_address
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Выход из аккаунта",
    description="Инвалидирует refresh-токен. Клиент должен удалить токены из хранилища.",
)
async def logout(
    session: SessionDep, data: LogoutRequest, current_user: CurrentUser
) -> MessageResponse:
    await auth_service.logout(session, data.refresh_token, current_user, data.all_devices)
    return MessageResponse(message="Выход выполнен успешно")


@router.get(
    "/me",
    response_model=UserRead,
    summary="Текущий пользователь",
    description="Возвращает профиль владельца access-токена.",
)
async def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
