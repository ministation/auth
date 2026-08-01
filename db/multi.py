# Copyright (c) 2024–2026 Мини-станция (Mini-Station). All rights reserved.
# See LICENSE for terms.

"""Multi-database helpers for Discord auth linking."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import text

from db import crud
from db.crud import LinkConflictError
from db.database import database_names, get_session

logger = logging.getLogger("discord_auth")


def is_linked_any(user_id: uuid.UUID) -> bool:
    """True if the SS14 account is linked in any healthy configured database."""
    saw_success = False
    last_error: Exception | None = None

    for name in database_names():
        try:
            with get_session(name) as session:
                saw_success = True
                if crud.is_linked(session, user_id):
                    return True
        except Exception as exc:  # noqa: BLE001
            logger.exception("is_linked check failed for %s", name)
            last_error = exc

    if not saw_success and last_error is not None:
        raise last_error
    return False


def ping_databases() -> dict[str, bool]:
    """Return connectivity map for configured databases."""
    result: dict[str, bool] = {}
    for name in database_names():
        try:
            with get_session(name) as session:
                session.execute(text("SELECT 1"))
            result[name] = True
        except Exception:  # noqa: BLE001
            logger.exception("DB ping failed for %s", name)
            result[name] = False
    return result


def link_account_all(user_id: uuid.UUID, discord_id: int) -> list[str]:
    """
    Write the same Discord <-> SS14 link into every configured database.

    Returns list of DB names that were updated.
    """
    names = database_names()
    if not names:
        raise RuntimeError("No databases configured")

    for name in names:
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

    linked: list[str] = []
    errors: list[str] = []
    for name in names:
        try:
            with get_session(name) as session:
                crud.link_account(session, user_id, discord_id)
            linked.append(name)
            logger.info("Linked discord=%s user=%s in %s", discord_id, user_id, name)
        except LinkConflictError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to link in %s", name)
            errors.append(f"{name}: {exc}")

    if not linked:
        raise RuntimeError("Не удалось записать привязку ни в одну БД: " + "; ".join(errors))
    if errors:
        logger.error("Partial multi-DB link for user=%s: ok=%s errors=%s", user_id, linked, errors)
    return linked
