# Copyright (c) 2024–2026 Мини-станция (Mini-Station). All rights reserved.
# See LICENSE for terms.

"""
Backfill Discord «Авторизован» roles for accounts already in discord_auth.

Recommended (Oasis):
  python scripts/sync_auth_roles.py --only-guild 1381238425260134440 --diagnose
  python scripts/sync_auth_roles.py --only-guild 1381238425260134440 --reset-state

By default the script lists actual guild members, intersects with discord_auth,
and only assigns to people who are ON that Discord server.
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
from discord_client import DiscordApiError, DiscordClient  # noqa: E402
from settings import get_settings  # noqa: E402


async def run(
    *,
    only_guild: str | None,
    dry_run: bool,
    delay: float,
    resume: bool,
    reset_state: bool,
    diagnose: bool,
    brute: bool,
) -> int:
    settings = get_settings()
    init_db()
    linked = [str(i) for i in list_linked_discord_ids()]
    linked_set = set(linked)
    targets = settings.auth_roles
    if only_guild:
        targets = [t for t in targets if t.guild_id == only_guild]
    if not targets:
        print("No auth role targets configured (check AUTH_DISCORD_ROLES / GUILD2_*).")
        return 1

    state_file = ROOT / f".sync_auth_roles_{only_guild or 'all'}.json"
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

    print(f"Linked in discord_auth: {len(linked)}")
    print("Targets: " + ", ".join(f"{t.guild_id}:{t.role_id}" for t in targets))

    discord = DiscordClient(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        redirect_uri=settings.redirect_uri,
        bot_token=settings.bot_token,
        auth_roles=[(t.guild_id, t.role_id, t.bot_token) for t in targets],
    )
    await discord.start()

    # per guild_id -> discord ids to assign
    work: dict[str, list[str]] = {}

    try:
        for target in targets:
            guild_id = target.guild_id
            try:
                guild = await discord.fetch_guild(guild_id)
            except DiscordApiError as exc:
                print(f"\nGuild {guild_id}: ERROR — {exc}")
                print("Check GUILD2_ID / GUILD2_BOT_TOKEN and that the bot is invited.")
                return 1

            name = guild.get("name", "?")
            approx = guild.get("approximate_member_count")
            print(f"\nGuild {guild_id} «{name}» approx_members={approx}")

            if brute:
                ids = [i for i in linked if f"{guild_id}:{i}" not in done and i not in done]
                print(f"Brute mode: will probe {len(ids)} linked IDs")
                work[guild_id] = ids
                continue

            try:
                member_ids = await discord.list_guild_member_ids(guild_id)
            except DiscordApiError as exc:
                print(f"Cannot list members: {exc}")
                print(
                    "\nEnable Server Members Intent:\n"
                    "  Discord Developer Portal → Oasis bot application → Bot\n"
                    "  → Privileged Gateway Intents → Server Members Intent = ON → Save\n"
                    "Wait ~1 minute, then re-run.\n"
                    "Or pass --brute to probe each linked id (slow)."
                )
                return 2

            overlap = sorted(linked_set & member_ids)
            print(f"Members visible to bot: {len(member_ids)}")
            print(f"Overlap with discord_auth: {len(overlap)}")
            if overlap:
                print("Sample overlap IDs: " + ", ".join(overlap[:8]))
            else:
                print(
                    "No overlap: nobody from discord_auth is currently on this Discord.\n"
                    "Backfill cannot invent membership — they must join Oasis first.\n"
                    "After join, next site/game login (or re-run sync) grants the role."
                )
            work[guild_id] = [i for i in overlap if i not in done]

        total = sum(len(v) for v in work.values())
        if diagnose:
            print(f"\nDiagnose only — {total} user(s) would get a role.")
            return 0
        if dry_run:
            print(f"\nDry run — would assign to {total} user(s).")
            return 0
        if total == 0:
            print("\nNothing to assign.")
            return 0

        print(f"\nAssigning roles to {total} member(s)…")
        counts: dict[str, int] = {}
        processed = 0
        try:
            for guild_id, ids in work.items():
                for discord_id in ids:
                    processed += 1
                    results = await discord.assign_auth_role(
                        discord_id,
                        only_guild_ids=[guild_id],
                        quiet_not_member=True,
                    )
                    for gid, status in results.items():
                        counts[status] = counts.get(status, 0) + 1
                        if status == "ok":
                            print(f"  ok  {discord_id} @ {gid}")
                        elif status != "not_member":
                            print(f"  {status}  {discord_id} @ {gid}")

                    done.add(discord_id)
                    if processed % 20 == 0 or processed == total:
                        state_file.write_text(
                            json.dumps({"done": sorted(done)}, ensure_ascii=True),
                            encoding="utf-8",
                        )
                        print(
                            f"… {processed}/{total}  "
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
            print(
                "Continue with: python scripts/sync_auth_roles.py --resume "
                + (f"--only-guild {only_guild}" if only_guild else "")
            )
            return 130

        state_file.write_text(
            json.dumps({"done": sorted(done)}, ensure_ascii=True),
            encoding="utf-8",
        )
        print("Summary:")
        for key, n in sorted(counts.items()):
            print(f"  {key}: {n}")
        return 0
    finally:
        await discord.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Discord auth roles for linked users")
    parser.add_argument("--only-guild", default="", help="Only this guild id (Oasis)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--diagnose", action="store_true", help="Only show guild/overlap stats")
    parser.add_argument(
        "--brute",
        action="store_true",
        help="Probe every linked id (old behaviour); ignore member list",
    )
    parser.add_argument("--delay", type=float, default=0.9)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reset-state", action="store_true")
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(
            run(
                only_guild=args.only_guild.strip() or None,
                dry_run=args.dry_run,
                delay=max(0.0, args.delay),
                resume=args.resume,
                reset_state=args.reset_state,
                diagnose=args.diagnose,
                brute=args.brute,
            )
        )
    )


if __name__ == "__main__":
    main()
