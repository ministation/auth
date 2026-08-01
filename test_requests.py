"""Smoke-test helpers for the Discord auth API."""

from __future__ import annotations

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5001"
USER_ID = "00000000-0000-0000-0000-000000000001"
API_KEY = sys.argv[2] if len(sys.argv) > 2 else os.getenv("API_KEY", "")


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=10.0, follow_redirects=False) as client:
        check = client.get(f"/{USER_ID}")
        print("GET /{user_id}:", check.status_code, check.text)

        link = client.post(f"/{USER_ID}", params={"key": API_KEY})
        print("POST /{user_id}:", link.status_code, link.json().get("Url"))

        login = client.get(f"/login/{USER_ID}")
        print("GET /login/{user_id}:", login.status_code, login.headers.get("location"))


if __name__ == "__main__":
    main()
