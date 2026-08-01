# Copyright (c) 2024–2026 Мини-станция (Mini-Station). All rights reserved.
# See LICENSE for terms.

"""Shared Discord HTTP client helpers."""

from __future__ import annotations

import asyncio
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
        auth_roles: Sequence[tuple[str, str, str]] | Sequence[tuple[str, str]] = (),
        # Back-compat: primary guild used when auth_roles empty
        guild_id: str = "",
        auth_role_id: str | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.bot_token = bot_token

        roles: list[tuple[str, str, str]] = []
        for item in auth_roles:
            if len(item) == 3:
                g, r, t = item  # type: ignore[misc]
                roles.append((str(g), str(r), str(t or bot_token)))
            elif len(item) == 2:
                g, r = item  # type: ignore[misc]
                roles.append((str(g), str(r), bot_token))
        if not roles and guild_id and auth_role_id:
            roles = [(guild_id, auth_role_id, bot_token)]
        self.auth_roles: list[tuple[str, str, str]] = [
            (g, r, t) for g, r, t in roles if g and r and t
        ]
        self.guild_ids: list[str] = list(dict.fromkeys(g for g, _, _ in self.auth_roles))
        if guild_id and guild_id not in self.guild_ids:
            self.guild_ids.insert(0, guild_id)
        self.guild_id = self.guild_ids[0] if self.guild_ids else guild_id
        self.auth_role_id = self.auth_roles[0][1] if self.auth_roles else auth_role_id
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
        token = self._token_for_guild(target)
        if not target or not token:
            return None
        resp = await self.http.get(
            f"{DISCORD_API}/guilds/{target}/members/{discord_id}",
            headers={"Authorization": f"Bot {token}"},
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

    def _token_for_guild(self, guild_id: str) -> str:
        for g, _r, token in self.auth_roles:
            if g == guild_id and token:
                return token
        return self.bot_token

    async def assign_auth_role(
        self,
        discord_id: str,
        *,
        only_guild_ids: Sequence[str] | None = None,
        quiet_not_member: bool = False,
        max_retries: int = 6,
    ) -> dict[str, str]:
        """
        Assign auth role on configured guilds.

        Returns map guild_id -> status (ok / not_member / skip / http_NNN / error).
        Failures are logged, not raised. HTTP 429 is retried using retry_after.
        """
        results: dict[str, str] = {}
        if not self.auth_roles:
            return results
        allow = set(only_guild_ids) if only_guild_ids else None
        for guild_id, role_id, token in self.auth_roles:
            if allow is not None and guild_id not in allow:
                continue
            if not token:
                results[guild_id] = "skip_no_token"
                continue
            url = f"{DISCORD_API}/guilds/{guild_id}/members/{discord_id}/roles/{role_id}"
            headers = {"Authorization": f"Bot {token}"}
            status = "error"
            try:
                for attempt in range(max_retries + 1):
                    resp = await self.http.put(url, headers=headers)
                    if resp.status_code in (200, 204):
                        status = "ok"
                        logger.info(
                            "Assigned auth role %s to %s on guild %s",
                            role_id,
                            discord_id,
                            guild_id,
                        )
                        break
                    if resp.status_code == 404:
                        status = "not_member"
                        log = logger.debug if quiet_not_member else logger.info
                        log(
                            "Skip role %s on guild %s for %s: not a guild member",
                            role_id,
                            guild_id,
                            discord_id,
                        )
                        break
                    if resp.status_code == 429 and attempt < max_retries:
                        retry_after = 1.0
                        try:
                            retry_after = float(resp.json().get("retry_after", 1.0))
                        except Exception:
                            retry_after = float(resp.headers.get("Retry-After", "1") or 1)
                        wait = max(0.25, retry_after) + 0.15
                        logger.warning(
                            "Rate limited assigning role on guild %s; sleep %.1fs (attempt %s)",
                            guild_id,
                            wait,
                            attempt + 1,
                        )
                        await asyncio.sleep(wait)
                        continue
                    status = f"http_{resp.status_code}"
                    logger.warning(
                        "Failed to assign role %s on guild %s for %s: HTTP %s %s",
                        role_id,
                        guild_id,
                        discord_id,
                        resp.status_code,
                        resp.text[:200],
                    )
                    break
            except Exception:
                status = "error"
                logger.exception(
                    "Error assigning role %s on guild %s for %s",
                    role_id,
                    guild_id,
                    discord_id,
                )
            results[guild_id] = status
        return results


class DiscordApiError(Exception):
    pass
