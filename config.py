"""Environment/configuration loading.

Converted from the Cloudflare Worker `env` bindings (env.BOT_TOKEN,
env.ADMIN_IDS, env.WEBHOOK_SECRET, env.BOT_USERNAME, env.DB) into plain
Python environment variables, read once at process startup.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _parse_admin_ids(raw_values: list[str]) -> set[int]:
    """Mirrors isAdmin() in util.js: accepts ADMIN_IDS (comma-separated),
    plus ADMIN_ID / admin_id as singular aliases, all merged together.
    """
    ids: set[int] = set()
    for raw in raw_values:
        if not raw:
            continue
        for part in raw.split(","):
            part = part.strip()
            if part:
                try:
                    ids.add(int(part))
                except ValueError:
                    pass
    return ids


@dataclass
class Config:
    bot_token: str
    admin_ids: set[int] = field(default_factory=set)
    webhook_secret: str | None = None
    bot_username: str | None = None
    database_path: str = "data/bot.db"
    run_mode: str = "polling"  # "polling" | "webhook"
    webhook_base_url: str | None = None  # e.g. https://your-domain.example
    webhook_path: str = "/webhook"
    web_server_host: str = "0.0.0.0"
    web_server_port: int = 8080

    @classmethod
    def from_env(cls) -> "Config":
        bot_token = os.environ.get("BOT_TOKEN", "").strip()
        if not bot_token:
            raise RuntimeError(
                "BOT_TOKEN environment variable is required (Telegram bot token "
                "from @BotFather)."
            )

        admin_ids = _parse_admin_ids(
            [
                os.environ.get("ADMIN_IDS", ""),
                os.environ.get("ADMIN_ID", ""),
                os.environ.get("admin_id", ""),
            ]
        )

        bot_username = os.environ.get("BOT_USERNAME", "").strip() or None
        if bot_username in ("undefined", ""):
            bot_username = None
        if bot_username:
            bot_username = bot_username.lstrip("@")

        return cls(
            bot_token=bot_token,
            admin_ids=admin_ids,
            webhook_secret=os.environ.get("WEBHOOK_SECRET") or None,
            bot_username=bot_username,
            database_path=os.environ.get("DATABASE_PATH", "data/bot.db"),
            run_mode=os.environ.get("RUN_MODE", "polling").strip().lower(),
            webhook_base_url=os.environ.get("WEBHOOK_BASE_URL") or None,
            webhook_path=os.environ.get("WEBHOOK_PATH", "/webhook"),
            web_server_host=os.environ.get("WEB_SERVER_HOST", "0.0.0.0"),
            web_server_port=int(os.environ.get("WEB_SERVER_PORT", "8080")),
        )

    def is_admin(self, user_id: int) -> bool:
        """Mirrors isAdmin(env, userId) in util.js."""
        return user_id in self.admin_ids
