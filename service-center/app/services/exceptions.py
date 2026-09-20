"""Доменные исключения бизнес-логики.

Сервисы не знают о HTTP: они выбрасывают эти исключения, а единый обработчик
в ``app.main`` превращает их в ответ формата {"detail": "..."} с нужным кодом.
Это и есть разделение бизнес-логики и транспортного слоя (требование п.10).
"""

from http import HTTPStatus


class ServiceError(Exception):
    """Базовая ошибка бизнес-логики."""

    status_code: int = HTTPStatus.BAD_REQUEST

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ServiceError):
    """Запрошенный объект не существует (404)."""

    status_code = HTTPStatus.NOT_FOUND


class ConflictError(ServiceError):
    """Нарушение уникальности или конфликт состояния (409)."""

    status_code = HTTPStatus.CONFLICT


class PermissionDeniedError(ServiceError):
    """Недостаточно прав для операции (403)."""

    status_code = HTTPStatus.FORBIDDEN


class AuthenticationError(ServiceError):
    """Ошибка аутентификации (401)."""

    status_code = HTTPStatus.UNAUTHORIZED


class BusinessRuleError(ServiceError):
    """Нарушение бизнес-правила: недопустимый переход, нехватка остатка и т.п. (400)."""

    status_code = HTTPStatus.BAD_REQUEST
