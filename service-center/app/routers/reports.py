"""Эндпоинты модуля отчётности (Функция 15).

Каждый отчёт отдаётся в JSON либо выгружается в CSV параметром ``format=csv``.
"""

import csv
import io
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.database import SessionDep
from app.dependencies import ReportUser
from app.models.enums import REQUEST_STATUS_LABELS, UserRole
from app.schemas.common import COMMON_ERROR_RESPONSES
from app.schemas.report import RevenueReport, SparePartsReport, WorksReport
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["Отчёты"], responses=COMMON_ERROR_RESPONSES)

ExportFormat = Literal["json", "csv"]


def _csv_response(headers: list[str], rows: list[list[Any]], filename: str) -> Response:
    """Формирует CSV-ответ.

    Разделитель «;» и BOM (utf-8-sig) — чтобы файл корректно открывался
    в русской локали Microsoft Excel без ручного импорта.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    writer.writerows(rows)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Response(
        content=buffer.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}_{stamp}.csv"'},
    )


def _fmt_dt(value: datetime | None) -> str:
    return value.strftime("%d.%m.%Y %H:%M") if value else ""


@router.get(
    "/works",
    response_model=WorksReport,
    summary="Отчёт по выполненным работам",
    description="Заявки в статусах «Готова к выдаче» и «Выдана» за период, фильтр по мастеру.",
)
async def works_report(
    session: SessionDep,
    user: ReportUser,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    master_id: Annotated[int | None, Query()] = None,
    export_format: Annotated[ExportFormat, Query(alias="format")] = "json",
) -> Any:
    if user.role == UserRole.STOREKEEPER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Кладовщику доступен только отчёт по запчастям",
        )

    report = await report_service.works_report(session, date_from, date_to, master_id)
    if export_format == "json":
        return report

    return _csv_response(
        headers=[
            "Номер", "Клиент", "Устройство", "Мастер", "Статус",
            "Создана", "Закрыта", "Работы, руб.", "Запчасти, руб.", "Итого, руб.",
        ],
        rows=[
            [
                row.number,
                row.client_name,
                row.device,
                row.master or "",
                REQUEST_STATUS_LABELS[row.status],
                _fmt_dt(row.created_at),
                _fmt_dt(row.closed_at),
                row.work_cost,
                row.parts_cost,
                row.total_cost,
            ]
            for row in report.rows
        ],
        filename="works_report",
    )


@router.get(
    "/spare-parts",
    response_model=SparePartsReport,
    summary="Отчёт по использованным запчастям",
)
async def spare_parts_report(
    session: SessionDep,
    _user: ReportUser,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    export_format: Annotated[ExportFormat, Query(alias="format")] = "json",
) -> Any:
    report = await report_service.spare_parts_report(session, date_from, date_to)
    if export_format == "json":
        return report

    return _csv_response(
        headers=[
            "Артикул", "Наименование", "Списано, шт.",
            "Сумма, руб.", "Заявок", "Текущий остаток",
        ],
        rows=[
            [
                row.article,
                row.name,
                row.total_quantity,
                row.total_cost,
                row.requests_count,
                row.current_quantity,
            ]
            for row in report.rows
        ],
        filename="spare_parts_report",
    )


@router.get(
    "/revenue",
    response_model=RevenueReport,
    summary="Отчёт по выручке",
    description="Сумма работ и запчастей по выданным заявкам с разбивкой по дням или месяцам.",
)
async def revenue_report(
    session: SessionDep,
    user: ReportUser,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    group_by: Annotated[Literal["day", "month"], Query()] = "month",
    export_format: Annotated[ExportFormat, Query(alias="format")] = "json",
) -> Any:
    if user.role == UserRole.STOREKEEPER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Кладовщику доступен только отчёт по запчастям",
        )

    report = await report_service.revenue_report(session, date_from, date_to, group_by)
    if export_format == "json":
        return report

    return _csv_response(
        headers=["Период", "Заявок", "Работы, руб.", "Запчасти, руб.", "Итого, руб."],
        rows=[
            [row.period, row.requests_count, row.work_cost, row.parts_cost, row.total]
            for row in report.rows
        ],
        filename="revenue_report",
    )
