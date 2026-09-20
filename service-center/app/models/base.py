"""Базовый класс декларативных моделей и общие миксины.

ВЫБОР ТИПА ПЕРВИЧНОГО КЛЮЧА (требование п.5)
--------------------------------------------
Используется автоинкрементный BIGINT (BIGSERIAL), а не UUID. Обоснование:

1. Сервисный центр — система с одним экземпляром БД, распределённой генерации
   идентификаторов на клиенте не требуется, т.е. главное преимущество UUID
   здесь не востребовано.
2. B-tree индекс по возрастающему BIGINT компактнее и не вызывает случайных
   вставок в середину страниц (проблема random UUIDv4), что важно для таблицы
   заявок и истории статусов — самых растущих таблиц системы.
3. Короткий числовой id удобен в поддержке: оператор может продиктовать его
   по телефону, он читаем в логах и URL.
4. Публичным (внешним) идентификатором заявки всё равно служит человекочитаемый
   номер формата SC-YYYY-NNNN, поэтому «угадываемость» последовательных id
   не раскрывает бизнес-информации напрямую.
"""

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def enum_column(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    """Создаёт нативный PostgreSQL ENUM, хранящий *значения* (а не имена) членов.

    По умолчанию SQLAlchemy пишет в БД имена членов (``ADMIN``), что неудобно
    при работе с данными напрямую. ``values_callable`` заставляет хранить
    значения (``admin``) — те же, что уходят в JSON.
    """
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda obj: [member.value for member in obj],
        native_enum=True,
    )


class Base(DeclarativeBase):
    """Общий декларативный базовый класс для всех моделей."""


class IdMixin:
    """Суррогатный первичный ключ."""

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)


class TimestampMixin:
    """Служебные отметки времени создания и последнего изменения записи."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
