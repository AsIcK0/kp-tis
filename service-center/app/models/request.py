"""Модели заявки на ремонт и истории её изменений."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin, enum_column
from app.models.enums import HistoryEventType, RequestPriority, RequestStatus

if TYPE_CHECKING:  # pragma: no cover
    from app.models.client import Client, Device
    from app.models.spare_part import SparePartUsage
    from app.models.user import User


class Request(IdMixin, TimestampMixin, Base):
    """Заявка на ремонт техники."""

    __tablename__ = "requests"
    __table_args__ = (
        # Составной индекс под самый частый сценарий выборки:
        # «активные заявки конкретного мастера».
        Index("ix_requests_master_status", "master_id", "status"),
        Index("ix_requests_status_created", "status", "created_at"),
    )

    # Человекочитаемый номер формата SC-YYYY-NNNN (Функция 7).
    number: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)

    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    device_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Менеджер, создавший заявку.
    manager_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Назначенный мастер; до назначения — NULL.
    master_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[RequestStatus] = mapped_column(
        enum_column(RequestStatus, "request_status"),
        nullable=False,
        default=RequestStatus.ACCEPTED,
        index=True,
    )
    priority: Mapped[RequestPriority] = mapped_column(
        enum_column(RequestPriority, "request_priority"),
        nullable=False,
        default=RequestPriority.MEDIUM,
        index=True,
    )

    description: Mapped[str] = mapped_column(Text, nullable=False)  # problem_description
    # Поля, заполняемые мастером в ходе выполнения работ.
    diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Стоимость работ. Numeric, а не float — деньги нельзя хранить в плавающей точке.
    work_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )

    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    client: Mapped["Client"] = relationship(back_populates="requests", lazy="selectin")
    device: Mapped["Device"] = relationship(back_populates="requests", lazy="selectin")
    manager: Mapped["User"] = relationship(
        back_populates="managed_requests", foreign_keys=[manager_id], lazy="selectin"
    )
    master: Mapped["User | None"] = relationship(
        back_populates="assigned_requests", foreign_keys=[master_id], lazy="selectin"
    )
    history: Mapped[list["StatusHistory"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="StatusHistory.created_at",
        lazy="raise",
    )
    spare_part_usages: Mapped[list["SparePartUsage"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        lazy="raise",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Request {self.number} status={self.status.value}>"


class StatusHistory(IdMixin, TimestampMixin, Base):
    """Журнал изменений заявки.

    Хранит не только смену статуса, но и назначение мастера и комментарии —
    это даёт единую хронологическую ленту событий для Функции 12.
    """

    __tablename__ = "status_history"

    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[HistoryEventType] = mapped_column(
        enum_column(HistoryEventType, "history_event_type"),
        nullable=False,
        default=HistoryEventType.STATUS_CHANGE,
    )
    old_status: Mapped[RequestStatus | None] = mapped_column(
        enum_column(RequestStatus, "request_status"), nullable=True
    )
    new_status: Mapped[RequestStatus | None] = mapped_column(
        enum_column(RequestStatus, "request_status"), nullable=True
    )
    changed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    request: Mapped["Request"] = relationship(back_populates="history", lazy="raise")
    author: Mapped["User | None"] = relationship(lazy="selectin")

    @property
    def changed_at(self) -> datetime:
        """Псевдоним ``created_at`` — имя поля из модели данных ТЗ (раздел 5)."""
        return self.created_at

    def __repr__(self) -> str:  # pragma: no cover
        return f"<StatusHistory request_id={self.request_id} event={self.event_type.value}>"
