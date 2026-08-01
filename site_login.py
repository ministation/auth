"""Compatibility shim — use security.*."""

from security import (
    create_oauth_state,
    create_site_login_token,
    parse_oauth_state,
    verify_site_login_token,
)

__all__ = [
    "create_oauth_state",
    "create_site_login_token",
    "parse_oauth_state",
    "verify_site_login_token",
]
