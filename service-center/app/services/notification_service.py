"""Сервис уведомлений.

В рамках ТЗ уведомления фиксируются в журнале. Точка расширения: здесь
подключается реальный канал доставки (SMTP, SMS-шлюз, push, очередь задач).
Интерфейс функций при этом не меняется, поэтому вызывающий код править
не придётся.
"""

import logging

from app.models.client import Client
from app.models.enums import REQUEST_STATUS_LABELS, RequestStatus
from app.models.request import Request
from app.models.spare_part import SparePart
from app.models.user import User

logger = logging.getLogger(__name__)


def notify_master_assigned(master: User, request: Request) -> None:
    """Уведомляет мастера о назначении на заявку (Функция 9)."""
    logger.info(
        "Уведомление мастеру: назначена заявка %s",
        request.number,
        extra={
            "notification": "master_assigned",
            "master_id": master.id,
            "master_email": master.email,
            "request_id": request.id,
            "request_number": request.number,
        },
    )


def notify_client_status_changed(
    client: Client, request: Request, new_status: RequestStatus
) -> None:
    """Уведомляет клиента о переводе заявки в «Готова к выдаче» или «Отменена»."""
    logger.info(
        "Уведомление клиенту: заявка %s — %s",
        request.number,
        REQUEST_STATUS_LABELS[new_status],
        extra={
            "notification": "client_status_changed",
            "client_id": client.id,
            "client_phone": client.phone,
            "request_id": request.id,
            "request_number": request.number,
            "new_status": new_status.value,
        },
    )


def notify_low_stock(spare_part: SparePart) -> None:
    """Уведомляет склад о снижении остатка ниже минимального (Функция 13)."""
    logger.warning(
        "Остаток запчасти «%s» ниже минимального: %s <= %s",
        spare_part.name,
        spare_part.quantity,
        spare_part.min_quantity,
        extra={
            "notification": "low_stock",
            "spare_part_id": spare_part.id,
            "article": spare_part.article,
            "quantity": spare_part.quantity,
            "min_quantity": spare_part.min_quantity,
        },
    )
