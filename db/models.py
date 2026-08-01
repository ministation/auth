# Copyright (c) 2024–2026 Мини-станция (Mini-Station). All rights reserved.
# See LICENSE for terms.

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DiscordAuth(Base):
    """Maps SS14 player UUID <-> Discord snowflake (table discord_auth)."""

    __tablename__ = "discord_auth"
    __table_args__ = (
        # Declared for documentation / create_all; production DB may rely on app checks + triggers.
        UniqueConstraint("user_id", name="uq_discord_auth_user_id"),
        UniqueConstraint("discord_id", name="uq_discord_auth_discord_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
