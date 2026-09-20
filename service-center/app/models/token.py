"""Хранилище выданных refresh-токенов.

JWT сам по себе не отзывается: чтобы реализовать Функцию 3 («Выход из аккаунта»),
сервер хранит идентификаторы (jti) выданных refresh-токенов и помечает их
отозванными. Access-токен короткоживущий (30 минут), поэтому его отзыв
не требуется.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.user import User


class RefreshToken(IdMixin, TimestampMixin, Base):
    """Выданный refresh-токен."""

    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped["User"] = relationship(lazy="raise")

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RefreshToken user_id={self.user_id} revoked={self.is_revoked}>"
