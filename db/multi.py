"""Multi-database helpers for Discord auth linking."""

from __future__ import annotations

import logging
import uuid

from db import crud
from db.database import database_names, get_session
from db.crud import LinkConflictError

logger = logging.getLogger("discord_auth")


def is_linked_any(user_id: uuid.UUID) -> bool:
    """True if the SS14 account is linked in any configured database."""
    for name in database_names():
        with get_session(name) as session:
            if crud.is_linked(session, user_id):
                return True
    return False


def link_account_all(user_id: uuid.UUID, discord_id: int) -> None:
    """
    Write the same Discord <-> SS14 link into every configured database.

    First validates uniqueness across all DBs, then writes.
    """
    # Pre-check every DB for conflicts so we fail early before partial writes.
    for name in database_names():
        with get_session(name) as session:
            existing_discord = crud.get_by_discord_id(session, discord_id)
            if existing_discord is not None and existing_discord.user_id != user_id:
                raise LinkConflictError(
                    f"[{name}] Этот Discord уже привязан к другому игровому аккаунту"
                )
            existing_user = crud.get_by_user_id(session, user_id)
            if (
                existing_user is not None
                and existing_user.discord_id is not None
                and existing_user.discord_id != discord_id
            ):
                raise LinkConflictError(
                    f"[{name}] Этот игровой аккаунт уже привязан к другому Discord"
                )

    errors: list[str] = []
    for name in database_names():
        try:
            with get_session(name) as session:
                crud.link_account(session, user_id, discord_id)
            logger.info("Linked discord=%s user=%s in %s", discord_id, user_id, name)
        except LinkConflictError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to link in %s", name)
            errors.append(f"{name}: {exc}")

    if errors:
        raise RuntimeError("Не удалось записать привязку во все БД: " + "; ".join(errors))
