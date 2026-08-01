# Copyright (c) 2024–2026 Мини-станция (Mini-Station). All rights reserved.
# See LICENSE for terms.

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from settings import get_settings

_engines: dict[str, Engine] = {}
_session_makers: dict[str, sessionmaker[Session]] = {}
_db_order: list[str] = []


def init_db() -> None:
    global _engines, _session_makers, _db_order
    if _engines:
        return

    settings = get_settings()
    engines: dict[str, Engine] = {}
    makers: dict[str, sessionmaker[Session]] = {}
    order: list[str] = []

    for db in settings.databases:
        engine = create_engine(
            db.url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        engines[db.name] = engine
        makers[db.name] = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        order.append(db.name)

    _engines = engines
    _session_makers = makers
    _db_order = order


def database_names() -> list[str]:
    if not _db_order:
        init_db()
    return list(_db_order)


def primary_db_name() -> str:
    names = database_names()
    if not names:
        raise RuntimeError("No databases configured")
    return names[0]


@contextmanager
def get_session(db_name: str | None = None) -> Generator[Session, None, None]:
    if not _session_makers:
        init_db()
    name = db_name or primary_db_name()
    maker = _session_makers.get(name)
    if maker is None:
        raise KeyError(f"Unknown database: {name}")

    session = maker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
