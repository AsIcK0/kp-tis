"""Зависимости FastAPI: аутентификация, разграничение прав, пагинация.

Реализует Функцию 4 ТЗ: роль пользователя проверяется при каждом обращении
к защищённому эндпоинту.
"""

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer

from app.config import get_settings
from app.core.security import JWTError, decode_token
from app.database import SessionDep
from app.models.enums import UserRole
from app.models.user import User

settings = get_settings()
logger = logging.getLogger(__name__)

# tokenUrl указывает на form-совместимый эндпоинт, чтобы кнопка Authorize
# в Swagger UI работала «из коробки».
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/token",
    auto_error=False,
)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Недействительный или просроченный токен",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    session: SessionDep,
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
) -> User:
    """Извлекает и проверяет пользователя по access-токену."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(token)
    except JWTError:
        raise _CREDENTIALS_ERROR from None

    # Refresh-токен не должен приниматься как access-токен.
    if payload.get("type") != "access":
        raise _CREDENTIALS_ERROR

    user_id = payload.get("sub")
    if user_id is None:
        raise _CREDENTIALS_ERROR

    user = await session.get(User, int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден или деактивирован",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


class RoleChecker:
    """Зависимость-фабрика: пропускает только указанные роли.

    Пример использования::

        @router.get("/users", dependencies=[Depends(require_admin)])
    """

    def __init__(self, *roles: UserRole) -> None:
        self.roles = frozenset(roles)

    def __call__(self, user: CurrentUser) -> User:
        if user.role not in self.roles:
            logger.warning(
                "Отказано в доступе",
                extra={
                    "user_id": user.id,
                    "user_role": user.role.value,
                    "required_roles": [r.value for r in self.roles],
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для выполнения операции",
            )
        return user


# Готовые наборы прав для роутеров.
require_admin = RoleChecker(UserRole.ADMIN)
require_manager = RoleChecker(UserRole.ADMIN, UserRole.MANAGER)
require_warehouse = RoleChecker(UserRole.ADMIN, UserRole.STOREKEEPER)
require_staff = RoleChecker(
    UserRole.ADMIN, UserRole.MANAGER, UserRole.MASTER, UserRole.STOREKEEPER
)
# Работа с заявками: кладовщик к ним доступа не имеет.
require_request_access = RoleChecker(UserRole.ADMIN, UserRole.MANAGER, UserRole.MASTER)
# Отчётность доступна руководству; кладовщику — только отчёт по запчастям
# (проверяется отдельно в роутере отчётов).
require_reports_access = RoleChecker(UserRole.ADMIN, UserRole.MANAGER, UserRole.STOREKEEPER)

AdminUser = Annotated[User, Depends(require_admin)]
ManagerUser = Annotated[User, Depends(require_manager)]
WarehouseUser = Annotated[User, Depends(require_warehouse)]
RequestUser = Annotated[User, Depends(require_request_access)]
ReportUser = Annotated[User, Depends(require_reports_access)]
StaffUser = Annotated[User, Depends(require_staff)]


@dataclass(frozen=True)
class PaginationParams:
    """Параметры постраничного вывода."""

    page: int
    size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size

    @property
    def limit(self) -> int:
        return self.size


def get_pagination(
    page: Annotated[int, Query(ge=1, description="Номер страницы")] = 1,
    size: Annotated[
        int,
        Query(ge=1, le=settings.MAX_PAGE_SIZE, description="Размер страницы"),
    ] = settings.DEFAULT_PAGE_SIZE,
) -> PaginationParams:
    """Зависимость постраничной навигации (по умолчанию 20 записей)."""
    return PaginationParams(page=page, size=size)


Pagination = Annotated[PaginationParams, Depends(get_pagination)]
