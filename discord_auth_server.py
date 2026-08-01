# Copyright (c) 2024–2026 Мини-станция (Mini-Station). All rights reserved.
# See LICENSE for terms.

"""SS14 Discord auth service (Corvax-compatible API) with ministation.ru handoff."""

from __future__ import annotations

import base64
import io
import logging
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlencode

import segno
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from db import init_db
from db.crud import LinkConflictError
from db.multi import is_linked_any, link_account_all, ping_databases
from discord_client import DiscordApiError, DiscordClient, OAUTH_AUTHORIZE
from middleware import SecurityHeadersMiddleware
from pages import error_page, success_page
from rate_limit import limiter
from schemas import AuthInfoResponse, HealthResponse, LinkResponse
from security import (
    api_key_valid,
    create_oauth_state,
    create_site_login_token,
    parse_oauth_state,
)
from settings import Settings, get_settings

__version__ = "1.4.5"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("discord_auth")


def _client_ip(request: Request) -> str:
    settings: Settings = request.app.state.settings
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _parse_user_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(raw))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid user_id") from exc


def _oauth_url(settings: Settings, user_id: uuid.UUID) -> str:
    state = create_oauth_state(secret=settings.game_auth_secret, user_id=str(user_id))
    return (
        f"{OAUTH_AUTHORIZE}?"
        + urlencode(
            {
                "client_id": settings.client_id,
                "redirect_uri": settings.redirect_uri,
                "response_type": "code",
                "scope": "identify guilds",
                "state": state,
                "prompt": "consent",
            }
        )
    )


def _qr_png_base64(url: str) -> str:
    # segno writes PNG without Pillow / system jpeg libs.
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="png", scale=6)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _page(settings: Settings, title: str, message: str, status_code: int = 400):
    return error_page(title, message, site_url=settings.site_public_url, status_code=status_code)


