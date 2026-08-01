# Copyright (c) 2024–2026 Мини-станция (Mini-Station). All rights reserved.
# See LICENSE for terms.

"""API response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LinkResponse(BaseModel):
    Url: str = Field(..., description="Discord OAuth URL")
    Qrcode: str = Field(..., description="PNG QR as base64")


class AuthInfoResponse(BaseModel):
    IsLinked: bool


class HealthResponse(BaseModel):
    ok: bool
    version: str
    databases: dict[str, bool]
