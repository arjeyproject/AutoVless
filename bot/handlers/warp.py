"""WARP menus and exports.

Device-aware builds are handled by the pool router. All exports use the shared
IPv4/IPv6-safe renderer, including callbacks from previously delivered messages.
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

from .. import db, keyboards, warpstore, warpconf, warpep
from .. import warp as warpcore
from ..config import settings
from ..i18n import num, t
from ..utils import ago, chunked, edit, esc, ping_label
from ..warpscan import ScanReport, warp_scanner
from ..warptune import TUNE

log = logging.getLogger("autovless.handlers.warp")
router = Router(name="warp")
_last_rescan: dict[int, float] = {}
_scan_jobs: set[asyncio.Task] = set()


class WarpFlow(StatesGroup):
    license = State()


def _profile(identity: dict) -> dict:
    return warpcore.obfuscation(identity.get("private_key", ""))


def _filename(suffix: str) -> str:
    return f"{settings.brand}-warp{suffix}"


def _loss_note(row: dict, lang: str) -> str:
    loss = float(row.get("loss") or 0)
    if loss <= 0:
        return ""
    return " \u00b7 " + t(lang, "warp.loss", pct=num(round(loss * 100), lang))


async def show_menu(event: CallbackQuery | Message, lang: str) -> None:
    stats = await warp_scanner.stats()
    record = await db.get_warp_user(event.from_user.id)
    if record is None:
        status = t(lang, "warp.status_none")
    else:
        endpoints = record.get("endpoints") or []
        status = t(
            lang, "warp.status_ready",
            account=esc(record["identity"].get("account_type", "free")),
            endpoint=esc(warpconf.label(endpoints)) if endpoints else "-",
            count=num(len(endpoints), lang), updated=ago(record.get("updated_at"), lang),
        )
    text = t(
        lang, "warp.menu", stable=num(stats["stable"], lang), total=num(stats["total"], lang),
        best=ping_label(stats["best"], lang),
        ports=" \u00b7 ".join(num(port, lang) for port in stats["ports"][:3]) or "-",
        updated=ago(stats["updated_at"], lang),
        state=t(lang, "admin.on" if stats["scanning"] else "admin.off"), status=status,
    )
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


@router.callback_query(F.data == "wg:build")
async def on_build(call: CallbackQuery, lang: str) -> None:
    # Old messages must not bypass the device picker or provision duplicate keys.
    from .pool import on_pick_network
    await on_pick_network(call, lang)


@router.callback_query(F.data == "wg:rebuild")
async def on_rebuild(call: CallbackQuery, lang: str) -> None:
    # The old scanner was IPv4-only and could silently replace an IPv6 config.
    # Re-enter the shared flow, which reuses the identity and chosen family.
    from .pool import on_pick_network
    await on_pick_network(call, lang)


@router.callback_query(F.data.startswith("wg:file:"))
async def on_file(call: CallbackQuery, lang: str) -> None:
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return
    kind = (call.data or "").rsplit(":", 1)[-1]
    if kind not in {"awg", "awg2", "plain", "singbox", "clash"}:
        await call.answer()
        return
    record = await db.get_warp_user(call.from_user.id)
    if record is None:
        await call.answer(t(lang, "warp.none"), show_alert=True)
        return
    identity = record["identity"]
    endpoints = record.get("endpoints") or []
    if not endpoints:
        await call.answer(t(lang, "warp.no_endpoint"), show_alert=True)
        return
    profile = _profile(identity)
    mtu = 1280 if identity.get("platform") == "ios" else max(1280, min(1420, settings.warp_mtu))
    family = warpconf.family_of(endpoints)
    await call.answer()
    if kind == "awg":
        body = warpconf.amnezia_conf(identity, endpoints, profile, mtu=mtu)
        name, caption = f"av-{family}-awg.conf", "warp.caption_awg"
    elif kind == "awg2":
        body = warpconf.amnezia_conf(identity, endpoints, profile, mtu=mtu, signature=True)
        name, caption = f"av-{family}-awg2.conf", "warp.caption_awg2"
    elif kind == "plain":
        body = warpconf.wireguard_conf(identity, endpoints, mtu=mtu)
        name, caption = f"av-{family}-wg.conf", "warp.caption_plain"
    elif kind == "singbox":
        body = warpconf.singbox_json(identity, endpoints, mtu=mtu)
        name, caption = _filename("-singbox.json"), "warp.caption_singbox"
    else:
        body = warpconf.clash_yaml(identity, endpoints, mtu=mtu)
        name, caption = _filename("-clash.yaml"), "warp.caption_clash"
    await call.message.answer_document(
        BufferedInputFile(body.encode("utf-8"), filename=name),
        caption=t(lang, caption), reply_markup=keyboards.warp_exports(lang),
    )


@router.callback_query(F.data == "wg:link")
async def on_links(call: CallbackQuery, lang: str) -> None:
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return
    record = await db.get_warp_user(call.from_user.id)
    if record is None:
        await call.answer(t(lang, "warp.none"), show_alert=True)
        return
    endpoints = record.get("endpoints") or []
    if not endpoints:
        await call.answer(t(lang, "warp.no_endpoint"), show_alert=True)
        return
    await call.answer()
    links = warpconf.links(record["identity"], endpoints)
    body = "\n\n".join(f"<code>{esc(link)}</code>" for link in links)
    parts = chunked(t(lang, "warp.caption_link", links=body))
    for index, part in enumerate(parts):
        await call.message.answer(
            part,
            reply_markup=keyboards.warp_exports(lang) if index == len(parts) - 1 else None,
            disable_web_page_preview=True,
        )


@router.callback_query(F.data == "wg:apps")
async def on_apps(call: CallbackQuery, lang: str) -> None:
    record = await db.get_warp_user(call.from_user.id)
    platform = ((record or {}).get("identity") or {}).get("platform")
    menu = (keyboards.apps_list(lang, platform, "warp") if platform in {"android", "ios"}
            else keyboards.apps_platforms(lang))
    await edit(call, t(lang, "warp.apps"), menu)
    await call.answer()


@router.callback_query(F.data == "wg:why")
async def on_why(call: CallbackQuery, lang: str) -> None:
    await edit(call, t(lang, "warp.dpi_note"), keyboards.simple_back(lang, "nav:warp"))
    await call.answer()


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
        address = warpep.host_port(row["ip"], row["port"])
        lines.append(
            f"{mark} <code>{esc(address)}</code> \u00b7 {ping_label(row['latency'], lang)}"
            f"{_loss_note(row, lang)}"
        )
    await edit(call, t(lang, "warp.eps", list="\n".join(lines)), keyboards.warp_endpoints(lang))
    await call.answer()


def _report_text(report: ScanReport, lang: str) -> str:
    if report.status == "disabled":
        return t(lang, "warp.off")
    if report.status == "cooldown":
        return t(lang, "warp.rescan_cooldown", wait=num(max(1, report.wait), lang))
    if report.status == "failed":
        return t(lang, "warp.rescan_failed", reason=esc(report.reason or "-"))
    if not report.found:
        return t(lang, "warp.rescan_empty")
    return t(
        lang, "warp.rescan_joined" if report.status == "joined" else "warp.rescan_done",
        count=num(report.found, lang), alive=num(report.alive, lang),
        ping=ping_label(report.best, lang),
        ports=" \u00b7 ".join(num(port, lang) for port in report.ports[:3]) or "-",
        secs=num(max(1, round(report.elapsed)), lang),
    )


async def _run_scan(notice: Message, lang: str, quick: bool, force: bool) -> None:
    report = await warp_scanner.scan(quick=quick, force=force)
    try:
        await notice.edit_text(_report_text(report, lang), reply_markup=keyboards.warp_endpoints(lang))
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
            await call.answer(t(lang, "warp.rescan_cooldown", wait=num(left, lang)), show_alert=True)
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
        reply_markup=keyboards.warp_exports(lang),
    )


@router.callback_query(F.data == "wg:del")
async def on_delete(call: CallbackQuery, lang: str) -> None:
    record = await db.get_warp_user(call.from_user.id)
    if record is None:
        await call.answer(t(lang, "warp.none"), show_alert=True)
        return
    await edit(
        call, t(lang, "warp.delete_confirm"),
        keyboards.confirm_menu(lang, "wg:del:yes", "nav:warp"),
    )
    await call.answer()


@router.callback_query(F.data == "wg:del:yes")
async def on_delete_confirm(call: CallbackQuery, lang: str) -> None:
    await db.delete_warp_user(call.from_user.id)
    await db.log_event("warp_delete", call.from_user.id)
    await call.answer(t(lang, "warp.deleted"))
    await show_menu(call, lang)
