# Copyright (c) 2024–2026 Мини-станция (Mini-Station). All rights reserved.
# See LICENSE for terms.

"""
Backfill Discord «Авторизован» roles for accounts already in discord_auth.

Usage (from repo root):
  python scripts/sync_auth_roles.py --only-guild 1381238425260134440
  python scripts/sync_auth_roles.py --only-guild 1381238425260134440 --resume
  python scripts/sync_auth_roles.py --dry-run

Notes:
  - «not_member» = user is not on that Discord server (normal for Oasis backfill).
  - 429 is retried automatically; raise --delay if Discord still throttles.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.database import init_db  # noqa: E402
from db.multi import list_linked_discord_ids  # noqa: E402
from discord_client import DiscordClient  # noqa: E402
from settings import get_settings  # noqa: E402


async def run(
    *,
    only_guild: str | None,
    dry_run: bool,
    delay: float,
    resume: bool,
    reset_state: bool,
) -> int:
    settings = get_settings()
    init_db()
    ids = list_linked_discord_ids()
    targets = settings.auth_roles
    if only_guild:
        targets = [t for t in targets if t.guild_id == only_guild]
    if not targets:
        print("No auth role targets configured (check AUTH_DISCORD_ROLES / GUILD2_*).")
        return 1

    state_file = ROOT / (
        f".sync_auth_roles_{only_guild or 'all'}.json"
    )
    done: set[str] = set()
    if reset_state and state_file.exists():
        state_file.unlink()
        print(f"Cleared state {state_file.name}")
    if resume and state_file.exists():
        try:
            payload = json.loads(state_file.read_text(encoding="utf-8"))
            done = {str(x) for x in payload.get("done", [])}
            print(f"Resume: {len(done)} already processed")
        except Exception as exc:  # noqa: BLE001
            print(f"Could not read state file: {exc}")

    pending = [i for i in ids if str(i) not in done]
    print(f"Linked Discord IDs: {len(ids)} (pending {len(pending)})")
    print("Targets: " + ", ".join(f"{t.guild_id}:{t.role_id}" for t in targets))
    print("not_member = user is not on the target Discord (skip, expected).")
    if dry_run:
        print("Dry run — no Discord API writes.")
        return 0
    if not pending:
        print("Nothing to do.")
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
        for i, discord_id in enumerate(pending, start=1):
            results = await discord.assign_auth_role(
                str(discord_id),
                only_guild_ids=[t.guild_id for t in targets],
                quiet_not_member=True,
            )
            for guild_id, status in results.items():
                key = f"{status}"
                counts[key] = counts.get(key, 0) + 1
                if status == "ok":
                    print(f"  ok  {discord_id} @ {guild_id}")
                elif status not in ("not_member",):
                    print(f"  {status}  {discord_id} @ {guild_id}")

            done.add(str(discord_id))
            if i % 20 == 0 or i == len(pending):
                state_file.write_text(
                    json.dumps({"done": sorted(done)}, ensure_ascii=True),
                    encoding="utf-8",
                )
                print(
                    f"… {i}/{len(pending)}  "
                    + " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
                )
            if delay > 0:
                await asyncio.sleep(delay)
    except KeyboardInterrupt:
        state_file.write_text(
            json.dumps({"done": sorted(done)}, ensure_ascii=True),
            encoding="utf-8",
        )
        print(f"\nInterrupted. Progress saved to {state_file.name}")
        print("Continue with: python scripts/sync_auth_roles.py --resume "
              + (f"--only-guild {only_guild}" if only_guild else ""))
        return 130
    finally:
        await discord.stop()

    state_file.write_text(
        json.dumps({"done": sorted(done)}, ensure_ascii=True),
        encoding="utf-8",
    )
    print("Summary:")
    for key, n in sorted(counts.items()):
        print(f"  {key}: {n}")
    print(
        "Hint: not_member means they never joined Oasis — invite/join first, "
        "then role is granted on next login or re-run."
    )
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
        default=0.9,
        help="Seconds between users (default 0.9; raise if 429 persists)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip Discord IDs already recorded in the state file",
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Clear resume state before starting",
    )
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(
            run(
                only_guild=args.only_guild.strip() or None,
                dry_run=args.dry_run,
                delay=max(0.0, args.delay),
                resume=args.resume,
                reset_state=args.reset_state,
            )
        )
    )


if __name__ == "__main__":
    main()
