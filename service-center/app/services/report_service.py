"""Бизнес-логика модуля отчётности (Функция 15).

Отчёты строятся агрегирующими SQL-запросами и не сохраняются в БД.
Денежные значения считаются в Numeric — никаких float.
"""

import logging
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client, Device
from app.models.enums import RequestStatus
from app.models.request import Request
from app.models.spare_part import SparePart, SparePartUsage
from app.models.user import User
from app.schemas.report import (
    RevenuePeriodRow,
    RevenueReport,
    ReportPeriod,
    SparePartsReport,
    SparePartsReportRow,
    WorksReport,
    WorksReportRow,
)

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")

#: Статусы, при которых работы считаются выполненными.
COMPLETED_STATUSES = (RequestStatus.READY, RequestStatus.ISSUED)


def _day_start(value: date | None) -> datetime | None:
    return datetime.combine(value, datetime.min.time()) if value else None


def _day_end(value: date | None) -> datetime | None:
    return datetime.combine(value, datetime.max.time()) if value else None


def _parts_cost_subquery():
    """Подзапрос: стоимость списанных запчастей в разрезе заявок."""
    return (
        select(
            SparePartUsage.request_id.label("request_id"),
            func.coalesce(
                func.sum(SparePartUsage.price_at_use * SparePartUsage.quantity), 0
            ).label("parts_cost"),
        )
        .group_by(SparePartUsage.request_id)
        .subquery()
    )


def _apply_period(stmt: Select, column, date_from: date | None, date_to: date | None) -> Select:
    """Накладывает ограничение по периоду на указанную колонку."""
    if date_from is not None:
        stmt = stmt.where(column >= _day_start(date_from))
    if date_to is not None:
        stmt = stmt.where(column <= _day_end(date_to))
    return stmt


async def works_report(
    session: AsyncSession,
    date_from: date | None = None,
    date_to: date | None = None,
    master_id: int | None = None,
) -> WorksReport:
    """Отчёт по выполненным работам за период с фильтром по мастеру."""
    parts = _parts_cost_subquery()
    # Для выданных заявок ориентируемся на дату закрытия, для готовых —
    # на дату последнего изменения.
    period_column = func.coalesce(Request.closed_at, Request.updated_at)

    stmt = (
        select(
            Request.id,
            Request.number,
            Client.full_name,
            Device.device_type,
            Device.model,
            User.full_name,
            User.username,
            Request.status,
            Request.created_at,
            Request.closed_at,
            Request.work_cost,
            func.coalesce(parts.c.parts_cost, 0).label("parts_cost"),
        )
        .join(Client, Client.id == Request.client_id)
        .join(Device, Device.id == Request.device_id)
        .outerjoin(User, User.id == Request.master_id)
        .outerjoin(parts, parts.c.request_id == Request.id)
        .where(Request.status.in_(COMPLETED_STATUSES))
        .order_by(period_column.desc())
    )
    stmt = _apply_period(stmt, period_column, date_from, date_to)
    if master_id is not None:
        stmt = stmt.where(Request.master_id == master_id)

    rows: list[WorksReportRow] = []
    total_work = total_parts = ZERO

    for record in (await session.execute(stmt)).all():
        (
            request_id,
            number,
            client_name,
            device_type,
            device_model,
            master_full_name,
            master_username,
            status,
            created_at,
            closed_at,
            work_cost,
            parts_cost,
        ) = record

        work_cost = Decimal(work_cost or 0)
        parts_cost = Decimal(parts_cost or 0)
        total_work += work_cost
        total_parts += parts_cost

        rows.append(
            WorksReportRow(
                request_id=request_id,
                number=number,
                client_name=client_name,
                device=f"{device_type} {device_model}".strip(),
                master=master_full_name or master_username,
                status=status,
                created_at=created_at,
                closed_at=closed_at,
                work_cost=work_cost,
                parts_cost=parts_cost,
                total_cost=work_cost + parts_cost,
            )
        )

    return WorksReport(
        period=ReportPeriod(date_from=date_from, date_to=date_to),
        master_id=master_id,
        rows=rows,
        requests_count=len(rows),
        total_work_cost=total_work,
        total_parts_cost=total_parts,
        total_cost=total_work + total_parts,
    )


