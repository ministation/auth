"""Compatibility shim — use settings.get_settings()."""

from settings import DatabaseConfig, Settings, get_settings, load_settings

__all__ = ["DatabaseConfig", "Settings", "get_settings", "load_settings"]
