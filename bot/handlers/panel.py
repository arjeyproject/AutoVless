"""Panel management: exports, QR, live ping, apply, rescan, rebuild, delete."""

from __future__ import annotations

import asyncio
import io
import logging

import qrcode
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery

from .. import db, deploy, keyboards, screens, vless
from ..autopilot import autopilot
from ..config import settings
from ..i18n import num, t
from ..scanner import scanner
from ..utils import chunked, edit, esc, ping_label, tcp_latency
from .build import BuildFlow, run_build

log = logging.getLogger("autovless.panel")
router = Router(name="panel")

_applying: set[int] = set()


async def _require_panel(call: CallbackQuery, lang: str) -> dict | None:
    panel = await db.get_panel(call.from_user.id)
    if panel is None:
        await edit(call, t(lang, "panel_none"), keyboards.simple_back(lang))
        await call.answer()
        return None
    return panel


@router.callback_query(F.data == "panel:sub")
async def on_sub(call: CallbackQuery, lang: str) -> None:
    panel = await _require_panel(call, lang)
    if panel is None:
        return
    host, uuid = panel["host"], panel["uuid"]
    text = t(
        lang,
        "sub_links",
        sub=esc(vless.sub_url(uuid, host)),
        clash=esc(vless.sub_url(uuid, host, "clash")),
        singbox=esc(vless.sub_url(uuid, host, "singbox")),
    )
    await edit(call, text, keyboards.simple_back(lang, "nav:panel"))
    await call.answer()