async def spare_parts_report(
    session: AsyncSession,
    date_from: date | None = None,
    date_to: date | None = None,
) -> SparePartsReport:
    """Отчёт по использованным запчастям за период."""
    stmt = (
        select(
            SparePart.id,
            SparePart.name,
            SparePart.article,
            SparePart.quantity,
            func.sum(SparePartUsage.quantity).label("total_quantity"),
            func.sum(SparePartUsage.quantity * SparePartUsage.price_at_use).label("total_cost"),
            func.count(func.distinct(SparePartUsage.request_id)).label("requests_count"),
        )
        .join(SparePart, SparePart.id == SparePartUsage.spare_part_id)
        .group_by(SparePart.id, SparePart.name, SparePart.article, SparePart.quantity)
        .order_by(func.sum(SparePartUsage.quantity * SparePartUsage.price_at_use).desc())
    )
    stmt = _apply_period(stmt, SparePartUsage.used_at, date_from, date_to)

    rows: list[SparePartsReportRow] = []
    total_quantity = 0
    total_cost = ZERO

    for record in (await session.execute(stmt)).all():
        part_id, name, article, current_qty, qty, cost, requests_count = record
        qty = int(qty or 0)
        cost = Decimal(cost or 0)
        total_quantity += qty
        total_cost += cost
        rows.append(
            SparePartsReportRow(
                spare_part_id=part_id,
                name=name,
                article=article,
                total_quantity=qty,
                total_cost=cost,
                requests_count=requests_count,
                current_quantity=current_qty,
            )
        )

    return SparePartsReport(
        period=ReportPeriod(date_from=date_from, date_to=date_to),
        rows=rows,
        total_quantity=total_quantity,
        total_cost=total_cost,
    )


async def revenue_report(
    session: AsyncSession,
    date_from: date | None = None,
    date_to: date | None = None,
    group_by: str = "month",
) -> RevenueReport:
    """Отчёт по выручке — сумма по закрытым (выданным) заявкам.

    Выручка = стоимость работ + стоимость списанных запчастей по ценам
    на момент списания.
    """
    date_format = "YYYY-MM-DD" if group_by == "day" else "YYYY-MM"
    period_label = func.to_char(Request.closed_at, date_format).label("period")

    parts = _parts_cost_subquery()

    stmt = (
        select(
            period_label,
            func.count(Request.id).label("requests_count"),
            func.coalesce(func.sum(Request.work_cost), 0).label("work_cost"),
            func.coalesce(func.sum(func.coalesce(parts.c.parts_cost, 0)), 0).label("parts_cost"),
        )
        .outerjoin(parts, parts.c.request_id == Request.id)
        .where(
            and_(
                Request.status == RequestStatus.ISSUED,
                Request.closed_at.is_not(None),
            )
        )
        .group_by(period_label)
        .order_by(period_label)
    )
    stmt = _apply_period(stmt, Request.closed_at, date_from, date_to)

    rows: list[RevenuePeriodRow] = []
    total_requests = 0
    total_work = total_parts = ZERO

    for period, count, work_cost, parts_cost in (await session.execute(stmt)).all():
        work_cost = Decimal(work_cost or 0)
        parts_cost = Decimal(parts_cost or 0)
        total_requests += count
        total_work += work_cost
        total_parts += parts_cost
        rows.append(
            RevenuePeriodRow(
                period=period,
                requests_count=count,
                work_cost=work_cost,
                parts_cost=parts_cost,
                total=work_cost + parts_cost,
            )
        )

    total_revenue = total_work + total_parts
    average_check = (
        (total_revenue / total_requests).quantize(Decimal("0.01")) if total_requests else ZERO
    )

    return RevenueReport(
        period=ReportPeriod(date_from=date_from, date_to=date_to),
        group_by=group_by,
        rows=rows,
        requests_count=total_requests,
        total_work_cost=total_work,
        total_parts_cost=total_parts,
        total_revenue=total_revenue,
        average_check=average_check,
    )
