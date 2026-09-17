"""WARP / WireGuard exports: every format, rendered for the client that asked.

The engine in ``warpscan`` maintains a pool of endpoints that answered a real
handshake more than once, scored on latency, jitter and loss. The build and
delivery flow lives in ``handlers.pool``; this module owns the export buttons,
the endpoint list, the rescan, the licence and the identity.

Three bugs used to live in here and all three produced the same symptom, which is
a user tapping a button and nothing happening at all.

The first: the platform picker asked which OS and then ignored the answer. Every
branch rendered AmneziaWG, so an iPhone user who correctly tapped iOS still got a
file carrying ``Jc`` in ``[Interface]``, which the official WireGuard app refuses
wholesale. ``warpconf`` now decides the shape from the platform.

The second: the picker's handler was gated on ``WarpFlow.platform``. Any
navigation between opening the picker and tapping it cleared the state, the
callback matched no handler, and the tap was swallowed in silence. The export kind
and the platform ride in the callback data now, so the flow is stateless and
cannot rot.

The third, and the reason iPhone reports outlived the first two: the platform
segment was run through ``normalise_platform`` the moment it arrived, and that
function answers ``android`` for anything it does not recognise - including the
empty string it gets from a callback whose platform segment is missing. So a
malformed or truncated callback did not fail, it silently became Android, and
Android is the one answer that puts obfuscation keys in the file. The raw value is
now carried as far as the renderer and resolved with ``resolve_platform``, which
is allowed to say it does not know. When it does not know, the device picker is
shown again rather than a file being guessed into existence.

Nothing here waits on a scan. The rescan button answers straight away and the
sweep reports back into the same message when it finishes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from .. import db, keyboards, warpconf, warpstore
from .. import warp as warpcore
from ..config import settings
from ..i18n import device_label, num, t
from ..platforms import may_obfuscate, resolve_platform
from ..utils import ago, chunked, edit, esc, ping_label
from ..warpscan import ScanReport, warp_scanner
from ..warptune import TUNE
from .pool import show_device

log = logging.getLogger("autovless.handlers.warp")
router = Router(name="warp")

# Monotonic stamp of the last accepted rescan, per user.
_last_rescan: dict[int, float] = {}

# Live scan jobs. Held so the event loop cannot garbage collect them mid-sweep.
_scan_jobs: set[asyncio.Task] = set()

# Every export the buttons can ask for, and what the caption should say about it.
EXPORTS: dict[str, str] = {
    "awg": "warp.caption_awg",
    "awg2": "warp.caption_awg2",
    "plain": "warp.caption_plain",
    "singbox": "warp.caption_singbox",
    "clash": "warp.caption_clash",
}

# Exports whose whole point is the obfuscation. Asking for one of these on a
# platform that cannot take it is a request that can only produce a dead file.
OBFUSCATED_KINDS: frozenset[str] = frozenset({"awg", "awg2"})


class WarpFlow(StatesGroup):
    # ``platform`` is deliberately gone: gating the picker on FSM state is what
    # made it a dead end. Only the licence prompt genuinely needs state.
    license = State()


# --------------------------------------------------------------- helpers


def _profile(identity: dict) -> dict:
    return warpcore.obfuscation(identity.get("private_key", ""))


def _loss_note(row: dict, lang: str) -> str:
    loss = float(row.get("loss") or 0)
    if loss <= 0:
        return ""
    return " \u00b7 " + t(lang, "warp.loss", pct=num(round(loss * 100), lang))


def _kind_of(data: str, fallback: str = "awg") -> str:
    kind = (data or "").strip().lower()
    return kind if kind in EXPORTS else fallback


async def show_menu(event: CallbackQuery | Message, lang: str) -> None:
    stats = await warp_scanner.stats()
    record = await db.get_warp_user(event.from_user.id)

    if record is None:
        status = t(lang, "warp.status_none")
    else:
        endpoints = record.get("endpoints") or []
        status = t(
            lang,
            "warp.status_ready",
            account=esc(record["identity"].get("account_type", "free")),
            endpoint=esc(warpconf.label(endpoints)),
            count=num(len(endpoints), lang),
            updated=ago(record.get("updated_at"), lang),
        )

    text = t(
        lang,
        "warp.menu",
        stable=num(stats["stable"], lang),
        total=num(stats["total"], lang),
        best=ping_label(stats["best"], lang),
        ports=" \u00b7 ".join(num(port, lang) for port in stats["ports"][:3]) or "-",
        updated=ago(stats["updated_at"], lang),
        state=t(lang, "admin.on" if stats["scanning"] else "admin.off"),
        status=status,
    )
    # The flag is honoured now. It used to be passed and dropped, which is why a
    # user with an identity saw a screen with no way to download anything.
    await edit(event, text, keyboards.warp_menu(lang, record is not None))


@router.callback_query(F.data == "nav:warp")
async def on_warp_home(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return
    await show_menu(call, lang)
    await call.answer()


@router.message(Command("warp"))
async def on_warp_command(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    if not await db.get_flag("warp_enabled"):
        await message.answer(t(lang, "warp.off"))
        return
    await show_menu(message, lang)


# ----------------------------------------------------------------- build


@router.callback_query(F.data == "wg:build")
async def on_build(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    """Legacy callback, kept for keyboards still sitting in chat history.

    It used to provision an identity, save it, and stop. No file was ever sent and
    the screen it returned to had no export button on it, so "build" genuinely
    produced nothing a user could install. It now opens the device picker and the
    pool flow takes it from there, which is the path that renders and delivers.
    """
    await state.clear()
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return
    await show_device(call, lang)
    await call.answer()


@router.callback_query(F.data == "wg:rebuild")
async def on_rebuild(call: CallbackQuery, lang: str) -> None:
    record = await db.get_warp_user(call.from_user.id)
    if record is None:
        await call.answer(t(lang, "warp.none"), show_alert=True)
        return

    await call.answer()
    current = record.get("endpoints") or []
    endpoints = await warp_scanner.failover(current)
    await db.update_warp_endpoints(call.from_user.id, endpoints)

    before = str(current[0]["ip"]) if current else ""
    after = str(endpoints[0]["ip"]) if endpoints else ""
    key = "warp.refreshed" if before != after else "warp.refreshed_same"
    best = endpoints[0]["latency"] if endpoints else None
    await call.message.answer(
        t(
            lang,
            key,
            endpoint=esc(warpconf.label(endpoints)),
            ping=ping_label(best, lang),
        ),
        reply_markup=keyboards.warp_menu(lang, True),
    )


# ------------------------------------------------ export: device picker first


async def _ask_device(call: CallbackQuery, lang: str, kind: str) -> None:
    """Show the device picker for an export whose platform we do not know."""
    await edit(
        call,
        t(lang, "warp.select_platform"),
        keyboards.device_picker(lang, f"f:{kind}"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("wg:file:"))
async def on_file(call: CallbackQuery, lang: str) -> None:
    """Intercept a file export and ask which device it is for.

    The kind travels in the picker's own callback data. Stashing it in FSM state
    is what used to break this: a navigation cleared the state, the follow-up tap
    matched nothing, and the user got no file and no error.
    """
    record = await db.get_warp_user(call.from_user.id)
    if record is None:
        await call.answer(t(lang, "warp.none"), show_alert=True)
        return

    await _ask_device(call, lang, _kind_of((call.data or "").rsplit(":", 1)[-1]))


@router.callback_query(F.data.startswith("wg:dev:") & F.data.contains(":f:"))
async def on_export_device(call: CallbackQuery, lang: str) -> None:
    """``wg:dev:<platform>:f:<kind>`` - the device picker answered for an export."""
    parts = (call.data or "").split(":")
    # Raw, not normalised. ``_deliver_export`` has to be able to tell "the user
    # picked Android" from "this callback names no platform at all".
    platform = parts[2] if len(parts) > 2 else ""
    kind = _kind_of(parts[4] if len(parts) > 4 else "")
    await _deliver_export(call, lang, platform, kind)


@router.callback_query(F.data.startswith("wg:exp:"))
async def on_export_direct(call: CallbackQuery, lang: str) -> None:
    """``wg:exp:<platform>:<kind>`` - the device is already known, no need to ask."""
    parts = (call.data or "").split(":")
    platform = parts[2] if len(parts) > 2 else ""
    kind = _kind_of(parts[3] if len(parts) > 3 else "")
    await _deliver_export(call, lang, platform, kind)


async def _deliver_export(
    call: CallbackQuery, lang: str, platform: str, kind: str
) -> None:
    """Render one export for one platform and send it.

    ``platform`` arrives exactly as the callback carried it. It is resolved here
    and an unresolvable value is not defaulted: it sends the user back to the
    device picker. Defaulting it to Android is what kept shipping AmneziaWG to
    iPhones long after the picker itself was correct.

    The rendering is guarded on purpose. A missing renderer used to raise here and
    the user simply never received anything; now the failure has a message.
    """
    record = await db.get_warp_user(call.from_user.id)
    if record is None:
        await call.answer(t(lang, "warp.none"), show_alert=True)
        return

    kind = _kind_of(kind)

    name = resolve_platform(platform)
    if name is None:
        await _ask_device(call, lang, kind)
        return

    # Asking for AmneziaWG on a platform whose client rejects it can only produce
    # a file that will not load, so the request is downgraded and said out loud
    # rather than honoured into a dead end.
    downgraded = kind in OBFUSCATED_KINDS and not may_obfuscate(name)
    if downgraded:
        kind = "plain"

    identity = record["identity"]
    endpoints = record.get("endpoints") or []
    profile = _profile(identity)

    await call.answer()

    try:
        if kind == "singbox":
            body = warpcore.singbox_json(identity, endpoints)
        elif kind == "clash":
            body = warpcore.clash_yaml(identity, endpoints)
        else:
            body = warpconf.conf_for(
                identity, endpoints, platform=name, kind=kind, profile=profile
            )
    except Exception as error:  # noqa: BLE001
        log.exception("could not render the %s export for %s", kind, name)
        await call.message.answer(
            t(lang, "wg.render_failed", reason=esc(str(error)[:180])),
            reply_markup=keyboards.warp_menu(lang, True),
        )
        return

    caption = t(lang, EXPORTS[kind])
    if downgraded:
        caption = t(lang, "wg.caption_clean", family="", device=device_label(name, lang))
        caption = f"{caption}\n\n{t(lang, 'wg.ios_dpi_hint')}"

    await call.message.answer_document(
        BufferedInputFile(
            body.encode("utf-8"),
            filename=warpconf.filename("", kind, name),
        ),
        caption=caption,
        reply_markup=keyboards.warp_exports(lang, True, name),
    )


@router.callback_query(F.data == "wg:link")
async def on_links(call: CallbackQuery, lang: str) -> None:
    record = await db.get_warp_user(call.from_user.id)
    if record is None:
        await call.answer(t(lang, "warp.none"), show_alert=True)
        return

    await call.answer()
    links = warpcore.links(record["identity"], record.get("endpoints") or [])
    body = "\n\n".join(f"<code>{esc(link)}</code>" for link in links)
    parts = chunked(t(lang, "warp.caption_link", links=body))
    for index, part in enumerate(parts):
        await call.message.answer(
            part,
            reply_markup=keyboards.warp_menu(lang, True) if index == len(parts) - 1 else None,
            disable_web_page_preview=True,
        )


@router.callback_query(F.data == "wg:apps")
async def on_apps(call: CallbackQuery, lang: str) -> None:
    """Only the apps that speak AmneziaWG, as real store links."""
    await edit(call, t(lang, "warp.apps"), keyboards.apps_list(lang, "android", "warp"))
    await call.answer()


@router.callback_query(F.data == "wg:why")
async def on_why(call: CallbackQuery, lang: str) -> None:
    body = t(lang, "warp.dpi_note") + "\n\n" + t(lang, "wg.ios_dpi_hint")
    await edit(call, body, keyboards.simple_back(lang, "nav:warp"))
    await call.answer()


# ------------------------------------------------------------- endpoints


@router.callback_query(F.data == "wg:eps")
async def on_endpoints(call: CallbackQuery, lang: str) -> None:
    rows = await warpstore.best(12, stable_only=True)
    if not rows:
        rows = await warpstore.best(12, stable_only=False)
    if not rows:
        await edit(call, t(lang, "warp.eps_empty"), keyboards.warp_endpoints(lang))
        await call.answer()
        return

    lines = []
    for row in rows:
        mark = "\u2705" if row.get("stable") and not row.get("fails") else "\u26aa\ufe0f"
        address = warpconf.host_port(row["ip"], row["port"])
        lines.append(
            f"{mark} <code>{esc(address)}</code> \u00b7 {ping_label(row['latency'], lang)}"
            f"{_loss_note(row, lang)}"
        )

    await edit(call, t(lang, "warp.eps", list="\n".join(lines)), keyboards.warp_endpoints(lang))
    await call.answer()


def _report_text(report: ScanReport, lang: str) -> str:
    """One report, one message. No more guessing what a zero meant."""
    if report.status == "disabled":
        return t(lang, "warp.off")
    if report.status == "cooldown":
        return t(lang, "warp.rescan_cooldown", wait=num(max(1, report.wait), lang))
    if report.status == "failed":
        return t(lang, "warp.rescan_failed", reason=esc(report.reason or "-"))
    if not report.found:
        return t(lang, "warp.rescan_empty")
    return t(
        lang,
        "warp.rescan_joined" if report.status == "joined" else "warp.rescan_done",
        count=num(report.found, lang),
        alive=num(report.alive, lang),
        ping=ping_label(report.best, lang),
        ports=" \u00b7 ".join(num(port, lang) for port in report.ports[:3]) or "-",
        secs=num(max(1, round(report.elapsed)), lang),
    )


async def _run_scan(notice: Message, lang: str, quick: bool, force: bool) -> None:
    report = await warp_scanner.scan(quick=quick, force=force)
    try:
        await notice.edit_text(
            _report_text(report, lang), reply_markup=keyboards.warp_endpoints(lang)
        )
    except TelegramBadRequest as error:
        log.info("could not update the scan notice: %s", error)


@router.callback_query(F.data == "wg:rescan")
async def on_rescan(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return

    moment = time.monotonic()
    previous: Optional[float] = _last_rescan.get(call.from_user.id)
    if not is_admin and previous is not None:
        left = int(TUNE.user_cooldown - (moment - previous))
        if left > 0:
            await call.answer(
                t(lang, "warp.rescan_cooldown", wait=num(left, lang)), show_alert=True
            )
            return
    _last_rescan[call.from_user.id] = moment

    await call.answer(t(lang, "warp.rescanning"))
    notice = await call.message.answer(t(lang, "warp.rescan_started"))

    task = asyncio.create_task(
        _run_scan(notice, lang, quick=not is_admin, force=is_admin),
        name=f"warp-rescan-{call.from_user.id}",
    )
    _scan_jobs.add(task)
    task.add_done_callback(_scan_jobs.discard)


# --------------------------------------------------------------- license


@router.callback_query(F.data == "wg:license")
async def on_license(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    record = await db.get_warp_user(call.from_user.id)
    if record is None:
        await call.answer(t(lang, "warp.none"), show_alert=True)
        return
    await state.set_state(WarpFlow.license)
    await edit(call, t(lang, "warp.license_prompt"), keyboards.simple_back(lang, "nav:warp"))
    await call.answer()


@router.message(WarpFlow.license, F.text, ~F.text.startswith("/"))
async def on_license_input(message: Message, state: FSMContext, lang: str) -> None:
    record = await db.get_warp_user(message.from_user.id)
    if record is None:
        await state.clear()
        await message.answer(t(lang, "warp.none"))
        return

    key = (message.text or "").strip()
    try:
        identity = await warpcore.apply_license(record["identity"], key)
    except warpcore.WarpError as error:
        await message.answer(t(lang, "warp.license_bad", reason=esc(error)))
        return

    await state.clear()
    await db.save_warp_user(message.from_user.id, identity, record.get("endpoints") or [])
    await db.log_event("warp_license", message.from_user.id, identity.get("account_type", ""))
    await message.answer(
        t(lang, "warp.license_ok", account=esc(identity.get("account_type", "warp_plus"))),
        reply_markup=keyboards.warp_menu(lang, True),
    )


# ---------------------------------------------------------------- delete


@router.callback_query(F.data == "wg:del")
async def on_delete(call: CallbackQuery, lang: str) -> None:
    record = await db.get_warp_user(call.from_user.id)
    if record is None:
        await call.answer(t(lang, "warp.none"), show_alert=True)
        return
    await edit(
        call,
        t(lang, "warp.delete_confirm"),
        keyboards.confirm_menu(lang, "wg:del:yes", "nav:warp"),
    )
    await call.answer()


@router.callback_query(F.data == "wg:del:yes")
async def on_delete_confirm(call: CallbackQuery, lang: str) -> None:
    await db.delete_warp_user(call.from_user.id)
    await db.log_event("warp_delete", call.from_user.id)
    await call.answer(t(lang, "warp.deleted"))
    await show_menu(call, lang)
