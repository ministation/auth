# Copyright (c) 2024–2026 Мини-станция (Mini-Station). All rights reserved.
# See LICENSE for terms.

"""Shared Discord HTTP client helpers."""

from __future__ import annotations

from typing import Any

import httpx

DISCORD_API = "https://discord.com/api/v10"
OAUTH_AUTHORIZE = "https://discord.com/api/oauth2/authorize"
OAUTH_TOKEN = "https://discord.com/api/oauth2/token"


class DiscordClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        bot_token: str,
        guild_id: str,
        auth_role_id: str | None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.bot_token = bot_token
        self.guild_id = guild_id
        self.auth_role_id = auth_role_id
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

    async def is_guild_member(self, discord_id: str) -> bool | None:
        """True/False if known, None if bot check unavailable."""
        if not self.guild_id or not self.bot_token:
            return None
        resp = await self.http.get(
            f"{DISCORD_API}/guilds/{self.guild_id}/members/{discord_id}",
            headers={"Authorization": f"Bot {self.bot_token}"},
        )
        if resp.status_code == 200:
            return True
        if resp.status_code == 404:
            return False
        raise DiscordApiError("Ошибка проверки участия в Discord-сервере")

    async def assign_auth_role(self, discord_id: str) -> None:
        if not self.guild_id or not self.bot_token or not self.auth_role_id:
            return
        await self.http.put(
            f"{DISCORD_API}/guilds/{self.guild_id}/members/{discord_id}/roles/{self.auth_role_id}",
            headers={"Authorization": f"Bot {self.bot_token}"},
        )


class DiscordApiError(Exception):
    pass
