# Copyright (c) 2024–2026 Мини-станция (Mini-Station). All rights reserved.
# See LICENSE for terms.

"""Signed tokens, OAuth state, API-key checks."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
import uuid
from typing import Any

_used_tokens: dict[str, int] = {}
_lock = threading.Lock()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(body: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return _b64url_encode(digest)


def _purge_expired(now: int) -> None:
    expired = [key for key, exp in _used_tokens.items() if exp <= now]
    for key in expired:
        _used_tokens.pop(key, None)


def _consume_once(key: str, exp: int) -> None:
    now = int(time.time())
    with _lock:
        _purge_expired(now)
        if key in _used_tokens:
            raise ValueError("Token already used")
        _used_tokens[key] = exp


def create_signed_payload(payload: dict[str, Any], secret: str) -> str:
    body = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    return f"{body}.{_sign(body, secret)}"


def verify_signed_payload(token: str, secret: str) -> dict[str, Any]:
    try:
        body, sig = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Malformed token") from exc

    if not hmac.compare_digest(_sign(body, secret), sig):
        raise ValueError("Invalid token signature")

    try:
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed token payload") from exc

    if not isinstance(payload, dict):
        raise ValueError("Malformed token payload")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Token expired")
    return payload


def create_oauth_state(*, secret: str, user_id: str, ttl_seconds: int = 600) -> str:
    # Validate early so we never embed garbage.
    uuid.UUID(str(user_id))
    return create_signed_payload(
        {
            "user_id": str(user_id),
            "nonce": secrets.token_urlsafe(16),
            "exp": int(time.time()) + ttl_seconds,
        },
        secret,
    )


def parse_oauth_state(state: str, secret: str, *, consume: bool = True) -> str:
    payload = verify_signed_payload(state, secret)
    user_id = payload.get("user_id")
    nonce = payload.get("nonce")
    if not user_id or not nonce:
        raise ValueError("State missing fields")
    uuid.UUID(str(user_id))
    if consume:
        _consume_once(f"state:{nonce}", int(payload["exp"]))
    return str(user_id)


def create_site_login_token(
    *,
    secret: str,
    discord_id: str,
    username: str,
    avatar: str | None,
    ss14_user_id: str,
    ttl_seconds: int = 120,
) -> str:
    if not str(discord_id).isdigit():
        raise ValueError("Invalid discord_id")
    uuid.UUID(str(ss14_user_id))
    if avatar is not None and not (
        isinstance(avatar, str) and len(avatar) <= 128 and all(c in "0123456789abcdef" for c in avatar.lower())
    ):
        avatar = None

    return create_signed_payload(
        {
            "discord_id": str(discord_id),
            "username": str(username)[:64],
            "avatar": avatar,
            "ss14_user_id": str(ss14_user_id),
            "jti": secrets.token_urlsafe(16),
            "exp": int(time.time()) + ttl_seconds,
        },
        secret,
    )


def verify_site_login_token(token: str, secret: str, *, consume: bool = False) -> dict[str, Any]:
    payload = verify_signed_payload(token, secret)
    discord_id = str(payload.get("discord_id") or "")
    username = str(payload.get("username") or "")
    jti = payload.get("jti")
    ss14_user_id = payload.get("ss14_user_id")

    if not discord_id.isdigit() or not username or not jti:
        raise ValueError("Token missing identity")
    if ss14_user_id:
        uuid.UUID(str(ss14_user_id))

    if consume:
        _consume_once(f"jti:{jti}", int(payload["exp"]))

    return payload


def api_key_valid(provided: str | None, expected: str) -> bool:
    left = (provided or "").encode("utf-8")
    right = expected.encode("utf-8")
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)
