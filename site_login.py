"""Helpers for one-time handoff tokens to ministation.ru."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_site_login_token(
    *,
    secret: str,
    discord_id: str,
    username: str,
    avatar: str | None,
    ss14_user_id: str,
    ttl_seconds: int = 120,
) -> str:
    payload = {
        "discord_id": str(discord_id),
        "username": username,
        "avatar": avatar,
        "ss14_user_id": ss14_user_id,
        "exp": int(time.time()) + ttl_seconds,
    }
    body = _b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64url_encode(signature)}"


def verify_site_login_token(token: str, secret: str) -> dict[str, Any]:
    try:
        body, sig = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Malformed token") from exc

    expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    given = _b64url_decode(sig)
    if not hmac.compare_digest(expected, given):
        raise ValueError("Invalid token signature")

    payload = json.loads(_b64url_decode(body).decode("utf-8"))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Token expired")
    if not payload.get("discord_id") or not payload.get("username"):
        raise ValueError("Token missing identity")
    return payload
