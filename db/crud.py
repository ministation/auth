from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import DiscordAuth


class LinkConflictError(Exception):
    """Raised when Discord ID or SS14 account is already bound to someone else."""


def is_linked(session: Session, user_id: uuid.UUID) -> bool:
    row = session.scalar(select(DiscordAuth).where(DiscordAuth.user_id == user_id).limit(1))
    return row is not None and row.discord_id is not None


def get_by_user_id(session: Session, user_id: uuid.UUID) -> DiscordAuth | None:
    return session.scalar(select(DiscordAuth).where(DiscordAuth.user_id == user_id).limit(1))


def get_by_discord_id(session: Session, discord_id: int) -> DiscordAuth | None:
    return session.scalar(select(DiscordAuth).where(DiscordAuth.discord_id == discord_id).limit(1))


def link_account(session: Session, user_id: uuid.UUID, discord_id: int) -> DiscordAuth:
    """
    Link Discord to SS14 user.

    Strict rule: one Discord ID <-> one SS14 account.
    Re-binding to a different account is rejected.
    """
    existing_user = get_by_user_id(session, user_id)
    existing_discord = get_by_discord_id(session, discord_id)

    if existing_user and existing_user.discord_id == discord_id:
        return existing_user

    if existing_discord is not None and existing_discord.user_id != user_id:
        raise LinkConflictError(
            "Этот Discord уже привязан к другому игровому аккаунту"
        )

    if existing_user is not None and existing_user.discord_id is not None and existing_user.discord_id != discord_id:
        raise LinkConflictError(
            "Этот игровой аккаунт уже привязан к другому Discord"
        )

    if existing_user is not None:
        existing_user.discord_id = discord_id
        session.flush()
        return existing_user

    row = DiscordAuth(user_id=user_id, discord_id=discord_id)
    session.add(row)
    session.flush()
    return row
