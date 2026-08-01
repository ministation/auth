"""Application settings loaded from environment / .env."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        if default is not None:
            return default
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class DatabaseConfig:
    name: str
    host: str
    port: int
    database: str
    username: str
    password: str

    @property
    def url(self) -> str:
        user = quote_plus(self.username)
        password = quote_plus(self.password)
        return (
            f"postgresql+psycopg2://{user}:{password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


def _load_databases() -> list[DatabaseConfig]:
    """
    Discover DB1, DB2, ... from env.

    Required per DB:
      DB1_HOST, DB1_NAME, DB1_USER, DB1_PASSWORD
    Optional:
      DB1_PORT (default 5432)
    """
    indexes: set[int] = set()
    pattern = re.compile(r"^DB(\d+)_(HOST|NAME|USER|PASSWORD|PORT)$", re.IGNORECASE)
    for key in os.environ:
        match = pattern.match(key)
        if match:
            indexes.add(int(match.group(1)))

    if not indexes:
        raise RuntimeError(
            "No databases configured. Set DB1_HOST, DB1_NAME, DB1_USER, DB1_PASSWORD "
            "(and optionally DB2_*, DB3_*, ...)."
        )

    databases: list[DatabaseConfig] = []
    for index in sorted(indexes):
        prefix = f"DB{index}"
        host = os.getenv(f"{prefix}_HOST", "").strip()
        name = os.getenv(f"{prefix}_NAME", "").strip()
        user = os.getenv(f"{prefix}_USER", "").strip()
        password = os.getenv(f"{prefix}_PASSWORD", "")
        port_raw = os.getenv(f"{prefix}_PORT", "5432").strip() or "5432"

        missing = [
            f"{prefix}_{field}"
            for field, value in (("HOST", host), ("NAME", name), ("USER", user), ("PASSWORD", password))
            if not value and field != "PASSWORD"
        ]
        # password may be empty in local trust setups, but require the key exists
        if f"{prefix}_PASSWORD" not in os.environ:
            missing.append(f"{prefix}_PASSWORD")
        if missing:
            raise RuntimeError(f"Incomplete database config for {prefix}: missing {', '.join(missing)}")

        databases.append(
            DatabaseConfig(
                name=prefix,
                host=host,
                port=int(port_raw),
                database=name,
                username=user,
                password=password,
            )
        )
    return databases


@dataclass(frozen=True)
class Settings:
    bot_token: str
    api_key: str
    client_id: str
    client_secret: str
    redirect_uri: str
    guild_id: str
    auth_discord_role_id: str | None
    site_public_url: str
    site_login_path: str
    game_auth_secret: str
    require_guild: bool
    host: str
    port: int
    databases: list[DatabaseConfig]


def load_settings() -> Settings:
    role_raw = os.getenv("AUTH_DISCORD_ROLE_ID", "").strip()
    return Settings(
        bot_token=_env("BOT_TOKEN"),
        api_key=_env("API_KEY"),
        client_id=_env("CLIENT_ID"),
        client_secret=_env("CLIENT_SECRET"),
        redirect_uri=_env("REDIRECT_URI"),
        guild_id=os.getenv("GUILD_ID", "").strip(),
        auth_discord_role_id=role_raw or None,
        site_public_url=_env("SITE_PUBLIC_URL", "https://ministation.ru").rstrip("/"),
        site_login_path=_env("SITE_LOGIN_PATH", "/api/auth/game"),
        game_auth_secret=_env("GAME_AUTH_SECRET"),
        require_guild=_env_bool("REQUIRE_GUILD", True),
        host=_env("HOST", "0.0.0.0"),
        port=int(_env("PORT", "5001")),
        databases=_load_databases(),
    )
