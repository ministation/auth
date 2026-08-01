from __future__ import annotations

import pytest

from security import (
    api_key_valid,
    create_oauth_state,
    create_site_login_token,
    parse_oauth_state,
    verify_site_login_token,
)
import security as security_mod

SECRET = "x" * 32
USER = "00000000-0000-0000-0000-000000000001"


def test_api_key_valid():
    assert api_key_valid("secret12", "secret12")
    assert not api_key_valid("secret1", "secret12")
    assert not api_key_valid(None, "secret12")


def test_oauth_state_roundtrip_and_replay():
    state = create_oauth_state(secret=SECRET, user_id=USER)
    assert parse_oauth_state(state, SECRET, consume=True) == USER
    with pytest.raises(ValueError, match="already used"):
        parse_oauth_state(state, SECRET, consume=True)


def test_site_login_token_roundtrip_and_replay():
    token = create_site_login_token(
        secret=SECRET,
        discord_id="123456789012345678",
        username="player",
        avatar="abcdef",
        ss14_user_id=USER,
    )
    payload = verify_site_login_token(token, SECRET, consume=True)
    assert payload["discord_id"] == "123456789012345678"
    assert payload["username"] == "player"
    with pytest.raises(ValueError, match="already used"):
        verify_site_login_token(token, SECRET, consume=True)


def test_invalid_avatar_stripped():
    token = create_site_login_token(
        secret=SECRET,
        discord_id="1",
        username="u",
        avatar="NOT_HEX!!!",
        ss14_user_id=USER,
    )
    payload = verify_site_login_token(token, SECRET, consume=True)
    assert payload["avatar"] is None


def test_expired_token_rejected(monkeypatch):
    clock = {"now": 1_700_000_000}

    def fake_time():
        return clock["now"]

    monkeypatch.setattr(security_mod.time, "time", fake_time)
    token = create_site_login_token(
        secret=SECRET,
        discord_id="1",
        username="u",
        avatar=None,
        ss14_user_id=USER,
        ttl_seconds=10,
    )
    clock["now"] += 100
    with pytest.raises(ValueError, match="expired"):
        verify_site_login_token(token, SECRET, consume=False)


def test_invalid_user_id_in_state():
    with pytest.raises(ValueError):
        create_oauth_state(secret=SECRET, user_id="not-a-uuid")
