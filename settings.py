# Copyright (c) 2024–2026 Мини-станция (Mini-Station). All rights reserved.
# See LICENSE for terms.

"""Application settings loaded from environment / .env."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

_DB_KEY_RE = re.compile(r"^DB(\d+)_(HOST|NAME|USER|PASSWORD|PORT)$", re.IGNORECASE)


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        if default is not None:
            return default
        raise RuntimeError(f"Missing required env var: {name}")
    return value.strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _require_min_len(name: str, value: str, minimum: int) -> str:
    if len(value) < minimum:
        raise RuntimeError(f"{name} must be at least {minimum} characters")
    return value


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
    indexes = {
        int(match.group(1))
        for key in os.environ
        if (match := _DB_KEY_RE.match(key))
    }
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
        port_raw = (os.getenv(f"{prefix}_PORT") or "5432").strip()

        missing = [
            f"{prefix}_{field}"
            for field, value in (("HOST", host), ("NAME", name), ("USER", user))
            if not value
        ]
        if f"{prefix}_PASSWORD" not in os.environ:
            missing.append(f"{prefix}_PASSWORD")
        if missing:
            raise RuntimeError(f"Incomplete database config for {prefix}: missing {', '.join(missing)}")

        try:
            port = int(port_raw)
        except ValueError as exc:
            raise RuntimeError(f"{prefix}_PORT must be an integer") from exc

        databases.append(
            DatabaseConfig(
                name=prefix,
                host=host,
                port=port,
                database=name,
                username=user,
                password=password,
            )
        )
    return databases


@dataclass(frozen=True)
class GuildRoleTarget:
    """Discord guild + auth role to assign after successful SS14 / site login."""

    guild_id: str
    role_id: str
    bot_token: str = ""  # empty → use Settings.bot_token


def _parse_snowflake_pairs(raw: str) -> list[tuple[str, str]]:
    """Parse 'guild:role,guild:role' or whitespace-separated pairs."""
    pairs: list[tuple[str, str]] = []
    for chunk in re.split(r"[\s,;]+", raw.strip()):
        if not chunk:
            continue
        if ":" not in chunk:
            raise RuntimeError(
                "AUTH_DISCORD_ROLES entries must look like guildId:roleId "
                f"(got {chunk!r})"
            )
        guild_id, role_id = chunk.split(":", 1)
        guild_id, role_id = guild_id.strip(), role_id.strip()
        if not guild_id.isdigit() or not role_id.isdigit():
            raise RuntimeError(
                f"AUTH_DISCORD_ROLES entry must be numeric snowflakes (got {chunk!r})"
            )
        pairs.append((guild_id, role_id))
    return pairs


def _guild_bot_token(index: int | None, guild_id: str, default_token: str) -> str:
    """Optional per-guild bot: GUILD2_BOT_TOKEN / GUILD{N}_BOT_TOKEN / BOT_TOKEN_<guildId>."""
    if index is not None:
        if index >= 2:
            specific = os.getenv(f"GUILD{index}_BOT_TOKEN", "").strip()
            if specific:
                return specific
        elif index == 1:
            specific = os.getenv("GUILD_BOT_TOKEN", "").strip() or os.getenv("GUILD1_BOT_TOKEN", "").strip()
            if specific:
                return specific
    by_id = os.getenv(f"BOT_TOKEN_{guild_id}", "").strip()
    if by_id:
        return by_id
    return default_token


def _load_auth_roles(*, default_bot_token: str) -> list[GuildRoleTarget]:
    """
    Role targets on one or more Discord servers.

    Preferred:
      AUTH_DISCORD_ROLES=guild1:role1,guild2:role2

    Also accepted:
      GUILD_ID + AUTH_DISCORD_ROLE_ID
      GUILD2_ID + AUTH_DISCORD_ROLE_ID_2
      GUILD2_BOT_TOKEN — bot that can Manage Roles on the second guild
    """
    seen: set[tuple[str, str]] = set()
    targets: list[GuildRoleTarget] = []

    def add(guild_id: str, role_id: str, *, index: int | None = None) -> None:
        guild_id, role_id = guild_id.strip(), role_id.strip()
        if not guild_id or not role_id:
            return
        key = (guild_id, role_id)
        if key in seen:
            return
        if not guild_id.isdigit() or not role_id.isdigit():
            raise RuntimeError(f"Invalid guild/role snowflake: {guild_id}/{role_id}")
        seen.add(key)
        token = _guild_bot_token(index, guild_id, default_bot_token)
        targets.append(
            GuildRoleTarget(guild_id=guild_id, role_id=role_id, bot_token=token)
        )

    roles_raw = os.getenv("AUTH_DISCORD_ROLES", "").strip()
    if roles_raw:
        for i, (guild_id, role_id) in enumerate(_parse_snowflake_pairs(roles_raw), start=1):
            add(guild_id, role_id, index=i)

    add(os.getenv("GUILD_ID", ""), os.getenv("AUTH_DISCORD_ROLE_ID", ""), index=1)
    add(os.getenv("GUILD2_ID", ""), os.getenv("AUTH_DISCORD_ROLE_ID_2", ""), index=2)

    for key in list(os.environ):
        match = re.match(r"^GUILD(\d+)_ID$", key, re.IGNORECASE)
        if not match:
            continue
        n = int(match.group(1))
        if n < 3:
            continue
        add(os.getenv(key, ""), os.getenv(f"AUTH_DISCORD_ROLE_ID_{n}", ""), index=n)

    return targets

@dataclass(frozen=True)
class Settings:
    bot_token: str
    api_key: str
    client_id: str
    client_secret: str
    redirect_uri: str
    guild_id: str
    auth_discord_role_id: str | None
    auth_roles: list[GuildRoleTarget]
    required_guild_ids: list[str]
    site_public_url: str
    site_login_path: str
    game_auth_secret: str
    require_guild: bool
    host: str
    port: int
    databases: list[DatabaseConfig]
    rate_limit_login: int
    rate_limit_callback: int
    disable_docs: bool
    require_check_api_key: bool
    show_success_page: bool
    trust_proxy: bool
    forwarded_allow_ips: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    site_login_path = _env("SITE_LOGIN_PATH", "/api/auth/game")
    if not site_login_path.startswith("/"):
        raise RuntimeError("SITE_LOGIN_PATH must start with '/'")

    redirect_uri = _env("REDIRECT_URI")
    if not (
        redirect_uri.startswith("https://")
        or redirect_uri.startswith("http://localhost")
        or redirect_uri.startswith("http://127.0.0.1")
        or redirect_uri.startswith("http://")  # allow LAN IPs for self-hosted game auth
    ):
        raise RuntimeError("REDIRECT_URI must be an http(s) URL")

    bot_token = _env("BOT_TOKEN")
    auth_roles = _load_auth_roles(default_bot_token=bot_token)
    guild_id = os.getenv("GUILD_ID", "").strip()
    if not guild_id and auth_roles:
        guild_id = auth_roles[0].guild_id
    role_id = os.getenv("AUTH_DISCORD_ROLE_ID", "").strip() or None
    if role_id is None and auth_roles:
        role_id = auth_roles[0].role_id

    # Membership gate defaults to primary Mini guild only (not every role target).
    required_guild_ids = [guild_id] if guild_id else []
    require_raw = os.getenv("REQUIRE_GUILD_IDS", "").strip()
    if require_raw:
        required_guild_ids = [
            g.strip() for g in re.split(r"[\s,;]+", require_raw) if g.strip().isdigit()
        ]
    elif not required_guild_ids and auth_roles:
        required_guild_ids = [auth_roles[0].guild_id]

    return Settings(
        bot_token=bot_token,
        api_key=_require_min_len("API_KEY", _env("API_KEY"), 8),
        client_id=_env("CLIENT_ID"),
        client_secret=_env("CLIENT_SECRET"),
        redirect_uri=redirect_uri,
        guild_id=guild_id,
        auth_discord_role_id=role_id,
        auth_roles=auth_roles,
        required_guild_ids=required_guild_ids,
        site_public_url=_env("SITE_PUBLIC_URL", "https://ministation.ru").rstrip("/"),
        site_login_path=site_login_path,
        game_auth_secret=_require_min_len("GAME_AUTH_SECRET", _env("GAME_AUTH_SECRET"), 24),
        require_guild=_env_bool("REQUIRE_GUILD", True),
        host=_env("HOST", "0.0.0.0"),
        port=int(_env("PORT", "5001")),
        databases=_load_databases(),
        rate_limit_login=int(_env("RATE_LIMIT_LOGIN", "30")),
        rate_limit_callback=int(_env("RATE_LIMIT_CALLBACK", "60")),
        disable_docs=_env_bool("DISABLE_DOCS", False),
        require_check_api_key=_env_bool("REQUIRE_CHECK_API_KEY", False),
        show_success_page=_env_bool("SHOW_SUCCESS_PAGE", True),
        trust_proxy=_env_bool("TRUST_PROXY", True),
        forwarded_allow_ips=_env("FORWARDED_ALLOW_IPS", "*"),
    )


# Backwards-compatible alias
def load_settings() -> Settings:
    return get_settings()
