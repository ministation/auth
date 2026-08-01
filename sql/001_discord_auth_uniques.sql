-- Optional hardening for production PostgreSQL.
-- Safe to run multiple times.

CREATE UNIQUE INDEX IF NOT EXISTS uq_discord_auth_user_id
    ON public.discord_auth (user_id)
    WHERE user_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_discord_auth_discord_id
    ON public.discord_auth (discord_id)
    WHERE discord_id IS NOT NULL;
