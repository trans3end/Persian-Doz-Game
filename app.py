"""Application entrypoint.

Wires together config, the SQLite-backed repository, the aiogram Bot +
Dispatcher, the timer manager (Durable Object replacement), and starts
the bot in either long-polling or webhook mode depending on RUN_MODE.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from config import Config
from context import AppContext
from database.repository import Repository
from game import games as game_service
from game.timer import TimerManager
from storage.sqlite import Database
from telegram.client import TelegramClient, make_bot
from telegram.handlers import callbacks, messages

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
logger = logging.getLogger("app")


async def build_context(config: Config) -> tuple[AppContext, Dispatcher]:
    db = Database(config.database_path)
    await db.connect()
    repo = Repository(db)

    bot = make_bot(config.bot_token)
    tg = TelegramClient(bot)
    timers = TimerManager()

    ctx = AppContext(tg=tg, repo=repo, config=config, timers=timers)

    async def on_warning(game_id: str, move_count: int) -> bool:
        return await game_service.notify_turn_warning(game_id, move_count, ctx)

    async def on_timeout(game_id: str, move_count: int) -> None:
        await game_service.apply_turn_timeout(game_id, move_count, ctx)

    timers.configure(on_warning=on_warning, on_timeout=on_timeout)

    dp = Dispatcher()
    dp.include_router(messages.router)
    dp.include_router(callbacks.router)

    return ctx, dp


async def recover_timers(ctx: AppContext) -> None:
    active_games = await ctx.repo.list_active_games()
    if active_games:
        logger.info("Recovering timers for %d in-progress game(s)", len(active_games))
        ctx.timers.recover(active_games)


async def run_polling(config: Config) -> None:
    ctx, dp = await build_context(config)
    await recover_timers(ctx)
    try:
        await ctx.tg.bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(ctx.tg.bot, ctx=ctx)
    finally:
        await ctx.tg.bot.session.close()
        await ctx.repo.db.close()


async def run_webhook(config: Config) -> None:
    if not config.webhook_base_url:
        raise RuntimeError("WEBHOOK_BASE_URL must be set when RUN_MODE=webhook")

    ctx, dp = await build_context(config)
    await recover_timers(ctx)

    webhook_url = config.webhook_base_url.rstrip("/") + config.webhook_path
    await ctx.tg.set_webhook(webhook_url, secret_token=config.webhook_secret)

    app = web.Application()
    SimpleRequestHandler(
        dispatcher=dp, bot=ctx.tg.bot, secret_token=config.webhook_secret, ctx=ctx
    ).register(app, path=config.webhook_path)
    setup_application(app, dp, bot=ctx.tg.bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.web_server_host, config.web_server_port)
    await site.start()
    logger.info("Webhook server listening on %s:%s%s", config.web_server_host, config.web_server_port, config.webhook_path)

    try:
        await asyncio.Event().wait()  # run forever
    finally:
        await runner.cleanup()
        await ctx.tg.bot.session.close()
        await ctx.repo.db.close()


def main() -> None:
    config = Config.from_env()
    if config.run_mode == "webhook":
        asyncio.run(run_webhook(config))
    else:
        asyncio.run(run_polling(config))


if __name__ == "__main__":
    main()
