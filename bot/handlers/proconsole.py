"""The 3.0 pro management console: one screen that answers every operational
question an operator asks in a running deployment.

The stock admin screens answer single questions one at a time - stats here,
broadcast there, panels somewhere else - and each of them rebuilds the world
from its own queries. That is fine for day one and painful on day thirty, when
the operator wants one glance that says whether the machine is healthy, one
flow that reaches exactly the right users, and one place to fix a user's panel
without reading SQL.

So this console owns, all from one home screen:

* a live monitor that merges every engine's numbers into a single view;
* a self-test that pokes each subsystem and prints a green/red line per check;
* a targeted broadcast with audiences (everyone, panel owners, panel-less,
  joined today, banned) and a preview before anything goes out;
* user tools: search, a full card, force rebuild, panel delete, direct
  message, ban and unban;
* a WARP console: pool health, the top endpoints, a deep sweep, a purge and
  the seed export;
* a settings backup that round-trips the bot's options as JSON, with secrets
  masked on the way out and a whitelist on the way back in;
* the daily digest toggle, which hands the same monitor to the operator's
  own chat every day without anybody pressing anything.

Every callback here lives in the ``adm:pro`` namespace. ``handlers.admin``
claims every ``adm:`` callback with one broad handler, so this router must be
registered before it - same reason ``adminx`` exists.
"""

from __future__ import annotations

import asyncio
import json
import logging
import resource
import time

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .. import db, keyboards, store, warpconf, warppool, warpstore, wgpro
from ..autopilot import autopilot
from ..config import settings
from ..curator import curator
from ..i18n import num, t
from ..utils import ago, edit, esc, ping_label
from ..warpscan import warp_scanner

# The pool instance rides on the module of the same name; the alias keeps the
# call sites readable exactly like main.py's own import.
warp_pool = warppool.warp_pool

log = logging.getLogger("autovless.handlers.proconsole")
router = Router(name="proconsole")

_STARTED = time.time()
_BROADCAST_GAP = 0.05  # seconds between deliveries: ~20/s, far under any limit
_BROADCAST_LIMIT = 10_000  # hard ceiling; a run past this needs a real mailing tool

SEGMENTS: tuple[str, ...] = ("all", "panel", "nopanel", "today", "banned")

# Keys the settings import is allowed to touch. Everything else in a pasted
# file is reported as skipped, never applied - a backup file from another bot,
# or a hand-edited one, cannot flip an engine it does not own.
IMPORT_ALLOWED: frozenset[str] = frozenset(db.DEFAULT_OPTIONS) | {"referral_required"}
SECRET_MARKS: tuple[str, ...] = ("token", "secret", "merchant", "key")


class ProFlow(StatesGroup):
    broadcast = State()
    user_search = State()
    direct_message = State()
    settings_import = State()


def _guard(is_admin: bool) -> bool:
    return bool(is_admin)


def _b(label: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=label, callback_data=data)


def _seg_key(segment: str) -> str:
    return f"pro.bcast_seg_{segment}"


# --------------------------------------------------------------------- #
# home
# --------------------------------------------------------------------- #


async def _digest_label(lang: str) -> str:
    on = await db.get_flag("digest")
    return f"{'✅' if on else '⚪️'} {t(lang, 'opt.digest')}"


async def pro_home_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.pro_sys"), "adm:pro:sys"), _b(t(lang, "btn.pro_selftest"), "adm:pro:selftest")],
            [_b(t(lang, "btn.pro_bcast"), "adm:pro:bcast"), _b(t(lang, "btn.pro_users"), "adm:pro:users")],
            [_b(t(lang, "btn.pro_wg"), "adm:pro:wg"), _b(t(lang, "btn.pro_cfg"), "adm:pro:cfg")],
            [_b(await _digest_label(lang), "adm:pro:digest")],
            keyboards.back_row(lang, "adm:menu"),
        ]
    )


