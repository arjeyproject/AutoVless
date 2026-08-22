"""Entrypoint: wire the dispatcher, start the background jobs, poll Telegram."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from . import db, handlers, middlewares
from .config import settings
from .refresher import refresher
from .scanner import proxy_scanner, scanner
from .warpscan import warp_scanner

log = logging.getLogger("autovless")

COMMANDS = [
    BotCommand(command="start", description="Start / \u0634\u0631\u0648\u0639"),
    BotCommand(command="menu", description="Main menu / \u0645\u0646\u0648\u06cc \u0627\u0635\u0644\u06cc"),
    BotCommand(command="warp", description="WARP / \u0648\u0627\u0631\u067e"),
    BotCommand(command="cancel", description="Cancel / \u0644\u063a\u0648"),
]


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


def preflight() -> None:
    problems: list[str] = []
    if not settings.bot_token:
        problems.append("BOT_TOKEN is missing")
    if not settings.admin_ids:
        problems.append("ADMIN_IDS is missing")
    if not settings.worker_file.exists():
        problems.append(f"worker bundle not found at {settings.worker_file}")
    if settings.config_count <= 0:
        problems.append("TLS_CONFIG_COUNT + HTTP_CONFIG_COUNT must be greater than zero")
    if not settings.clean_ip_sources:
        log.warning("CLEAN_IP_SOURCES is empty; the scanner will run on the sweep alone")
    if problems:
        for problem in problems:
            log.error("configuration error: %s", problem)
        sys.exit(1)


async def seed_options() -> None:
    for key, value in db.DEFAULT_OPTIONS.items():
        existing = await db.fetch_one("SELECT 1 FROM options WHERE key = ?", (key,))
        if existing is None:
            await db.set_option(key, value)


async def notify_admins(bot: Bot) -> None:
    pool = await scanner.stats()
    relays = await proxy_scanner.stats()
    warp = await warp_scanner.stats()
    by_port = pool.get("by_port") or {}
    breakdown = " \u00b7 ".join(f"{port}:{count}" for port, count in sorted(by_port.items())) or "-"
    message = (
        f"\u2705 <b>{settings.brand}</b> is up.\n"
        f"\U0001f4e1 clean ip pool: <b>{pool['total']}</b> "
        f"(fresh <b>{pool.get('fresh', 0)}</b> \u00b7 {breakdown})\n"
        f"\U0001f6e1 relays ready: <b>{relays['verified']}</b>\n"
        f"\U0001f9ec warp endpoints: <b>{warp['stable']}</b>\n"
        f"\U0001f50d sweep: <b>{pool.get('sweep', 0)}%</b> of "
        f"{pool.get('blocks', 0)} blocks \u00b7 lap {pool.get('laps', 0) + 1}\n"
        f"\U0001f50c ports: <b>{', '.join(str(p) for p in scanner.ports)}</b>"
    )
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, message)
        except Exception:  # noqa: BLE001
            log.warning("could not notify admin %s", admin_id)


async def run() -> None:
    configure_logging()
    preflight()

    await db.init()
    await seed_options()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())

    middlewares.register(dispatcher)
    handlers.register(dispatcher)

    await scanner.start()
    await proxy_scanner.start()
    await warp_scanner.start()
    refresher.attach(bot)
    await refresher.start()

    try:
        await bot.set_my_commands(COMMANDS)
        await notify_admins(bot)
        log.info("%s is polling", settings.brand)
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await refresher.stop()
        await warp_scanner.stop()
        await proxy_scanner.stop()
        await scanner.stop()
        await db.close()
        await bot.session.close()
        log.info("shutdown complete")


def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
