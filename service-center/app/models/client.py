"""Модели клиента и его устройств."""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.request import Request


class Client(IdMixin, TimestampMixin, Base):
    """Клиент сервисного центра (физическое или юридическое лицо)."""

    __tablename__ = "clients"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Телефон нормализуется до формата +7XXXXXXXXXX и служит ключом
    # для проверки дублирования (Функция 5).
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    devices: Mapped[list["Device"]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    requests: Mapped[list["Request"]] = relationship(back_populates="client", lazy="raise")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Client id={self.id} full_name={self.full_name!r}>"


class Device(IdMixin, TimestampMixin, Base):
    """Устройство, принадлежащее клиенту и сдаваемое в ремонт."""

    __tablename__ = "devices"

    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_type: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(150), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    client: Mapped["Client"] = relationship(back_populates="devices", lazy="joined")
    requests: Mapped[list["Request"]] = relationship(back_populates="device", lazy="raise")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Device id={self.id} model={self.model!r} sn={self.serial_number!r}>"
