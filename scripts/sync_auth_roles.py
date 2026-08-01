# Copyright (c) 2024–2026 Мини-станция (Mini-Station). All rights reserved.
# See LICENSE for terms.

"""
Backfill Discord «Авторизован» roles for accounts already in discord_auth.

Usage (from repo root):
  python scripts/sync_auth_roles.py
  python scripts/sync_auth_roles.py --only-guild 1381238425260134440
  python scripts/sync_auth_roles.py --dry-run
  python scripts/sync_auth_roles.py --delay 0.4
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.database import init_db  # noqa: E402
from db.multi import list_linked_discord_ids  # noqa: E402
from discord_client import DiscordClient  # noqa: E402
from settings import get_settings  # noqa: E402


async def run(*, only_guild: str | None, dry_run: bool, delay: float) -> int:
    settings = get_settings()
    init_db()
    ids = list_linked_discord_ids()
    targets = settings.auth_roles
    if only_guild:
        targets = [t for t in targets if t.guild_id == only_guild]
    if not targets:
        print("No auth role targets configured (check AUTH_DISCORD_ROLES / GUILD2_*).")
        return 1

    print(f"Linked Discord IDs: {len(ids)}")
    print(
        "Targets: "
        + ", ".join(f"{t.guild_id}:{t.role_id}" for t in targets)
    )
    if dry_run:
        print("Dry run — no Discord API writes.")
        return 0

    discord = DiscordClient(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        redirect_uri=settings.redirect_uri,
        bot_token=settings.bot_token,
        auth_roles=[(t.guild_id, t.role_id, t.bot_token) for t in targets],
    )
    await discord.start()
    counts: dict[str, int] = {}
    try:
        for i, discord_id in enumerate(ids, start=1):
            results = await discord.assign_auth_role(
                str(discord_id),
                only_guild_ids=[t.guild_id for t in targets],
            )
            for guild_id, status in results.items():
                key = f"{guild_id}:{status}"
                counts[key] = counts.get(key, 0) + 1
            if i % 25 == 0 or i == len(ids):
                print(f"… {i}/{len(ids)}")
            if delay > 0:
                await asyncio.sleep(delay)
    finally:
        await discord.stop()

    print("Summary:")
    for key, n in sorted(counts.items()):
        print(f"  {key}: {n}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Discord auth roles for linked users")
    parser.add_argument(
        "--only-guild",
        default="",
        help="Only assign on this guild id (e.g. Oasis)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.35,
        help="Seconds between users (rate-limit friendly)",
    )
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(
            run(
                only_guild=args.only_guild.strip() or None,
                dry_run=args.dry_run,
                delay=max(0.0, args.delay),
            )
        )
    )


if __name__ == "__main__":
    main()
