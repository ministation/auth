from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DiscordAuth(Base):
    """Maps SS14 player UUID <-> Discord snowflake (table discord_auth)."""

    __tablename__ = "discord_auth"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
