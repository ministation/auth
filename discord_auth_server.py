"""SS14 Discord auth service (Corvax-compatible API) with ministation.ru handoff."""

from __future__ import annotations

import io
import logging
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx
import qrcode
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from config_loader import load_settings
from db import init_db
from db.crud import LinkConflictError
from db.multi import is_linked_any, link_account_all
from site_login import create_site_login_token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("discord_auth")

settings = load_settings()

BOT_TOKEN = settings.bot_token
API_KEY = settings.api_key
CLIENT_ID = settings.client_id
CLIENT_SECRET = settings.client_secret
REDIRECT_URI = settings.redirect_uri
GUILD_ID = settings.guild_id
AUTH_DISCORD_ROLE_ID = settings.auth_discord_role_id
SITE_PUBLIC_URL = settings.site_public_url
SITE_LOGIN_PATH = settings.site_login_path
GAME_AUTH_SECRET = settings.game_auth_secret
REQUIRE_GUILD = settings.require_guild

DISCORD_API = "https://discord.com/api/v10"
OAUTH_AUTHORIZE = "https://discord.com/api/oauth2/authorize"
OAUTH_TOKEN = "https://discord.com/api/oauth2/token"

app = FastAPI(title="SS14 Discord Auth", version="1.1.0")


class LinkResponse(BaseModel):
    Url: str
    Qrcode: str


class AuthInfoResponse(BaseModel):
    IsLinked: bool


def _parse_user_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid user_id") from exc


def _oauth_url(user_id: uuid.UUID) -> str:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds",
        "state": str(user_id),
        "prompt": "consent",
    }
    return f"{OAUTH_AUTHORIZE}?{urlencode(params)}"


def _qr_png_base64(url: str) -> str:
    import base64

    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _require_api_key(key: str) -> None:
    import hmac as _hmac

    if not key or not _hmac.compare_digest(key.encode("utf-8"), API_KEY.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Invalid API key")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    logger.info("Databases: %s", ", ".join(db.name for db in settings.databases))


async def _exchange_code(code: str) -> str:
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            OAUTH_TOKEN,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Token exchange failed: {resp.text}")
        payload = resp.json()
        token = payload.get("access_token")
        if not token:
            raise HTTPException(status_code=400, detail="No access_token from Discord")
        return token


async def _fetch_discord_user(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch Discord user")
        return resp.json()


async def _fetch_user_guilds(access_token: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{DISCORD_API}/users/@me/guilds",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch Discord guilds")
        return resp.json()


async def _ensure_guild_member(discord_id: str) -> None:
    if not GUILD_ID or not BOT_TOKEN:
        return
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{DISCORD_API}/guilds/{GUILD_ID}/members/{discord_id}",
            headers={"Authorization": f"Bot {BOT_TOKEN}"},
        )
        if resp.status_code == 404:
            raise HTTPException(
                status_code=403,
                detail="Вы должны быть участником Discord-сервера Мини-станции",
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Discord guild membership check failed")


async def _assign_auth_role(discord_id: str) -> None:
    if not GUILD_ID or not BOT_TOKEN or not AUTH_DISCORD_ROLE_ID:
        return
    async with httpx.AsyncClient(timeout=20.0) as client:
        await client.put(
            f"{DISCORD_API}/guilds/{GUILD_ID}/members/{discord_id}/roles/{AUTH_DISCORD_ROLE_ID}",
            headers={"Authorization": f"Bot {BOT_TOKEN}"},
        )


def _error_page(title: str, message: str, status_code: int = 400) -> HTMLResponse:
    html = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>{title}</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0f1419;color:#e7ecf3;display:grid;place-items:center;min-height:100vh;margin:0}}
main{{max-width:28rem;padding:2rem;border:1px solid #2a3441;border-radius:12px;background:#161c24}}
a{{color:#6cb6ff}}
</style></head>
<body><main><h1>{title}</h1><p>{message}</p>
<p><a href="{SITE_PUBLIC_URL}">Перейти на сайт</a></p></main></body></html>"""
    return HTMLResponse(html, status_code=status_code)


@app.get("/login/{user_id}")
def generate_auth_link_get(user_id: str):
    uid = _parse_user_id(user_id)
    return RedirectResponse(_oauth_url(uid), status_code=307)


@app.get("/callback")
async def discord_callback(code: str, state: str):
    uid = _parse_user_id(state)
    access_token = await _exchange_code(code)
    user = await _fetch_discord_user(access_token)
    discord_id = str(user["id"])
    username = user.get("global_name") or user.get("username") or discord_id
    avatar = user.get("avatar")

    if REQUIRE_GUILD and GUILD_ID:
        guilds = await _fetch_user_guilds(access_token)
        if not any(str(g.get("id")) == GUILD_ID for g in guilds):
            try:
                await _ensure_guild_member(discord_id)
            except HTTPException as exc:
                return _error_page(
                    "Нужен Discord сервер",
                    str(exc.detail),
                    status_code=exc.status_code,
                )

    try:
        link_account_all(uid, int(discord_id))
    except LinkConflictError as exc:
        return _error_page("Привязка невозможна", str(exc), status_code=409)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Link failed")
        return _error_page("Ошибка привязки", f"Не удалось сохранить привязку: {exc}", 500)

    try:
        await _assign_auth_role(discord_id)
    except Exception:
        pass

    token = create_site_login_token(
        secret=GAME_AUTH_SECRET,
        discord_id=discord_id,
        username=username,
        avatar=avatar,
        ss14_user_id=str(uid),
    )
    target = f"{SITE_PUBLIC_URL}{SITE_LOGIN_PATH}?token={token}"
    return RedirectResponse(target, status_code=302)


@app.post("/{user_id}", response_model=LinkResponse)
def generate_auth_link_post(user_id: str, key: str = Query(...)):
    _require_api_key(key)
    uid = _parse_user_id(user_id)
    url = _oauth_url(uid)
    return LinkResponse(Url=url, Qrcode=_qr_png_base64(url))


@app.get("/{user_id}", response_model=AuthInfoResponse)
def check_verification_status(user_id: str):
    uid = _parse_user_id(user_id)
    return AuthInfoResponse(IsLinked=is_linked_any(uid))


def main() -> None:
    uvicorn.run(
        "discord_auth_server:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
