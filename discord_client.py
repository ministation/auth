# Copyright (c) 2024–2026 Мини-станция (Mini-Station). All rights reserved.
# See LICENSE for terms.

"""Shared Discord HTTP client helpers."""

from __future__ import annotations

import logging
from typing import Any, Sequence

import httpx

DISCORD_API = "https://discord.com/api/v10"
OAUTH_AUTHORIZE = "https://discord.com/api/oauth2/authorize"
OAUTH_TOKEN = "https://discord.com/api/oauth2/token"

logger = logging.getLogger(__name__)


class DiscordClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        bot_token: str,
        auth_roles: Sequence[tuple[str, str]] = (),
        # Back-compat: primary guild used when auth_roles empty
        guild_id: str = "",
        auth_role_id: str | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.bot_token = bot_token

        roles = [(g, r) for g, r in auth_roles if g and r]
        if not roles and guild_id and auth_role_id:
            roles = [(guild_id, auth_role_id)]
        self.auth_roles: list[tuple[str, str]] = roles
        self.guild_ids: list[str] = list(dict.fromkeys(g for g, _ in roles))
        if guild_id and guild_id not in self.guild_ids:
            self.guild_ids.insert(0, guild_id)
        # Primary guild (first configured) — used by older call sites / logs
        self.guild_id = self.guild_ids[0] if self.guild_ids else guild_id
        self.auth_role_id = roles[0][1] if roles else auth_role_id
        self._http: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=20.0)

    async def stop(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            raise RuntimeError("DiscordClient is not started")
        return self._http

    async def exchange_code(self, code: str) -> str:
        resp = await self.http.post(
            OAUTH_TOKEN,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise DiscordApiError("Не удалось обменять код авторизации Discord")
        token = resp.json().get("access_token")
        if not token:
            raise DiscordApiError("Discord не вернул access_token")
        return token

    async def fetch_user(self, access_token: str) -> dict[str, Any]:
        resp = await self.http.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code != 200:
            raise DiscordApiError("Не удалось получить профиль Discord")
        data = resp.json()
        if not str(data.get("id", "")).isdigit():
            raise DiscordApiError("Некорректный ответ Discord user")
        return data

    async def fetch_guilds(self, access_token: str) -> list[dict[str, Any]]:
        resp = await self.http.get(
            f"{DISCORD_API}/users/@me/guilds",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code != 200:
            raise DiscordApiError("Не удалось получить список серверов Discord")
        data = resp.json()
        return data if isinstance(data, list) else []

    async def is_guild_member(self, discord_id: str, guild_id: str | None = None) -> bool | None:
        """True/False if known, None if bot check unavailable."""
        target = guild_id or self.guild_id
        if not target or not self.bot_token:
            return None
        resp = await self.http.get(
            f"{DISCORD_API}/guilds/{target}/members/{discord_id}",
            headers={"Authorization": f"Bot {self.bot_token}"},
        )
        if resp.status_code == 200:
            return True
        if resp.status_code == 404:
            return False
        raise DiscordApiError("Ошибка проверки участия в Discord-сервере")

    async def is_member_of_any(self, discord_id: str, guild_ids: Sequence[str]) -> bool | None:
        """True if member of any guild; False if checked and nowhere; None if unverifiable."""
        saw_false = False
        for gid in guild_ids:
            result = await self.is_guild_member(discord_id, gid)
            if result is True:
                return True
            if result is False:
                saw_false = True
        if saw_false:
            return False
        return None

    async def assign_auth_role(self, discord_id: str) -> None:
        """Assign auth role on every configured guild. Failures are logged, not raised."""
        if not self.bot_token or not self.auth_roles:
            return
        headers = {"Authorization": f"Bot {self.bot_token}"}
        for guild_id, role_id in self.auth_roles:
            url = f"{DISCORD_API}/guilds/{guild_id}/members/{discord_id}/roles/{role_id}"
            try:
                resp = await self.http.put(url, headers=headers)
                if resp.status_code in (200, 204):
                    logger.info(
                        "Assigned auth role %s to %s on guild %s",
                        role_id,
                        discord_id,
                        guild_id,
                    )
                elif resp.status_code == 404:
                    logger.warning(
                        "Cannot assign role %s on guild %s for %s: member not found "
                        "(user not on server, or bot missing)",
                        role_id,
                        guild_id,
                        discord_id,
                    )
                else:
                    logger.warning(
                        "Failed to assign role %s on guild %s for %s: HTTP %s %s",
                        role_id,
                        guild_id,
                        discord_id,
                        resp.status_code,
                        resp.text[:200],
                    )
            except Exception:
                logger.exception(
                    "Error assigning role %s on guild %s for %s",
                    role_id,
                    guild_id,
                    discord_id,
                )


class DiscordApiError(Exception):
    pass
