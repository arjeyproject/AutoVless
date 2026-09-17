"""Entrypoint: wire the dispatcher, start the engines, serve the mini app, poll."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from . import db, handlers, middlewares, referral, store
from .api import api_server
from .autopilot import autopilot
from .config import settings
from .curator import curator
from .scanner import proxy_scanner, scanner
from .warppool import warp_pool
from .warpscan import warp_scanner

log = logging.getLogger("autovless")

COMMANDS = [
    BotCommand(command="start", description="Start / \u0634\u0631\u0648\u0639"),
    BotCommand(command="menu", description="Main menu / \u0645\u0646\u0648\u06cc \u0627\u0635\u0644\u06cc"),
    BotCommand(command="app", description="Mini App / \u0645\u06cc\u0646\u06cc\u200c\u0627\u067e"),
    BotCommand(command="selfhost", description="Free tier / \u0633\u0631\u0648\u06cc\u0633 \u0631\u0627\u06cc\u06af\u0627\u0646"),
    BotCommand(command="invite", description="Invite friends / \u062f\u0639\u0648\u062a \u062f\u0648\u0633\u062a\u0627\u0646"),
    BotCommand(command="apps", description="Apps / \u0628\u0631\u0646\u0627\u0645\u0647\u200c\u0647\u0627"),
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
    if problems:
        for problem in problems:
            log.error("configuration error: %s", problem)
        sys.exit(1)


async def seed_options() -> None:
    for key, value in db.DEFAULT_OPTIONS.items():
        existing = await db.fetch_one("SELECT 1 FROM options WHERE key = ?", (key,))
        if existing is None:
            await db.set_option(key, value)


def _n(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


async def _stat(coro) -> dict:
    """One engine's stats, or an empty dict.

    Every read in the startup notice goes through here. It used to index the
    dictionaries directly, and because the notice runs inside ``run()``'s try
    block, a single missing key raised, fell through to the ``finally``, and shut
    the whole bot down before it ever polled. A stat that will not load is worth
    a blank in a message, nothing more.
    """
    try:
        return dict(await coro or {})
    except Exception:  # noqa: BLE001
        log.debug("startup stat unavailable", exc_info=True)
        return {}


async def _option(coro, default: Any) -> Any:
    try:
        return await coro
    except Exception:  # noqa: BLE001
        log.debug("startup option unavailable", exc_info=True)
        return default


async def _startup_report() -> str:
    pool = await _stat(db.pool_stats())
    relays = await _stat(proxy_scanner.stats())
    warp = await _stat(warp_scanner.stats())
    pools = await _stat(warp_pool.status())
    pilot = await _stat(autopilot.stats())
    keeper = await _stat(curator.stats())
    free = await _stat(store.free_stats())

    families = dict(pools.get("families") or {})
    v4 = dict(families.get("v4") or {})
    v6 = dict(families.get("v6") or {})
    target = _n(pools.get("target"))
    lock = await _option(store.flag("referral_lock"), False)
    required = await _option(store.get_int("referral_required", 3), 3)
    ports = list(getattr(scanner, "ports", ()) or settings.all_ports)

    return (
        f"\u2705 <b>{settings.brand}</b> is up.\n"
        f"\U0001f4e1 clean ip pool: <b>{_n(pool.get('total'))}</b> "
        f"(verified {_n(pool.get('verified'))}, fresh {_n(pool.get('fresh'))})\n"
        f"\U0001f300 self-healing hostnames: <b>{_n(pool.get('domains'))}</b>\n"
        f"\U0001f6e1 relays ready: <b>{_n(relays.get('verified'))}</b>\n"
        f"\U0001f9ec warp endpoints: <b>{_n(warp.get('stable'))}</b>\n"
        f"\U0001f3ca warp pools: IPv4 <b>{_n(v4.get('healthy'))}</b>/{target} \u00b7 "
        f"IPv6 <b>{_n(v6.get('healthy'))}</b>/{target} "
        f"(agent {'on' if pools.get('agent') else 'off'}, "
        f"source {pools.get('source') or 'n/a'})\n"
        f"\U0001f916 autopilot: <b>{'on' if pilot.get('enabled') else 'off'}</b> "
        f"(every {_n(pilot.get('interval'), settings.autopilot_interval)}s)\n"
        f"\U0001f9f9 curator: <b>{'on' if keeper.get('enabled') else 'off'}</b> "
        f"(every {_n(keeper.get('interval'), settings.curator_interval)}s, "
        f"{_n(keeper.get('target'))} fresh per port)\n"
        f"\U0001f388 free servers: <b>{_n(free.get('servers'))}</b> "
        f"(healthy {_n(free.get('healthy'))})\n"
        f"\U0001f510 invite lock: <b>{'on' if lock else 'off'}</b> ({_n(required, 3)} per user)\n"
        f"\U0001f680 mini app: <b>{settings.webapp_url or 'not set'}</b>\n"
        f"\U0001f50c ports: <b>{', '.join(str(p) for p in ports)}</b>"
    )


async def notify_admins(bot: Bot) -> None:
    try:
        message = await _startup_report()
    except Exception:  # noqa: BLE001
        log.exception("could not build the startup report")
        message = f"\u2705 <b>{settings.brand}</b> is up."
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
    # Tables added after 1.0 patch themselves in here, before any handler can
    # read one that does not exist yet.
    await store.ensure()

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
    # After the scanner: the pool agent borrows its probing identity.
    await warp_pool.start()
    await autopilot.start()
    await curator.start()
    # The invite link is built from the bot's own username, and the API has no Bot
    # handle of its own, so it is resolved once here.
    await referral.bot_username(bot)
    await api_server.start()

    try:
        await bot.set_my_commands(COMMANDS)
        await notify_admins(bot)
        log.info("%s is polling", settings.brand)
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await api_server.stop()
        await curator.stop()
        await autopilot.stop()
        await warp_pool.stop()
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
