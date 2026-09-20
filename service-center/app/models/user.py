"""Модель пользователя системы."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin, enum_column
from app.models.enums import UserRole

if TYPE_CHECKING:  # pragma: no cover
    from app.models.request import Request


class User(IdMixin, TimestampMixin, Base):
    """Учётная запись сотрудника сервисного центра."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # Пароль хранится ТОЛЬКО в виде bcrypt-хеша (требование 4.3).
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        enum_column(UserRole, "user_role"), nullable=False, index=True
    )
    # «Удаление» пользователя — это деактивация: связанные заявки должны
    # сохранить ссылку на автора.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    managed_requests: Mapped[list["Request"]] = relationship(
        back_populates="manager",
        foreign_keys="Request.manager_id",
        lazy="raise",
    )
    assigned_requests: Mapped[list["Request"]] = relationship(
        back_populates="master",
        foreign_keys="Request.master_id",
        lazy="raise",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} username={self.username!r} role={self.role.value}>"