@router.callback_query(F.data == "adm:pro")
async def on_home(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    await state.clear()
    await edit(call, t(lang, "pro.admin_home"), await pro_home_kb(lang))
    await call.answer()


@router.callback_query(F.data == "adm:pro:digest")
async def on_digest_toggle(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    on = await db.toggle_flag("digest")
    await db.log_event("digest_toggle", call.from_user.id, "on" if on else "off")
    await edit(call, t(lang, "pro.admin_home"), await pro_home_kb(lang))
    await call.answer(t(lang, "admin.on" if on else "admin.off"))


# --------------------------------------------------------------------- #
# the live monitor
# --------------------------------------------------------------------- #


def _human_size(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _uptime() -> str:
    seconds = int(time.time() - _STARTED)
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h{minutes:02d}m"


async def monitor_text(lang: str) -> str:
    gs = await db.global_stats()
    pool = await db.pool_stats()
    warp = await warpstore.stats()
    pilot = await autopilot.stats()
    keeper = await curator.stats()
    return t(
        lang,
        "pro.sys",
        uptime=_uptime(),
        mem=_human_size(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
        dbsize=_human_size(settings.db_path.stat().st_size) if settings.db_path.exists() else "-",
        users=num(gs["users"], lang),
        today=num(gs["users_today"], lang),
        week=num(gs["active_week"], lang),
        panels=num(gs["panels"], lang),
        healthy=num(gs["panels_healthy"], lang),
        pool=num(pool["total"], lang),
        verified=num(pool["verified"], lang),
        warp=num(warp["stable"], lang),
        best=f"{num(round(warp['best'] or 0, 1), lang)} ms" if warp["best"] else "-",
        v4=num(warp["v4"], lang),
        v6=num(warp["v6"], lang),
        pilot=t(lang, "admin.on") if pilot["enabled"] else t(lang, "admin.off"),
        curator=t(lang, "admin.on") if keeper["enabled"] else t(lang, "admin.off"),
        tickets=num(gs["tickets_waiting"], lang),
        maintenance=t(lang, "admin.on") if await db.get_flag("maintenance") else t(lang, "admin.off"),
        builds=num(gs["syncs"], lang),
    )


@router.callback_query(F.data == "adm:pro:sys")
async def on_monitor(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    await state.clear()
    try:
        await edit(call, await monitor_text(lang), await pro_home_kb(lang))
    except Exception:  # noqa: BLE001
        log.warning("monitor render failed", exc_info=True)
        await call.answer(t(lang, "pro.common_error", reason="render"), show_alert=True)
        return
    await call.answer()


# --------------------------------------------------------------------- #
# the self-test
# --------------------------------------------------------------------- #


async def _check(name: str, function) -> tuple[str, bool, str]:
    try:
        ok, detail = await function()
        return name, bool(ok), str(detail)
    except Exception as error:  # noqa: BLE001
        return name, False, esc(str(error)[:90])


async def run_selftest(lang: str) -> tuple[list[tuple[str, bool, str]], str]:
    checks: list[tuple[str, bool, str]] = []

    async def db_alive() -> tuple[bool, str]:
        await db.fetch_one("SELECT 1")
        return True, "sqlite ok"

    async def options_alive() -> tuple[bool, str]:
        value = await db.get_option("maintenance", "0")
        return value != "", "options ok"

    async def crypto_roundtrip() -> tuple[bool, str]:
        probe = f"probe-{int(time.time())}"
        await db.set_option("selftest_probe", probe)
        back = await db.get_option("selftest_probe")
        await db.execute("DELETE FROM options WHERE key = 'selftest_probe'")
        return back == probe, "write+read ok"

    async def clean_pool() -> tuple[bool, str]:
        stats = await db.pool_stats()
        return (
            stats["verified"] >= 1,
            f"{num(stats['verified'], lang)}/{num(stats['total'], lang)} · fresh {num(stats['fresh'], lang)}",
        )

    async def warp_endpoints() -> tuple[bool, str]:
        stats = await warpstore.stats()
        return stats["stable"] >= 1, f"stable {num(stats['stable'], lang)}"

    async def warp_families() -> tuple[bool, str]:
        status = await warp_pool.status()
        v4 = status["families"]["v4"]["healthy"]
        v6 = status["families"]["v6"]["healthy"]
        return v4 >= 1 or v6 >= 1, f"v4 {num(v4, lang)} · v6 {num(v6, lang)}"

    async def free_servers() -> tuple[bool, str]:
        stats = await store.free_stats()
        return True, f"{num(stats['servers'], lang)} · healthy {num(stats['healthy'], lang)}"

    async def worker_bundle() -> tuple[bool, str]:
        return settings.worker_file.exists(), esc(str(settings.worker_file.name))

    async def panels() -> tuple[bool, str]:
        gs = await db.global_stats()
        if gs["panels"] == 0:
            return True, t(lang, "pro.wg_none")
        ratio = gs["panels_healthy"] / max(1, gs["panels"])
        return ratio >= 0.5, f"{num(gs['panels_healthy'], lang)}/{num(gs['panels'], lang)}"

    async def scanner_recent() -> tuple[bool, str]:
        stats = await db.pool_stats()
        age = int(time.time()) - int(stats["updated_at"] or 0)
        fresh = age < max(settings.scan_ttl * 4, 6 * 3600)
        return fresh, ago(stats["updated_at"] or 0, lang)

    async def miniapp() -> tuple[bool, str]:
        return bool(settings.webapp_url), esc(settings.webapp_url or "-")

    checks.append(await _check(t(lang, "pro.chk_db"), db_alive))
    checks.append(await _check(t(lang, "pro.chk_opts"), options_alive))
    checks.append(await _check(t(lang, "pro.chk_crypto"), crypto_roundtrip))
    checks.append(await _check(t(lang, "pro.chk_pool"), clean_pool))
    checks.append(await _check(t(lang, "pro.chk_warp"), warp_endpoints))
    checks.append(await _check(t(lang, "pro.chk_warpool"), warp_families))
    checks.append(await _check(t(lang, "pro.chk_free"), free_servers))
    checks.append(await _check(t(lang, "pro.chk_worker"), worker_bundle))
    checks.append(await _check(t(lang, "pro.chk_panels"), panels))
    checks.append(await _check(t(lang, "pro.chk_scanner"), scanner_recent))
    checks.append(await _check(t(lang, "pro.chk_webapp"), miniapp))

    ok = sum(1 for _, good, _ in checks if good)
    total = len(checks)
    verdict = (
        t(lang, "pro.selftest_pass", ok=num(ok, lang), total=num(total, lang))
        if ok == total
        else t(lang, "pro.selftest_partial", fail=num(total - ok, lang), ok=num(ok, lang), total=num(total, lang))
    )
    return checks, verdict


@router.callback_query(F.data == "adm:pro:selftest")
async def on_selftest(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    await state.clear()
    await call.answer(t(lang, "pro.selftest_started"))
    checks, verdict = await run_selftest(lang)
    lines = "\n".join(
        t(lang, "pro.selftest_ok" if good else "pro.selftest_fail", name=name, detail=detail)
        for name, good, detail in checks
    )
    passed = sum(1 for _, good, _ in checks if good)
    await db.log_event("selftest", call.from_user.id, f"{passed}/{len(checks)}")
    await edit(
        call,
        t(lang, "pro.selftest_done", lines=lines, verdict=verdict),
        await pro_home_kb(lang),
    )


# --------------------------------------------------------------------- #
# the targeted broadcast
# --------------------------------------------------------------------- #


async def _segment_counts() -> dict[str, int]:
    day = db.now() - 86_400
    return {
        "all": int(await db.scalar("SELECT COUNT(*) FROM users WHERE is_banned = 0")),
        "panel": int(
            await db.scalar("SELECT COUNT(*) FROM users u JOIN panels p ON p.tg_id = u.tg_id WHERE u.is_banned = 0")
        ),
        "nopanel": int(
            await db.scalar(
                "SELECT COUNT(*) FROM users u WHERE u.is_banned = 0 AND "
                "NOT EXISTS (SELECT 1 FROM panels p WHERE p.tg_id = u.tg_id)"
            )
        ),
        "today": int(await db.scalar("SELECT COUNT(*) FROM users WHERE created_at >= ?", (day,))),
        "banned": int(await db.scalar("SELECT COUNT(*) FROM users WHERE is_banned = 1")),
    }


async def _audience(segment: str) -> list[int]:
    if segment == "all":
        return await db.all_user_ids(include_banned=False)
    if segment == "panel":
        rows = await db.fetch_all(
            "SELECT u.tg_id FROM users u JOIN panels p ON p.tg_id = u.tg_id WHERE u.is_banned = 0"
        )
    elif segment == "nopanel":
        rows = await db.fetch_all(
            "SELECT u.tg_id FROM users u WHERE u.is_banned = 0 AND "
            "NOT EXISTS (SELECT 1 FROM panels p WHERE p.tg_id = u.tg_id)"
        )
    elif segment == "today":
        rows = await db.fetch_all(
            "SELECT tg_id FROM users WHERE is_banned = 0 AND created_at >= ?", (db.now() - 86_400,)
        )
    elif segment == "banned":
        rows = await db.fetch_all("SELECT tg_id FROM users WHERE is_banned = 1")
    else:
        return []
    return [row["tg_id"] for row in rows]


def _segment_kb(lang: str, counts: dict[str, int]) -> InlineKeyboardMarkup:
    rows = [
        [_b(t(lang, _seg_key(segment), count=num(counts[segment], lang)), f"adm:pro:bcast:{segment}")]
        for segment in SEGMENTS
    ]
    rows.append(keyboards.back_row(lang, "adm:pro"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:pro:bcast")
async def on_broadcast(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    await state.clear()
    await edit(call, t(lang, "pro.bcast"), _segment_kb(lang, await _segment_counts()))
    await call.answer()


@router.callback_query(F.data.startswith("adm:pro:bcast:"))
async def on_segment(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    segment = (call.data or "").rsplit(":", 1)[-1]
    if segment not in SEGMENTS:
        await call.answer()
        return
    audience = await _audience(segment)
    if not audience:
        await call.answer(t(lang, "pro.users_none"), show_alert=True)
        return
    await state.set_state(ProFlow.broadcast)
    await state.update_data(segment=segment, count=len(audience))
    await edit(call, t(lang, "pro.bcast_prompt"), keyboards.simple_back(lang, "adm:pro"))
    await call.answer()


@router.message(ProFlow.broadcast)
async def on_broadcast_message(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    segment = data.get("segment", "all")
    count = int(data.get("count", 0))
    await state.update_data(src_chat=message.chat.id, src_msg=message.message_id)
    await state.set_state(None)
    await message.answer(
        t(
            lang,
            "pro.bcast_preview",
            segment=t(lang, _seg_key(segment), count=num(count, lang)),
            count=num(count, lang),
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    _b(t(lang, "btn.confirm"), "adm:pro:send"),
                    _b(t(lang, "btn.cancel"), "adm:pro:abort"),
                ]
            ]
        ),
    )


@router.callback_query(F.data == "adm:pro:abort")
async def on_broadcast_cancel(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    await state.clear()
    await edit(call, t(lang, "pro.bcast_cancel"), await pro_home_kb(lang))
    await call.answer()


@router.callback_query(F.data == "adm:pro:send")
async def on_broadcast_send(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    data = await state.get_data()
    await state.clear()
    src_chat = data.get("src_chat")
    src_msg = data.get("src_msg")
    if not src_chat or not src_msg:
        await call.answer(t(lang, "pro.common_error", reason="state"), show_alert=True)
        return

    segment = data.get("segment", "all")
    audience = (await _audience(segment))[:_BROADCAST_LIMIT]
    bot: Bot = call.bot
    sent = failed = 0
    progress = await call.message.answer(t(lang, "pro.bcast_running", count=num(len(audience), lang)))

    for index, tg_id in enumerate(audience, start=1):
        try:
            await bot.copy_message(tg_id, src_chat, src_msg)
            sent += 1
        except Exception:  # noqa: BLE001
            failed += 1
        if index % 25 == 0:
            try:
                await progress.edit_text(
                    f"📣 {num(index, lang)}/{num(len(audience), lang)} · ✅ {num(sent, lang)} · ❌ {num(failed, lang)}"
                )
            except Exception:  # noqa: BLE001
                pass
        await asyncio.sleep(_BROADCAST_GAP)

    await db.log_event("broadcast", call.from_user.id, f"{segment}:{sent}/{len(audience)}")
    body = t(lang, "pro.bcast_done", sent=num(sent, lang), failed=num(failed, lang))
    try:
        await progress.edit_text(body, reply_markup=await pro_home_kb(lang))
    except Exception:  # noqa: BLE001
        await call.message.answer(body, reply_markup=await pro_home_kb(lang))
    await call.answer()


# --------------------------------------------------------------------- #
# user tools
# --------------------------------------------------------------------- #


def _user_rows(lang: str, rows) -> InlineKeyboardMarkup:
    buttons = [
        [_b(f"👤 {esc(row['first_name'] or row['username'] or row['tg_id'])}", f"adm:pro:u:{row['tg_id']}")]
        for row in rows
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons + [keyboards.back_row(lang, "adm:pro")])


async def _user_card(lang: str, tg_id: int) -> tuple[str, InlineKeyboardMarkup]:
    user = await db.get_user(tg_id)
    panel = await db.get_panel(tg_id)
    prefs = await wgpro.prefs_of(tg_id)
    gs_row = user
    name = esc((gs_row["first_name"] if gs_row else "") or "-")
    username = esc((gs_row["username"] if gs_row else "") or "-")
    card = t(
        lang,
        "pro.user_card",
        tg=num(tg_id, lang),
        name=name,
        username=username,
        lang=(gs_row["lang"] if gs_row else "-"),
        operator=esc((gs_row["operator"] if gs_row else "") or "-"),
        panel=f"<code>{esc(panel['host'])}</code>" if panel else t(lang, "pro.wg_none"),
        rebuilds=num(panel["rebuilds"], lang) if panel else "0",
        builds=num(gs_row["builds"], lang) if gs_row else "0",
        wg=wgpro.summary(prefs, lang),
        banned=("🚫" if (gs_row and gs_row["is_banned"]) else "✅"),
        seen=ago(gs_row["seen_at"] if gs_row else 0, lang),
    )
    banned = bool(gs_row and gs_row["is_banned"])
    rows: list[list[InlineKeyboardButton]] = []
    if panel:
        rows.append(
            [
                _b(t(lang, "btn.pro_force_rebuild"), f"adm:pro:u:{tg_id}:rb"),
                _b(t(lang, "btn.pro_del_panel"), f"adm:pro:u:{tg_id}:pdel"),
            ]
        )
    rows.append(
        [
            _b(t(lang, "btn.pro_dm"), f"adm:pro:u:{tg_id}:dm"),
            _b(t(lang, "btn.pro_unban" if banned else "btn.pro_ban"), f"adm:pro:u:{tg_id}:{'unban' if banned else 'ban'}"),
        ]
    )
    rows.append(keyboards.back_row(lang, "adm:pro:users"))
    return card, InlineKeyboardMarkup(inline_keyboard=rows)


# NOTE: the back button above goes to the ``adm:pro:users`` callback, which
# re-arms the search state; no separate "back" callback is needed here.


@router.callback_query(F.data == "adm:pro:users")
async def on_users(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    await state.set_state(ProFlow.user_search)
    await edit(call, t(lang, "pro.users_prompt"), keyboards.simple_back(lang, "adm:pro"))
    await call.answer()


@router.message(ProFlow.user_search, F.text, ~F.text.startswith("/"))
async def on_user_term(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(None)
    rows = await db.find_users(message.text or "", limit=8)
    if not rows:
        await message.answer(t(lang, "pro.users_none"))
        return
    if len(rows) == 1:
        card, markup = await _user_card(lang, rows[0]["tg_id"])
        await message.answer(card, reply_markup=markup)
        return
    await message.answer(t(lang, "pro.users_pick"), reply_markup=_user_rows(lang, rows))


@router.callback_query(F.data.startswith("adm:pro:u:"))
async def on_user_action(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    parts = (call.data or "").split(":")
    # adm:pro:u:<id> | adm:pro:u:<id>:<action>
    try:
        tg_id = int(parts[3])
    except (IndexError, ValueError):
        await call.answer()
        return
    action = parts[4] if len(parts) > 4 else ""

    if not action:
        await state.clear()
        card, markup = await _user_card(lang, tg_id)
        await edit(call, card, markup)
        await call.answer()
        return

    if action == "rb":
        if await db.get_panel(tg_id) is None:
            await call.answer(t(lang, "pro.panel_missing"), show_alert=True)
            return
        await db.queue_panel_refresh([tg_id])
        await db.log_event("pro_rebuild", tg_id, "queued")
        await call.answer(t(lang, "pro.rebuild_queued"), show_alert=True)
        return
    if action == "pdel":
        await db.delete_panel(tg_id)
        await db.log_event("pro_panel_del", tg_id, "")
        card, markup = await _user_card(lang, tg_id)
        await edit(call, t(lang, "pro.panel_deleted") + "\n\n" + card, markup)
        await call.answer()
        return
    if action == "ban":
        await db.set_banned(tg_id, True)
        await db.log_event("pro_ban", tg_id, "on")
        card, markup = await _user_card(lang, tg_id)
        await edit(call, t(lang, "admin.ban_done") + "\n\n" + card, markup)
        await call.answer()
        return
    if action == "unban":
        await db.set_banned(tg_id, False)
        await db.log_event("pro_ban", tg_id, "off")
        card, markup = await _user_card(lang, tg_id)
        await edit(call, t(lang, "admin.unban_done") + "\n\n" + card, markup)
        await call.answer()
        return
    if action == "dm":
        await state.set_state(ProFlow.direct_message)
        await state.update_data(target=tg_id)
        await edit(call, t(lang, "pro.dm_prompt", tg=num(tg_id, lang)), keyboards.simple_back(lang, "adm:pro:users"))
        await call.answer()
        return
    await call.answer()


@router.message(ProFlow.direct_message)
async def on_dm_message(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    await state.clear()
    target = int(data.get("target") or 0)
    if not target:
        await message.answer(t(lang, "pro.users_none"))
        return
    try:
        await message.bot.copy_message(target, message.chat.id, message.message_id)
    except Exception as error:  # noqa: BLE001
        await message.answer(t(lang, "pro.common_error", reason=esc(str(error)[:80])))
        return
    await db.log_event("pro_dm", target, "")
    card, markup = await _user_card(lang, target)
    await message.answer(t(lang, "pro.dm_sent", tg=num(target, lang)) + "\n\n" + card, reply_markup=markup)


# --------------------------------------------------------------------- #
# the WARP console
# --------------------------------------------------------------------- #


def _warp_console_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.pro_wg_top"), "adm:pro:wg:top"), _b(t(lang, "btn.pro_deep_scan"), "adm:pro:wg:deep")],
            [_b(t(lang, "btn.pro_purge"), "adm:pro:wg:purge"), _b(t(lang, "btn.pro_pub_seed"), "adm:pro:wg:seed")],
            keyboards.back_row(lang, "adm:pro"),
        ]
    )


@router.callback_query(F.data == "adm:pro:wg")
async def on_warp_console(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    await state.clear()
    stats = await warpstore.stats()
    status = await warp_pool.status()
    manual = int(
        await db.scalar(
            "SELECT COUNT(*) FROM warp_endpoints WHERE manual = 1",
            default=0,
        )
        or 0
    )
    best = f"{esc(stats['best_endpoint'])} · {num(round(stats['best'] or 0, 1), lang)} ms" if stats["best"] else "-"
    body = t(
        lang,
        "pro.wg_title",
        total=num(stats["total"], lang),
        stable=num(stats["stable"], lang),
        fast=num(stats["fast"], lang),
        v4=num(stats["v4"], lang),
        v6=num(stats["v6"], lang),
        manual=num(manual, lang),
        best=best,
        best_score=num(round(stats["best_score"] or 0, 1), lang) if stats["best_score"] else "-",
        loss=f"{num(round((stats['loss'] or 0) * 100, 1), lang)}%",
        users=num(stats["users"], lang),
        pool_v4=num(status["families"]["v4"]["healthy"], lang),
        pool_v6=num(status["families"]["v6"]["healthy"], lang),
        target=num(status["target"], lang),
        updated=ago(stats["updated_at"], lang),
    )
    await edit(call, body, _warp_console_kb(lang))
    await call.answer()


@router.callback_query(F.data == "adm:pro:wg:top")
async def on_warp_top(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    rows = await warpstore.best(15)
    if not rows:
        await call.answer(t(lang, "pro.bench_no_pool"), show_alert=True)
        return
    lines = []
    for index, row in enumerate(rows, start=1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(index, "▫️")
        lines.append(
            f"{medal} <code>{esc(warpconf.host_port(row['ip'], row['port']))}</code> · "
            f"<b>{ping_label(row['latency'], lang)}</b> · {num(round(row.get('score') or 0, 1), lang)}"
        )
    await edit(call, t(lang, "pro.wg_top", count=num(len(rows), lang), table="\n".join(lines)), _warp_console_kb(lang))
    await call.answer()


@router.callback_query(F.data == "adm:pro:wg:deep")
async def on_warp_deep(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    if warp_scanner.running:
        await call.answer(t(lang, "pro.wg_scan_running"), show_alert=True)
        return
    # A full sweep of every family this host can reach, forced, with the
    # verification pass that proves traffic actually flows through the winner.
    asyncio.create_task(warp_scanner.scan(force=True, quick=False))
    await db.log_event("warp_deep_scan", call.from_user.id, "forced")
    await call.answer(t(lang, "pro.wg_deep_started"), show_alert=True)


@router.callback_query(F.data == "adm:pro:wg:purge")
async def on_warp_purge(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    retired = await warpstore.retire()
    purged = await warpstore.purge_unhealthy()
    await db.log_event("warp_purge", call.from_user.id, f"retired={retired} purged={purged}")
    await call.answer(
        t(lang, "pro.wg_purged", retired=num(retired, lang), purged=num(purged, lang)),
        show_alert=True,
    )


@router.callback_query(F.data == "adm:pro:wg:seed")
async def on_warp_seed(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    rows = await warpstore.snapshot(limit=64)
    if not rows:
        await call.answer(t(lang, "pro.bench_no_pool"), show_alert=True)
        return
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    stats = await warpstore.stats()
    payload = {
        "generated_at": stamp,
        "source": "console",
        "count": len(rows),
        "best_latency_ms": round(min(row["latency"] for row in rows), 1),
        "pool": {"stable": stats["stable"], "total": stats["total"], "avg_loss": stats["loss"]},
        "endpoints": [
            {
                "endpoint": f"{row['ip']}:{row['port']}",
                "ip": row["ip"],
                "port": row["port"],
                "latency_ms": round(float(row["latency"]), 1),
            }
            for row in rows
        ],
    }
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    lines = "\n".join(f"{row['ip']}:{row['port']}" for row in rows)
    try:
        data_dir = settings.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "warp-seed.json").write_text(body, encoding="utf-8")
        (data_dir / "warp-seed.txt").write_text(lines + "\n", encoding="utf-8")
    except OSError as error:
        await call.answer(t(lang, "pro.wg_pub_fail", reason=esc(str(error)[:90])), show_alert=True)
        return
    await db.log_event("warp_seed", call.from_user.id, str(len(rows)))
    await call.answer()
    await call.message.answer_document(
        BufferedInputFile(body.encode("utf-8"), filename="warp-seed.json"),
        caption=t(lang, "pro.wg_pub_done", path="data/warp-seed.json", count=num(len(rows), lang)),
    )


# --------------------------------------------------------------------- #
# the settings backup
# --------------------------------------------------------------------- #


def _mask(key: str, value: str) -> str:
    if not value:
        return value
    if any(mark in key.lower() for mark in SECRET_MARKS):
        return "••••••"
    return value


@router.callback_query(F.data == "adm:pro:cfg")
async def on_cfg(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    await state.clear()
    rows = [
        [_b(t(lang, "btn.pro_cfg_export"), "adm:pro:cfg:exp"), _b(t(lang, "btn.pro_cfg_import"), "adm:pro:cfg:imp")],
        keyboards.back_row(lang, "adm:pro"),
    ]
    await edit(call, t(lang, "pro.cfg_title"), InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()


@router.callback_query(F.data == "adm:pro:cfg:exp")
async def on_cfg_export(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    rows = await db.fetch_all("SELECT key, value FROM options WHERE key NOT LIKE 'wgpro:%' ORDER BY key")
    options = {row["key"]: _mask(row["key"], row["value"]) for row in rows}
    payload = {
        "format": "autovless-settings-backup",
        "version": 1,
        "brand": settings.brand,
        "exported_at": int(time.time()),
        "options": options,
    }
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    await db.log_event("cfg_export", call.from_user.id, str(len(options)))
    await call.answer()
    await call.message.answer_document(
        BufferedInputFile(body.encode("utf-8"), filename="autovless-settings.json"),
        caption=t(lang, "pro.cfg_export_caption"),
    )


@router.callback_query(F.data == "adm:pro:cfg:imp")
async def on_cfg_import(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer()
        return
    await state.set_state(ProFlow.settings_import)
    await edit(call, t(lang, "pro.cfg_import_prompt"), keyboards.simple_back(lang, "adm:pro"))
    await call.answer()


async def _apply_settings(message: Message, lang: str, raw: str) -> None:
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("not an object")
        options = payload.get("options") if isinstance(payload.get("options"), dict) else payload
    except ValueError as error:
        await message.answer(t(lang, "pro.cfg_import_bad", reason=esc(str(error)[:90])))
        return

    applied = skipped = 0
    for key, value in (options or {}).items():
        if key not in IMPORT_ALLOWED or isinstance(value, (dict, list)):
            skipped += 1
            continue
        await db.set_option(key, str(value))
        applied += 1
    await db.log_event("cfg_import", message.from_user.id, f"{applied}/{skipped}")
    await message.answer(
        t(lang, "pro.cfg_import_done", applied=num(applied, lang), skipped=num(skipped, lang)),
        reply_markup=await pro_home_kb(lang),
    )


@router.message(ProFlow.settings_import, F.document)
async def on_cfg_file(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    document = message.document
    if document is None or (document.file_size or 0) > 256_000:
        await message.answer(t(lang, "pro.cfg_import_bad", reason="file"))
        return
    try:
        raw = (await message.bot.download(document)).read().decode("utf-8")
    except Exception as error:  # noqa: BLE001
        await message.answer(t(lang, "pro.cfg_import_bad", reason=esc(str(error)[:90])))
        return
    await _apply_settings(message, lang, raw)


@router.message(ProFlow.settings_import, F.text, ~F.text.startswith("/"))
async def on_cfg_text(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    await _apply_settings(message, lang, message.text or "")
