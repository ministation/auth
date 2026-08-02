# Copyright (c) 2024–2026 Мини-станция (Mini-Station). All rights reserved.
# See LICENSE for terms.

"""Discord Gateway presence: показывает онлайн SS14 в статусе auth-бота."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord
import httpx

from settings import Settings

logger = logging.getLogger(__name__)


async def fetch_ss14_online(status_url: str) -> tuple[int, int | None]:
    """GET /status → (players, soft_max_players)."""
    async with httpx.AsyncClient(timeout=10.0) as http:
        resp = await http.get(status_url)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise RuntimeError("Invalid /status JSON")
        players = int(data.get("players", 0))
        soft_max = data.get("soft_max_players")
        if soft_max is not None:
            soft_max = int(soft_max)
        return players, soft_max


def format_online(players: int, soft_max: int | None) -> str:
    if soft_max and soft_max > 0:
        return f"Онлайн: {players}/{soft_max}"
    return f"Онлайн: {players}"


class PresenceBot:
    """Лёгкий discord.Client только для presence (тот же BOT_TOKEN)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: discord.Client | None = None
        self._start_task: asyncio.Task[Any] | None = None
        self._loop_task: asyncio.Task[Any] | None = None
        self._stop = asyncio.Event()
        self._last_text: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.ss14_status_url)

    async def start(self) -> None:
        if not self.enabled:
            logger.info("SS14_STATUS_URL не задан — Discord presence отключён")
            return

        intents = discord.Intents.none()
        # Минимальные intents для подключения к Gateway
        intents.guilds = True
        client = discord.Client(intents=intents)
        self._client = client
        self._stop.clear()

        @client.event
        async def on_ready() -> None:
            logger.info(
                "Presence bot online as %s; status from %s every %ss",
                client.user,
                self.settings.ss14_status_url,
                self.settings.status_update_interval,
            )
            if self._loop_task is None or self._loop_task.done():
                self._loop_task = asyncio.create_task(
                    self._update_loop(), name="ss14-presence-loop"
                )

        self._start_task = asyncio.create_task(
            client.start(self.settings.bot_token),
            name="ss14-presence-gateway",
        )

        def _on_gateway_done(task: asyncio.Task[Any]) -> None:
            try:
                exc = task.exception()
            except asyncio.CancelledError:
                return
            if exc:
                logger.error("Presence gateway stopped: %s", exc)

        self._start_task.add_done_callback(_on_gateway_done)

    async def stop(self) -> None:
        self._stop.set()
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        self._loop_task = None

        if self._client is not None and not self._client.is_closed():
            await self._client.close()
        self._client = None

        if self._start_task and not self._start_task.done():
            self._start_task.cancel()
            try:
                await self._start_task
            except (asyncio.CancelledError, Exception):
                pass
        self._start_task = None

    async def _update_loop(self) -> None:
        assert self._client is not None
        while not self._stop.is_set():
            try:
                await self._update_once()
            except Exception:
                logger.exception("Failed to update SS14 presence")
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.settings.status_update_interval,
                )
                break
            except asyncio.TimeoutError:
                continue

    async def _update_once(self) -> None:
        client = self._client
        if client is None or not client.is_ready():
            return

        url = self.settings.ss14_status_url
        assert url
        try:
            players, soft_max = await fetch_ss14_online(url)
            text = format_online(players, soft_max)
            status = discord.Status.online
        except Exception as exc:
            logger.warning("SS14 /status unreachable (%s): %s", url, exc)
            text = "Сервер недоступен"
            status = discord.Status.idle

        await client.change_presence(
            status=status,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=text,
            ),
        )
        if text != self._last_text:
            logger.info("Presence → %s", text)
            self._last_text = text
