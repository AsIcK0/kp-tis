"""Pydantic-схемы модуля отчётности (Функция 15).

Отчёты не хранятся в БД — они формируются на лету агрегирующими запросами
(раздел 5 ТЗ: сущность Report не материализуется).
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import RequestStatus


class ReportPeriod(BaseModel):
    """Период, за который построен отчёт."""

    date_from: date | None = None
    date_to: date | None = None


class WorksReportRow(BaseModel):
    """Строка отчёта по выполненным работам."""

    request_id: int
    number: str
    client_name: str
    device: str
    master: str | None
    status: RequestStatus
    created_at: datetime
    closed_at: datetime | None
    work_cost: Decimal
    parts_cost: Decimal
    total_cost: Decimal


class WorksReport(BaseModel):
    """Отчёт по выполненным работам за период с фильтром по мастеру."""

    period: ReportPeriod
    master_id: int | None = None
    rows: list[WorksReportRow] = Field(default_factory=list)
    requests_count: int = 0
    total_work_cost: Decimal = Decimal("0.00")
    total_parts_cost: Decimal = Decimal("0.00")
    total_cost: Decimal = Decimal("0.00")


class SparePartsReportRow(BaseModel):
    """Строка отчёта по использованным запчастям."""

    spare_part_id: int
    name: str
    article: str
    total_quantity: int
    total_cost: Decimal
    requests_count: int
    current_quantity: int


class SparePartsReport(BaseModel):
    """Отчёт по использованным запчастям за период."""

    period: ReportPeriod
    rows: list[SparePartsReportRow] = Field(default_factory=list)
    total_quantity: int = 0
    total_cost: Decimal = Decimal("0.00")


class RevenuePeriodRow(BaseModel):
    """Выручка в разрезе периода (месяц или день)."""

    period: str
    requests_count: int
    work_cost: Decimal
    parts_cost: Decimal
    total: Decimal


class RevenueReport(BaseModel):
    """Отчёт по выручке — сумма по закрытым (выданным) заявкам."""

    period: ReportPeriod
    group_by: str = Field(default="month", description="day | month")
    rows: list[RevenuePeriodRow] = Field(default_factory=list)
    requests_count: int = 0
    total_work_cost: Decimal = Decimal("0.00")
    total_parts_cost: Decimal = Decimal("0.00")
    total_revenue: Decimal = Decimal("0.00")
    average_check: Decimal = Decimal("0.00")