@router.callback_query(F.data == "panel:qr")
async def on_qr(call: CallbackQuery, lang: str) -> None:
    panel = await _require_panel(call, lang)
    if panel is None:
        return
    url = vless.sub_url(panel["uuid"], panel["host"])
    image = qrcode.make(url, box_size=8, border=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    await call.message.answer_photo(
        BufferedInputFile(buffer.getvalue(), filename="autovless-sub.png"),
        caption=t(lang, "qr_caption", brand=esc(settings.brand)),
        reply_markup=keyboards.simple_back(lang, "nav:panel"),
    )
    await call.answer()


@router.callback_query(F.data == "panel:single")
async def on_single(call: CallbackQuery, lang: str) -> None:
    panel = await _require_panel(call, lang)
    if panel is None:
        return
    links = vless.build_links(panel["uuid"], panel["host"], panel["endpoints"])
    body = t(lang, "single_configs") + "\n\n" + "\n\n".join(
        f"<b>#{num(index, lang)}</b>\n<code>{esc(link)}</code>"
        for index, link in enumerate(links, start=1)
    )
    parts = chunked(body)
    for position, part in enumerate(parts):
        last = position == len(parts) - 1
        await call.message.answer(
            part,
            reply_markup=keyboards.simple_back(lang, "nav:panel") if last else None,
            disable_web_page_preview=True,
        )
    await call.answer()


@router.callback_query(F.data.in_({"panel:clash", "panel:singbox"}))
async def on_export(call: CallbackQuery, lang: str) -> None:
    panel = await _require_panel(call, lang)
    if panel is None:
        return
    wants_clash = call.data == "panel:clash"
    if wants_clash:
        payload = vless.build_clash(panel["uuid"], panel["host"], panel["endpoints"])
        filename = "autovless-clash.yaml"
    else:
        payload = vless.build_singbox(panel["uuid"], panel["host"], panel["endpoints"])
        filename = "autovless-singbox.json"

    await call.message.answer_document(
        BufferedInputFile(payload.encode("utf-8"), filename=filename),
        reply_markup=keyboards.simple_back(lang, "nav:panel"),
    )
    await call.answer()


@router.callback_query(F.data == "panel:ping")
async def on_ping(call: CallbackQuery, lang: str) -> None:
    panel = await _require_panel(call, lang)
    if panel is None:
        return
    await call.answer()

    endpoints = panel["endpoints"]
    results = await asyncio.gather(
        *(tcp_latency(ep["ip"], int(ep["port"])) for ep in endpoints)
    )

    rows = []
    for index, (endpoint, latency) in enumerate(zip(endpoints, results), start=1):
        mark = "\u2705" if latency else "\u274c"
        if endpoint.get("kind") == "domain":
            mark = f"{mark}\U0001f300"
        rows.append(
            f"{mark} <b>#{num(index, lang)}</b> \u00b7 <code>{esc(endpoint['ip'])}:"
            f"{num(endpoint['port'], lang)}</code> \u00b7 {ping_label(latency, lang)}"
        )
        # A shipped endpoint that no longer answers should stop being shipped.
        if not latency:
            await scanner.demote(str(endpoint["ip"]), int(endpoint["port"]))

    await edit(
        call,
        t(lang, "ping_result", rows="\n".join(rows)),
        keyboards.panel_menu(lang),
    )


@router.callback_query(F.data == "panel:apply")
async def on_apply(call: CallbackQuery, lang: str) -> None:
    """Push the current best clean IPs onto this panel, keeping the same link.

    This is the same operation the autopilot runs in the background, exposed as a
    button for people who do not want to wait for the next cycle.
    """
    panel = await _require_panel(call, lang)
    if panel is None:
        return

    tg_id = call.from_user.id
    if tg_id in _applying:
        await call.answer(t(lang, "busy"), show_alert=True)
        return

    if not panel.get("token"):
        await edit(call, t(lang, "token_missing"), keyboards.token_menu(lang))
        await call.answer()
        return

    await call.answer()
    notice = await call.message.answer(t(lang, "applying"))
    _applying.add(tg_id)
    try:
        result = await autopilot.refresh_panel(tg_id, force_scan=True)
    except deploy.DeployError as error:
        await notice.edit_text(t(lang, "apply_failed", reason=esc(error.reason)))
        return
    except Exception as error:  # noqa: BLE001
        log.exception("apply failed")
        await notice.edit_text(t(lang, "apply_failed", reason=esc(error)))
        return
    finally:
        _applying.discard(tg_id)

    if result is None:
        await notice.edit_text(t(lang, "token_missing"), reply_markup=keyboards.token_menu(lang))
        return

    endpoints = result["endpoints"]
    latencies = [e.get("latency") or 0 for e in endpoints]
    await notice.edit_text(
        t(
            lang,
            "applied",
            count=num(len(endpoints), lang),
            best=ping_label(min((v for v in latencies if v), default=None), lang),
            health=t(lang, "panel_health_ok" if result["healthy"] else "panel_health_bad"),
        ),
        reply_markup=keyboards.panel_menu(lang),
    )
    await db.log_event("apply", tg_id, f"endpoints={len(endpoints)} healthy={result['healthy']}")


@router.callback_query(F.data == "panel:rescan")
async def on_rescan(call: CallbackQuery, lang: str) -> None:
    await call.answer(t(lang, "scan_started"))
    await scanner.scan_once(batch=max(320, settings.scan_batch // 3))
    text, markup = await screens.network_status(lang)
    await edit(call, text, markup)


@router.callback_query(F.data == "panel:rebuild")
async def on_rebuild(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    panel = await _require_panel(call, lang)
    if panel is None:
        return

    token = panel.get("token")
    if not token:
        await state.set_state(BuildFlow.token)
        await state.update_data(mode="rebuild")
        await edit(call, t(lang, "token_missing"), keyboards.token_menu(lang))
        await call.answer()
        return

    await call.answer(t(lang, "rebuilding"))
    await run_build(
        call.message,
        call.from_user.id,
        lang,
        token,
        reuse={
            "account_id": panel["account_id"],
            "script_name": panel["script_name"],
            "uuid": panel["uuid"],
        },
        force_scan=True,
    )


@router.callback_query(F.data == "panel:delete")
async def on_delete_ask(call: CallbackQuery, lang: str) -> None:
    panel = await _require_panel(call, lang)
    if panel is None:
        return
    await edit(
        call,
        t(lang, "delete_confirm", script=esc(panel["script_name"])),
        keyboards.confirm_menu(lang, "panel:delete_yes"),
    )
    await call.answer()


@router.callback_query(F.data == "panel:delete_yes")
async def on_delete(call: CallbackQuery, lang: str) -> None:
    panel = await _require_panel(call, lang)
    if panel is None:
        return
    await call.answer()

    token = panel.get("token")
    if token:
        try:
            await deploy.destroy(token, panel["account_id"], panel["script_name"])
        except deploy.DeployError as error:
            log.warning("worker delete failed: %s", error.reason)

    await db.delete_panel(call.from_user.id)
    await db.log_event("panel_deleted", call.from_user.id, panel["host"])
    await edit(call, t(lang, "deleted"), keyboards.simple_back(lang))
