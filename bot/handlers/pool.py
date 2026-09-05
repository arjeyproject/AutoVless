"""Device/operator selection and admin controls for the endpoint pools.

Device choice controls file syntax, not network reachability. Pool measurements
are from the server, not proof of connectivity on the user's mobile network.
This router is registered ahead of handlers.warp.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile, CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup,
)

from .. import db, keyboards, operators, warpconf, warpep, warpmanual, warpstore
from .. import warp as warpcore
from ..config import settings
from ..i18n import num, t
from ..utils import ago, edit, esc, ping_label
from ..warpep import V4, V6
from ..warppool import AuditReport, RefreshReport, warp_pool
from ..warptune import TUNE

log = logging.getLogger("autovless.handlers.pool")
router = Router(name="pool")

CHOICES: dict[str, dict[str, str]] = {
    "mtn": {"family": V6, "operator": "mtn"},
    "other": {"family": V4, "operator": "other"},
}
PLATFORMS = ("android", "ios")
WIREGUARD_IOS = "https://apps.apple.com/app/wireguard/id1441195209"

VERDICT_MARKS: dict[str, str] = {
    "stored": "\u2705",
    "untested": "\U0001f552",
    "dead": "\U0001f480",
    "weak": "\u26a0\ufe0f",
    "family": "\U0001f6ab",
    "dup": "\U0001f501",
    "bad": "\u274c",
    "over": "\u26d4\ufe0f",
}
REPORT_LINES = 24
_jobs: set[asyncio.Task] = set()
# A second tap must not register another identity or race endpoint rotation.
_building: set[int] = set()


class PoolFlow(StatesGroup):
    """Waiting for a pasted endpoint list. The family is kept in the state data."""

    manual = State()


def _spawn(coro, name: str) -> None:
    task = asyncio.create_task(coro, name=name)
    _jobs.add(task)
    task.add_done_callback(_jobs.discard)


def _family_label(family: str, lang: str) -> str:
    return t(lang, "wg.family_v6" if family == V6 else "wg.family_v4")


def _operator_hint(family: str, lang: str) -> str:
    return t(lang, "btn.wg_irancell" if family == V6 else "btn.wg_other")


def _app_link(platform: str = "android") -> str:
    if platform == "ios":
        return f'<a href="{WIREGUARD_IOS}">WireGuard</a>'
    return f'<a href="{keyboards.AMNEZIA_PLAY_URL}">AmneziaVPN</a>'


def _mark(full: bool) -> str:
    return "\u2705" if full else "\u26a0\ufe0f"


def _out_of(value: object, lang: str) -> str:
    return f"{num(int(value or 0), lang)}/{num(100, lang)}"


def _note_line(note: str, lang: str) -> str:
    if not note:
        return ""
    return "\n" + t(lang, f"pool.note_{note}")


def _identity_line(status: dict, lang: str) -> str:
    ok = status.get("identity_ok")
    state = (
        t(lang, "pool.identity_unknown")
        if ok is None
        else t(lang, "pool.identity_ok" if ok else "pool.identity_bad")
    )
    return f"{esc(str(status.get('identity') or '-'))} \u00b7 {state}"


def _routes_line(status: dict, lang: str) -> str:
    routes = status.get("routes") or {}
    parts = []
    for family in (V4, V6):
        mark = "\u2705" if routes.get(family) else "\u26d4\ufe0f"
        parts.append(f"{_family_label(family, lang)} {mark}")
    return " \u00b7 ".join(parts)


def _guard(is_admin: bool) -> bool:
    return bool(is_admin)


def _next_endpoints(endpoints: list[dict], current: list[dict]) -> list[dict]:
    """Rotate relative to the last delivered (IP, port), not a fixed pool slot."""
    if len(endpoints) < 2 or not current:
        return endpoints
    key = (str(current[0]["ip"]), int(current[0]["port"]))
    for index, row in enumerate(endpoints):
        if (str(row["ip"]), int(row["port"])) == key:
            start = (index + 1) % len(endpoints)
            return endpoints[start:] + endpoints[:start]
    return endpoints


def _device_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, f"btn.apps_{platform}"),
                              callback_data=f"wg:device:{platform}")
         for platform in PLATFORMS],
        keyboards.back_row(lang, "nav:warp"),
    ])


def _network_menu(lang: str, platform: str) -> InlineKeyboardMarkup:
    menu = keyboards.warp_network(lang)
    for row in menu.inline_keyboard:
        for button in row:
            if button.callback_data in ("wg:net:mtn", "wg:net:other"):
                button.callback_data += f":{platform}"
            elif button.callback_data == "nav:warp":
                button.callback_data = "wg:net"
    return menu


def _delivered_menu(lang: str, family: str, platform: str) -> InlineKeyboardMarkup:
    menu = keyboards.warp_delivered(lang, family)
    for row in menu.inline_keyboard:
        for button in row:
            if button.callback_data == f"wg:net:next:{family}":
                button.callback_data += f":{platform}"
            if platform == "ios" and button.url == keyboards.AMNEZIA_PLAY_URL:
                button.text, button.url = "WireGuard (iPhone)", WIREGUARD_IOS
    other = V4 if family == V6 else V6
    choice = "other" if other == V4 else "mtn"
    text = f"Try IPv{other[-1]}" if lang == "en" else f"امتحان IPv{other[-1]}"
    menu.inline_keyboard.insert(1, [
        InlineKeyboardButton(text=text, callback_data=f"wg:net:{choice}:{platform}"),
    ])
    return menu


@router.callback_query(F.data == "wg:net")
async def on_pick_network(call: CallbackQuery, lang: str) -> None:
    """Build starts with an explicit device choice, including for existing users."""
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return
    prompt = ("Choose your device:" if lang == "en"
              else "کانفیگ را برای کدام دستگاه می‌خواهی؟")
    await edit(call, prompt, _device_menu(lang))
    await call.answer()


@router.callback_query(F.data.startswith("wg:device:"))
async def on_device_chosen(call: CallbackQuery, lang: str) -> None:
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return
    platform = (call.data or "").split(":")[-1]
    if platform not in PLATFORMS:
        await on_pick_network(call, lang)
        return
    v4 = await warpstore.counts(V4)
    v6 = await warpstore.counts(V6)
    await edit(
        call,
        t(lang, "wg.pick_net", v4=num(v4["healthy"], lang),
          v6=num(v6["healthy"], lang), target=num(TUNE.pool_target, lang)),
        _network_menu(lang, platform),
    )
    await call.answer()


@router.callback_query(F.data.startswith("wg:net:"))
async def on_network_chosen(call: CallbackQuery, lang: str) -> None:
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return
    tail = (call.data or "").split(":")[2:]
    rotate = bool(tail and tail[0] == "next")
    expected = 3 if rotate else 2
    # Old keyboards have no device information. Never silently assume Android.
    if len(tail) != expected or tail[-1] not in PLATFORMS:
        await on_pick_network(call, lang)
        return
    platform = tail[-1]
    if rotate:
        family = tail[1]
        if family not in (V4, V6):
            await on_pick_network(call, lang)
            return
        operator = "mtn" if family == V6 else "other"
    else:
        choice = CHOICES.get(tail[0])
        if choice is None:
            await on_pick_network(call, lang)
            return
        family, operator = choice["family"], choice["operator"]
    user_id = call.from_user.id
    if user_id in _building:
        await call.answer(t(lang, "warp.building"))
        return
    _building.add(user_id)
    try:
        await call.answer()
        notice = await call.message.answer(t(lang, "wg.making", family=_family_label(family, lang)))
        await _deliver(call, notice, lang, family, operator, rotate, platform)
    finally:
        _building.discard(user_id)


async def _deliver(
    call: CallbackQuery,
    notice: Message,
    lang: str,
    family: str,
    operator: str,
    rotate: bool,
    platform: str = "android",
) -> None:
    if platform not in PLATFORMS:
        raise ValueError("unsupported device")
    record = await db.get_warp_user(call.from_user.id)
    endpoints = await warp_pool.pick(family, count=settings.warp_per_config)
    if rotate:
        endpoints = _next_endpoints(endpoints, (record or {}).get("endpoints") or [])
    if not endpoints:
        # Check the pool before registering: repeated taps on an empty pool used
        # to create unused WARP devices and consume registration quota.
        text = (
            "No endpoint is available in this pool. Try the other IP family; "
            "server tests do not establish reachability on your phone."
            if lang == "en" else
            "این مخزن فعلاً آدرس آماده ندارد. خانواده IP دیگر را امتحان کن؛ "
            "تست سرور به معنی اتصال قطعی روی گوشی تو نیست."
        )
        await notice.edit_text(text, reply_markup=_network_menu(lang, platform))
        return
    identity = dict((record or {}).get("identity") or {})
    if not identity:
        try:
            identity = await warpcore.provision()
        except warpcore.WarpError as error:
            log.warning("warp provisioning failed: %s", error)
            await notice.edit_text(t(lang, "wg.identity_failed", reason=esc(error)))
            return
    # Extra metadata is preserved in the existing encrypted identity JSON.
    identity["platform"] = platform
    mtu = 1280 if platform == "ios" else max(1280, min(1420, settings.warp_mtu))
    profile = warpcore.obfuscation(identity.get("private_key", ""))
    if platform == "ios":
        body = warpconf.wireguard_conf(identity, endpoints, mtu=mtu)
        kind = "wg"
    else:
        body = warpconf.amnezia_conf(identity, endpoints, profile, mtu=mtu)
        kind = "awg"
    # Short, ASCII tunnel names work with strict WireGuard importers too.
    filename = f"av-{family}-{kind}.conf"
    await db.save_warp_user(call.from_user.id, identity, endpoints)
    await db.log_event("warp_build", call.from_user.id, f"{operator}/{family}/{platform}")
    await call.message.answer_document(
        BufferedInputFile(body.encode("utf-8"), filename=filename),
        caption=f"{'WireGuard' if platform == 'ios' else 'AmneziaWG'} / IPv{family[-1]}",
    )
    head = endpoints[0]
    if platform == "ios":
        text = (
            f"Import the .conf file in {_app_link(platform)} using "
            "'Create from file or archive'. This is standard WireGuard, not AmneziaWG."
            if lang == "en" else
            f"فایل .conf را در {_app_link(platform)} با گزینه "
            "«Create from file or archive» وارد کن. این فایل WireGuard استاندارد است، نه AmneziaWG."
        )
    else:
        text = t(
            lang, "wg.sent",
            operator=esc(operators.label(operator, lang) or operator),
            family=_family_label(family, lang), endpoint=esc(warpconf.label(endpoints)),
            ping=ping_label(head.get("latency"), lang),
            health=_out_of(head.get("health"), lang),
            spares=num(max(0, len(endpoints) - 1), lang),
            jc=num(profile["jc"], lang), jmin=num(profile["jmin"], lang),
            jmax=num(profile["jmax"], lang), mtu=num(mtu, lang), app=_app_link(platform),
        )
    text += (
        "\nConnectivity still depends on your network. IPv6 needs an IPv6 route on "
        "the phone; if UDP is blocked, changing the file format cannot unblock it. "
        "Try another endpoint or IP family. Importing a file is not a traffic test."
        if lang == "en" else
        "\nاتصال به شبکه تو بستگی دارد. IPv6 به مسیر IPv6 روی گوشی نیاز دارد؛ "
        "اگر UDP مسدود باشد تغییر فرمت فایل آن را باز نمی‌کند. آدرس بعدی یا "
        "خانواده IP دیگر را امتحان کن. وارد شدن فایل به معنی عبور ترافیک نیست."
    )
    try:
        await notice.edit_text(text, reply_markup=_delivered_menu(lang, family, platform))
    except TelegramBadRequest as error:
        log.info("could not update the delivery notice: %s", error)


# --------------------------------------------------------------------- #
# admin: the pool screen
# --------------------------------------------------------------------- #


async def show_pool(event: CallbackQuery | Message, lang: str) -> None:
    status = await warp_pool.status()
    v4 = status["families"][V4]
    v6 = status["families"][V6]
    text = t(
        lang,
        "pool.screen",
        source=esc(status["source"]),
        identity=_identity_line(status, lang),
        routes=_routes_line(status, lang),
        agent=t(lang, "admin.on" if status["agent"] else "admin.off"),
        interval=num(status["agent_interval"], lang),
        passes=num(status["passes"], lang),
        deep=(
            t(lang, "admin.on")
            if status["deep"]
            else (t(lang, "admin.off") if status["deep_possible"] else t(lang, "pool.deep_off"))
        ),
        floor=_out_of(status["floor"], lang),
        target=num(status["target"], lang),
        v4=num(v4["healthy"], lang),
        v4mark=_mark(v4["full"]),
        v4best=ping_label(v4["best"], lang),
        v4avg=ping_label(v4["avg"], lang),
        v4ep=esc(v4["best_endpoint"] or "-"),
        v6=num(v6["healthy"], lang),
        v6mark=_mark(v6["full"]),
        v6best=ping_label(v6["best"], lang),
        v6avg=ping_label(v6["avg"], lang),
        v6ep=esc(v6["best_endpoint"] or "-"),
        updated=ago(max(v4["updated_at"], v6["updated_at"]), lang),
    )
    manual = await warpmanual.both()
    text += "\n" + t(
        lang,
        "pool.manual_block",
        v4=num(manual[V4]["healthy"], lang),
        v4all=num(manual[V4]["total"], lang),
        v6=num(manual[V6]["healthy"], lang),
        v6all=num(manual[V6]["total"], lang),
    )
    await edit(event, text, keyboards.pool_menu(lang))


@router.callback_query(F.data == "pool:home")
async def on_pool_home(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    await state.clear()
    await show_pool(call, lang)
    await call.answer()


@router.callback_query(F.data == "pool:list")
async def on_pool_list(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    """Every endpoint in both pools, in ping order, with what was proven about it."""
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    await state.clear()

    blocks: list[str] = []
    for family in (V4, V6):
        rows = await warpstore.pool(family, limit=TUNE.pool_target * 3)
        counts = await warpstore.counts(family)
        blocks.append(
            t(
                lang,
                "pool.list_family",
                family=_family_label(family, lang),
                count=num(len(rows), lang),
                target=num(counts["target"], lang),
            )
        )
        if not rows and not warpep.reachable(family):
            blocks.append(t(lang, "pool.note_no_route"))
            continue
        for index, row in enumerate(rows, start=1):
            blocks.append(f"{num(index, lang)}. {_row_line(row, lang)}")

    listing = "\n".join(blocks).strip() or t(lang, "pool.list_empty")
    await edit(call, t(lang, "pool.list", list=listing), keyboards.pool_menu(lang))
    await call.answer()


def _row_line(row: dict, lang: str) -> str:
    """One stored endpoint, with everything that was actually proven about it."""
    flag = int(row.get("verified", -1) or -1)
    verified = True if flag == 1 else (False if flag == 0 else None)
    points = int(row.get("health") or 0)
    hand = " \U0001f590" if int(row.get("manual") or 0) else ""
    return (
        f"{warpep.badge(points, verified)}{hand} "
        f"<code>{esc(warpep.host_port(row['ip'], row['port']))}</code> \u00b7 "
        f"{ping_label(row.get('latency'), lang)} \u00b7 "
        f"\u2764\ufe0f {num(points, lang)}"
    )


# --------------------------------------------------------------------- #
# admin: refresh
# --------------------------------------------------------------------- #


def _refresh_text(report: RefreshReport, lang: str) -> str:
    family = _family_label(report.family, lang)
    if report.status == "disabled":
        return t(lang, "warp.off")
    if report.status == "busy":
        return t(lang, "pool.refresh_busy", family=family)
    if report.status == "cooldown":
        return t(lang, "pool.refresh_cooldown", wait=num(max(1, report.wait), lang))
    if report.status == "unreachable":
        return t(lang, "pool.refresh_unreachable", family=family) + _note_line(report.note, lang)
    if report.status == "failed":
        return t(
            lang, "pool.refresh_failed", family=family, reason=esc(report.reason or "-")
        ) + _note_line(report.note, lang)
    return t(
        lang,
        "pool.refresh_done",
        family=family,
        probed=num(report.probed, lang),
        answered=num(report.answered, lang),
        healthy=num(report.healthy, lang),
        proven=num(report.proven, lang),
        stored=num(report.stored, lang),
        dropped=num(report.dropped, lang),
        pool=num(report.pool, lang),
        target=num(report.target, lang),
        mark=_mark(report.full),
        best=ping_label(report.best, lang),
        ports=" \u00b7 ".join(num(port, lang) for port in report.ports[:4]) or "-",
        secs=num(max(1, round(report.elapsed)), lang),
    ) + _note_line(report.note, lang)


async def _run_refresh(notice: Message, lang: str, family: Optional[str]) -> None:
    families = (V4, V6) if family is None else (family,)
    parts: list[str] = []
    for code in families:
        report = await warp_pool.refresh(code, force=True)
        parts.append(_refresh_text(report, lang))
    try:
        await notice.edit_text("\n\n".join(parts), reply_markup=keyboards.pool_menu(lang))
    except TelegramBadRequest as error:
        log.info("could not update the refresh notice: %s", error)


@router.callback_query(F.data.startswith("pool:refresh"))
async def on_pool_refresh(
    call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool
) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return
    await state.clear()
    tail = (call.data or "").split(":")[2:]
    family = warpep.normalise_family(tail[0]) if tail else None
    await call.answer(t(lang, "btn.pool_refresh"))
    notice = await call.message.answer(t(lang, "pool.refresh_started"))
    _spawn(_run_refresh(notice, lang, family), f"pool-refresh-{family or 'all'}")


# --------------------------------------------------------------------- #
# admin: filling a pool by hand
# --------------------------------------------------------------------- #


@router.callback_query(F.data.startswith("pool:add:"))
async def on_manual_ask(
    call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool
) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    tail = (call.data or "").split(":")[2:]
    family = warpep.normalise_family(tail[0] if tail else V4)
    counts = await warpstore.manual_counts(family)
    await state.set_state(PoolFlow.manual)
    await state.update_data(family=family)
    text = t(
        lang,
        "pool.manual_prompt",
        family=_family_label(family, lang),
        operator=_operator_hint(family, lang),
        port=num(warpmanual.DEFAULT_PORT, lang),
        cap=num(TUNE.manual_max, lang),
        floor=num(TUNE.health_floor, lang),
        pinned=num(counts["healthy"], lang),
        total=num(counts["total"], lang),
    )
    if not warpep.reachable(family):
        text += "\n" + t(lang, "pool.manual_no_route", family=_family_label(family, lang))
    await edit(call, text, keyboards.pool_manual_cancel(lang))
    await call.answer()


@router.message(PoolFlow.manual, F.text)
async def on_manual_text(
    message: Message, state: FSMContext, lang: str, is_admin: bool
) -> None:
    if not _guard(is_admin):
        return
    data = await state.get_data()
    family = warpep.normalise_family(data.get("family") or V4)
    body = message.text or ""
    tokens = warpmanual.tokens_of(body)
    if not tokens:
        await message.answer(
            t(lang, "pool.manual_empty"), reply_markup=keyboards.pool_manual_cancel(lang)
        )
        return
    await state.clear()
    notice = await message.answer(
        t(
            lang,
            "pool.manual_started",
            family=_family_label(family, lang),
            count=num(len(tokens), lang),
        )
    )
    _spawn(_run_manual(notice, lang, family, body), f"pool-manual-{family}")


def _entry_line(entry: warpmanual.Entry, lang: str) -> str:
    mark = VERDICT_MARKS.get(entry.verdict, "\u2022")
    line = f"{mark} <code>{esc(entry.label)}</code> \u00b7 {t(lang, f'pool.manual_v_{entry.verdict}')}"
    if entry.verdict in {"stored", "weak"}:
        line += (
            f" \u00b7 {ping_label(entry.latency, lang)} \u00b7 "
            f"\u2764\ufe0f {num(entry.health, lang)}"
        )
    return line


def _manual_text(report: warpmanual.ImportReport, lang: str) -> str:
    family = _family_label(report.family, lang)
    if report.status == "empty":
        return t(lang, "pool.manual_empty")
    if report.status == "none":
        return t(lang, "pool.manual_none", family=family)
    if report.status == "identity":
        return t(lang, "pool.manual_identity") + _note_line("identity", lang)
    lines = [_entry_line(entry, lang) for entry in report.entries[:REPORT_LINES]]
    if len(report.entries) > REPORT_LINES:
        lines.append(
            t(lang, "pool.manual_more", count=num(len(report.entries) - REPORT_LINES, lang))
        )
    text = t(
        lang,
        "pool.manual_done",
        family=family,
        operator=_operator_hint(report.family, lang),
        given=num(len(report.entries), lang),
        stored=num(report.stored, lang),
        untested=num(report.untested, lang),
        dead=num(report.dead, lang),
        weak=num(report.weak, lang),
        skipped=num(report.skipped, lang),
        pinned=num(report.manual_healthy, lang),
        total=num(report.manual, lang),
        pool=num(report.pool, lang),
        target=num(TUNE.pool_target, lang),
        secs=num(max(1, round(report.elapsed)), lang),
        list="\n".join(lines),
    )
    if not report.tested:
        text += "\n" + t(lang, "pool.manual_untested_note", family=family)
    return text


async def _run_manual(notice: Message, lang: str, family: str, body: str) -> None:
    try:
        report = await warpmanual.import_pool(family, body)
        text = _manual_text(report, lang)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        log.exception("manual endpoint import failed")
        text = t(lang, "pool.manual_failed", reason=esc(str(error)[:180]))
    counts = await warpmanual.both()
    try:
        await notice.edit_text(
            text,
            reply_markup=keyboards.pool_manual(
                lang, counts[V4]["total"], counts[V6]["total"]
            ),
        )
    except TelegramBadRequest as error:
        log.info("could not update the manual import notice: %s", error)


async def show_manual(event: CallbackQuery | Message, lang: str) -> None:
    counts = await warpmanual.both()
    blocks: list[str] = []
    for family in (V4, V6):
        state = counts[family]
        blocks.append(
            t(
                lang,
                "pool.manual_family",
                family=_family_label(family, lang),
                operator=_operator_hint(family, lang),
                healthy=num(state["healthy"], lang),
                total=num(state["total"], lang),
                untested=num(state["untested"], lang),
            )
        )
        rows = await warpmanual.listing(family, limit=30)
        if not rows:
            blocks.append(t(lang, "pool.manual_family_empty"))
            continue
        for index, row in enumerate(rows, start=1):
            blocks.append(f"{num(index, lang)}. {_row_line(row, lang)}")
    await edit(
        event,
        t(lang, "pool.manual_screen", list="\n".join(blocks).strip()),
        keyboards.pool_manual(lang, counts[V4]["total"], counts[V6]["total"]),
    )


@router.callback_query(F.data == "pool:manual")
async def on_manual_home(
    call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool
) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    await state.clear()
    await show_manual(call, lang)
    await call.answer()


@router.callback_query(F.data == "pool:manual:check")
async def on_manual_check(
    call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool
) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    await state.clear()
    await call.answer(t(lang, "btn.pool_manual_check"))
    notice = await call.message.answer(t(lang, "pool.manual_check_started"))
    _spawn(_run_manual_check(notice, lang), "pool-manual-check")


async def _run_manual_check(notice: Message, lang: str) -> None:
    outcome = await warpmanual.recheck()
    counts = await warpmanual.both()
    text = t(
        lang,
        "pool.manual_check_done",
        checked=num(outcome["checked"], lang),
        alive=num(outcome["alive"], lang),
        dead=num(outcome["dead"], lang),
        skipped=num(outcome["skipped"], lang),
        v4=num(counts[V4]["healthy"], lang),
        v4all=num(counts[V4]["total"], lang),
        v6=num(counts[V6]["healthy"], lang),
        v6all=num(counts[V6]["total"], lang),
    )
    try:
        await notice.edit_text(
            text,
            reply_markup=keyboards.pool_manual(
                lang, counts[V4]["total"], counts[V6]["total"]
            ),
        )
    except TelegramBadRequest as error:
        log.info("could not update the manual check notice: %s", error)


@router.callback_query(F.data.startswith("pool:manual:ask:"))
async def on_manual_clear_ask(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    family = warpep.normalise_family((call.data or "").split(":")[-1])
    counts = await warpstore.manual_counts(family)
    await edit(
        call,
        t(
            lang,
            "pool.manual_clear_ask",
            family=_family_label(family, lang),
            count=num(counts["total"], lang),
        ),
        keyboards.pool_manual_confirm(lang, family),
    )
    await call.answer()


@router.callback_query(F.data.startswith("pool:manual:wipe:"))
async def on_manual_clear(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    family = warpep.normalise_family((call.data or "").split(":")[-1])
    removed = await warpmanual.clear(family)
    await call.answer(
        t(
            lang,
            "pool.manual_cleared",
            family=_family_label(family, lang),
            count=num(removed, lang),
        )
    )
    await show_manual(call, lang)


# --------------------------------------------------------------------- #
# admin: the full check
# --------------------------------------------------------------------- #


def _audit_text(report: AuditReport, lang: str) -> str:
    if report.status == "disabled":
        return t(lang, "warp.off")
    if report.status == "busy":
        return t(lang, "pool.audit_busy")
    if report.status == "failed":
        return t(
            lang, "pool.audit_failed", reason=esc(report.reason or "-")
        ) + _note_line(report.note, lang)
    v4 = report.families.get(V4, {})
    v6 = report.families.get(V6, {})
    return t(
        lang,
        "pool.audit_done",
        verdict=t(lang, f"pool.verdict_{report.verdict}"),
        checked=num(report.checked, lang),
        alive=num(report.alive, lang),
        dead=num(report.dead, lang),
        removed=num(report.removed, lang),
        target=num(report.target, lang),
        v4=num(v4.get("healthy", 0), lang),
        v4mark=_mark(bool(v4.get("full"))),
        v4best=ping_label(v4.get("best"), lang),
        v6=num(v6.get("healthy", 0), lang),
        v6mark=_mark(bool(v6.get("full"))),
        v6best=ping_label(v6.get("best"), lang),
        secs=num(max(1, round(report.elapsed)), lang),
    ) + _note_line(report.note, lang)


async def _run_audit(notice: Message, lang: str) -> None:
    report = await warp_pool.audit()
    try:
        await notice.edit_text(_audit_text(report, lang), reply_markup=keyboards.pool_menu(lang))
    except TelegramBadRequest as error:
        log.info("could not update the audit notice: %s", error)


@router.callback_query(F.data == "pool:audit")
async def on_pool_audit(
    call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool
) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return
    await state.clear()
    await call.answer(t(lang, "pool.audit_started"))
    notice = await call.message.answer(t(lang, "pool.audit_started"))
    _spawn(_run_audit(notice, lang), "pool-audit")