def _require_api_key(settings: Settings, key: str | None) -> None:
    if not api_key_valid(key, settings.api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")


async def _ensure_required_guild(
    *,
    settings: Settings,
    discord: DiscordClient,
    access_token: str,
    discord_id: str,
):
    if not settings.require_guild:
        return None
    required = settings.required_guild_ids
    if not required:
        return _page(
            settings,
            "Конфигурация",
            "REQUIRE_GUILD включён, но не задан ни один GUILD_ID / AUTH_DISCORD_ROLES",
            500,
        )

    try:
        guilds = await discord.fetch_guilds(access_token)
        user_guild_ids = {str(g.get("id")) for g in guilds}
        if any(gid in user_guild_ids for gid in required):
            return None

        member = await discord.is_member_of_any(discord_id, required)
        if member is True:
            return None
        if member is False:
            return _page(
                settings,
                "Нужен Discord сервер",
                "Вы должны быть участником Discord-сервера Мини-станции",
                403,
            )
        return _page(
            settings,
            "Нужен Discord сервер",
            "Не удалось подтвердить участие в Discord-сервере. "
            "Разрешите приложению видеть ваши сервера в настройках Discord.",
            403,
        )
    except DiscordApiError as exc:
        return _page(settings, "Ошибка Discord", str(exc), 502)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    discord = DiscordClient(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        redirect_uri=settings.redirect_uri,
        bot_token=settings.bot_token,
        auth_roles=[(t.guild_id, t.role_id, t.bot_token) for t in settings.auth_roles],
        guild_id=settings.guild_id,
        auth_role_id=settings.auth_discord_role_id,
    )
    await discord.start()
    app.state.settings = settings
    app.state.discord = discord
    if settings.require_guild and settings.required_guild_ids and not settings.bot_token:
        logger.warning("REQUIRE_GUILD=true but BOT_TOKEN is empty; relying on OAuth guilds list only")
    logger.info(
        "SS14 Discord Auth v%s ready; databases=%s; auth_roles=%s",
        __version__,
        ", ".join(db.name for db in settings.databases),
        ", ".join(f"{t.guild_id}:{t.role_id}" for t in settings.auth_roles) or "(none)",
    )
    yield
    await discord.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="SS14 Discord Auth",
        version=__version__,
        description="Discord linking service for Мини-станция / Space Station 14",
        lifespan=lifespan,
        docs_url=None if settings.disable_docs else "/docs",
        redoc_url=None if settings.disable_docs else "/redoc",
        openapi_url=None if settings.disable_docs else "/openapi.json",
    )
    application.add_middleware(SecurityHeadersMiddleware)

    @application.get("/health", response_model=HealthResponse)
    def health():
        db_status = ping_databases()
        ok = bool(db_status) and all(db_status.values())
        payload = HealthResponse(ok=ok, version=__version__, databases=db_status)
        return JSONResponse(
            content=payload.model_dump(),
            status_code=200 if ok else 503,
        )

    @application.get("/login/{user_id}")
    def generate_auth_link_get(request: Request, user_id: str):
        settings = request.app.state.settings
        if not limiter.hit(f"login:{_client_ip(request)}", limit=settings.rate_limit_login):
            raise HTTPException(status_code=429, detail="Too many requests")
        uid = _parse_user_id(user_id)
        return RedirectResponse(_oauth_url(settings, uid), status_code=307)

    @application.get("/callback")
    async def discord_callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
        error_description: str | None = None,
    ):
        settings: Settings = request.app.state.settings
        discord: DiscordClient = request.app.state.discord

        if not limiter.hit(f"callback:{_client_ip(request)}", limit=settings.rate_limit_callback):
            return _page(settings, "Слишком много запросов", "Подождите немного и попробуйте снова.", 429)

        if error:
            return _page(settings, "Авторизация отменена", error_description or error, 400)
        if not code or not state:
            return _page(settings, "Ошибка авторизации", "Нет code/state от Discord", 400)

        try:
            uid = _parse_user_id(parse_oauth_state(state, settings.game_auth_secret, consume=True))
        except (ValueError, HTTPException):
            return _page(settings, "Ошибка авторизации", "Некорректный или просроченный state", 400)

        try:
            access_token = await discord.exchange_code(code)
            user = await discord.fetch_user(access_token)
        except DiscordApiError as exc:
            logger.warning("Discord OAuth failed: %s", exc)
            return _page(settings, "Ошибка Discord", str(exc), 400)

        discord_id = str(user["id"])
        username = str(user.get("global_name") or user.get("username") or discord_id)
        avatar = user.get("avatar")

        guild_error = await _ensure_required_guild(
            settings=settings,
            discord=discord,
            access_token=access_token,
            discord_id=discord_id,
        )
        if guild_error is not None:
            return guild_error

        try:
            link_account_all(uid, int(discord_id))
        except LinkConflictError as exc:
            return _page(settings, "Привязка невозможна", str(exc), 409)
        except Exception:
            logger.exception("Link failed for user=%s discord=%s", uid, discord_id)
            return _page(settings, "Ошибка привязки", "Не удалось сохранить привязку. Попробуйте позже.", 500)

        await discord.assign_auth_role(discord_id)

        token = create_site_login_token(
            secret=settings.game_auth_secret,
            discord_id=discord_id,
            username=username,
            avatar=avatar if isinstance(avatar, str) else None,
            ss14_user_id=str(uid),
        )
        target = f"{settings.site_public_url}{settings.site_login_path}?{urlencode({'token': token})}"

        if settings.show_success_page:
            return success_page(
                site_url=settings.site_public_url,
                redirect_url=target,
                username=username,
            )
        return RedirectResponse(target, status_code=302)

    @application.post("/{user_id}", response_model=LinkResponse)
    def generate_auth_link_post(request: Request, user_id: str, key: str = Query(...)):
        settings = request.app.state.settings
        _require_api_key(settings, key)
        uid = _parse_user_id(user_id)
        url = _oauth_url(settings, uid)
        return LinkResponse(Url=url, Qrcode=_qr_png_base64(url))

    @application.get("/{user_id}", response_model=AuthInfoResponse)
    def check_verification_status(
        request: Request,
        user_id: str,
        key: str | None = Query(default=None),
    ):
        settings = request.app.state.settings
        if settings.require_check_api_key:
            _require_api_key(settings, key)
        uid = _parse_user_id(user_id)
        return AuthInfoResponse(IsLinked=is_linked_any(uid))

    return application


app = create_app()


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "discord_auth_server:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        proxy_headers=settings.trust_proxy,
        forwarded_allow_ips=settings.forwarded_allow_ips,
    )


if __name__ == "__main__":
    main()
