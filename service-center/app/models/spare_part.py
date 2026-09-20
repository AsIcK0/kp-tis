"""Модели складского учёта: номенклатура запчастей и их списание."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.request import Request
    from app.models.user import User


class SparePart(IdMixin, TimestampMixin, Base):
    """Позиция номенклатуры склада (Функция 13)."""

    __tablename__ = "spare_parts"
    __table_args__ = (
        # Отрицательный остаток невозможен даже при ошибке в коде сервиса.
        CheckConstraint("quantity >= 0", name="ck_spare_parts_quantity_non_negative"),
        CheckConstraint("min_quantity >= 0", name="ck_spare_parts_min_quantity_non_negative"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    article: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    supplier: Mapped[str | None] = mapped_column(String(255), nullable=True)

    usages: Mapped[list["SparePartUsage"]] = relationship(
        back_populates="spare_part", lazy="raise"
    )

    @property
    def is_low_stock(self) -> bool:
        """Признак того, что остаток опустился ниже минимального."""
        return self.quantity <= self.min_quantity

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SparePart {self.article} qty={self.quantity}>"


class SparePartUsage(IdMixin, TimestampMixin, Base):
    """Факт списания запчасти на заявку (Функция 14)."""

    __tablename__ = "spare_part_usages"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_usage_quantity_positive"),
    )

    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    spare_part_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    # Цена фиксируется на момент списания: последующее изменение прайса
    # не должно менять уже сформированную выручку по закрытым заявкам.
    price_at_use: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    used_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    request: Mapped["Request"] = relationship(back_populates="spare_part_usages", lazy="raise")
    spare_part: Mapped["SparePart"] = relationship(back_populates="usages", lazy="selectin")
    author: Mapped["User | None"] = relationship(lazy="selectin")

    @property
    def total_cost(self) -> Decimal:
        """Стоимость списанной позиции."""
        return self.price_at_use * self.quantity

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SparePartUsage request_id={self.request_id} qty={self.quantity}>"
