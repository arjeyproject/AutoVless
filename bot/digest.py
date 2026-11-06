"""The scheduled admin digest: the pro monitor, delivered unprompted.

An operator who has to open the bot and press buttons to learn the machine's
state eventually stops doing it, and the first sign of a dead scanner becomes
a user complaint three days later. The digest flips that around: once a day
the bot sends the same numbers the live monitor shows straight to every
admin's chat, so a shrinking pool or a stalled autopilot is visible without
anybody asking.

The toggle is the ``digest`` option flag, exposed on the pro console home.
Delivery time is nothing special - the job ticks every ten minutes and fires
when at least a day has passed since the previous digest - because an exact
hour matters far less than the report simply always arriving.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from aiogram import Bot

from . import db
from .config import settings

log = logging.getLogger("autovless.digest")

TICK_SECONDS = 600
DAY_SECONDS = 86_400


async def digest_text() -> str:
    """The digest body, in the admin's language when it can be told apart."""
    from . import store, warpstore
    from .autopilot import autopilot
    from .curator import curator
    from .i18n import num, t
    from .utils import esc

    lang = settings.default_lang or "fa"
    gs = await db.global_stats()
    pool = await db.pool_stats()
    warp = await warpstore.stats()
    free = await store.free_stats()
    pilot = await autopilot.stats()
    keeper = await curator.stats()
    return t(
        lang,
        "pro.digest_text",
        brand=esc(settings.brand),
        users=num(gs["users"], lang),
        today=num(gs["users_today"], lang),
        panels=num(gs["panels"], lang),
        healthy=num(gs["panels_healthy"], lang),
        pool=num(pool["total"], lang),
        verified=num(pool["verified"], lang),
        warp=num(warp["stable"], lang),
        v4=num(warp["v4"], lang),
        v6=num(warp["v6"], lang),
        free=num(free["healthy"], lang),
        tickets=num(gs["tickets_waiting"], lang),
        pilot=("🟢" if pilot["enabled"] else "🔴"),
        curator=("🟢" if keeper["enabled"] else "🔴"),
    )


class Digest:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._bot: Optional[Bot] = None

    async def start(self, bot: Bot) -> None:
        self._bot = bot
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="digest")
            log.info("digest job started (tick=%ss)", TICK_SECONDS)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=TICK_SECONDS)
                return
            except asyncio.TimeoutError:
                pass
            try:
                await self._tick()
            except Exception:  # noqa: BLE001
                log.warning("digest tick failed", exc_info=True)

    async def _tick(self) -> None:
        if not await db.get_flag("digest"):
            return
        last = int(await db.get_option("digest_at", "0") or 0)
        if last and time.time() - last < DAY_SECONDS:
            return
        body = await digest_text()
        delivered = 0
        for admin_id in settings.admin_ids:
            try:
                await self._bot.send_message(admin_id, body)
                delivered += 1
            except Exception:  # noqa: BLE001
                log.info("digest could not reach admin %s", admin_id)
        await db.set_option("digest_at", str(int(time.time())))
        await db.log_event("digest", None, f"delivered={delivered}")
        log.info("digest delivered to %s admin(s)", delivered)


digest = Digest()
