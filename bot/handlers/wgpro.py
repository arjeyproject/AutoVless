"""WARP pro screens: tuning, identity backup/restore, the live benchmark.

These callbacks live apart from ``handlers.warp`` on purpose. That module owns
the build-and-deliver flow and every legacy callback that keyboards already in
chat history can still press; this one owns the 3.0 layer. Both answer ``wg:``
prefixes, but every callback here is a distinct key that older keyboards never
sent, so the two routers never fight for the same tap.

The benchmark answers immediately and reports into the chat when the probes
finish, exactly like the rescan flow: nobody waits on a message that cannot
tell the difference between "working" and "dead".
"""

from __future__ import annotations

import asyncio
import logging
import time

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, Message

from .. import db, keyboards, warpconf, wgpro, warpops
from ..i18n import num, t
from ..utils import edit, esc, ping_label
from ..warpstore import best as best_endpoints

log = logging.getLogger("autovless.handlers.wgpro")
router = Router(name="wgpro")

# Live benchmark jobs, held so the loop cannot collect them mid-sweep.
_jobs: set[asyncio.Task] = set()


class RestoreFlow(StatesGroup):
    waiting = State()


class ProDmFlow(StatesGroup):
    waiting = State()


def _b(label: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=label, callback_data=data)


def _mark(value: str, current: str) -> str:
    return f"{value} ✓" if value.split(" ", 1)[-1] == current or value == current else value


def settings_keyboard(lang: str, prefs: dict) -> "keyboards.InlineKeyboardMarkup":
    intensity = prefs.get("intensity", "normal")
    mtu = prefs.get("mtu", "auto")
    dns = prefs.get("dns", "cf")

    def on(name: str, current: str) -> str:
        return f"✓ {t(lang, name)}" if name.split("_", 2)[-1] == current else t(lang, name)

    rows: list[list[InlineKeyboardButton]] = [
        [
            _b(on("pro.intensity_normal", intensity), "wg:set:int:normal"),
            _b(on("pro.intensity_strong", intensity), "wg:set:int:strong"),
            _b(on("pro.intensity_ultra", intensity), "wg:set:int:ultra"),
        ],
        [
            _b(on("pro.mtu_auto", mtu), "wg:set:mtu:auto"),
            _b(on("pro.mtu_safe", mtu), "wg:set:mtu:safe"),
        ],
        [
            _b(on("pro.mtu_balanced", mtu), "wg:set:mtu:balanced"),
            _b(on("pro.mtu_max", mtu), "wg:set:mtu:max"),
        ],
    ]
    dns_rows: list[InlineKeyboardButton] = [
        _b(on(f"pro.dns_{code}", dns), f"wg:set:dns:{code}")
        for code, _ in wgpro.DNS_CHOICES
    ]
    for index in range(0, len(dns_rows), 2):
        rows.append(dns_rows[index : index + 2])
    rows.append([_b("⚡ " + t(lang, "btn.wg_bench"), "wg:bench")])
    rows.append(keyboards.back_row(lang, "nav:warp"))
    return keyboards.InlineKeyboardMarkup(inline_keyboard=rows)


async def show_settings(event: "CallbackQuery | Message", lang: str) -> None:
    prefs = await wgpro.prefs_of(event.from_user.id)
    intensity = t(lang, f"pro.intensity_{prefs.get('intensity', 'normal')}")
    body = t(
        lang,
        "pro.settings",
        intensity=intensity,
        intensity_desc=t(lang, f"pro.intensity_desc_{prefs.get('intensity', 'normal')}"),
        mtu=t(lang, f"pro.mtu_{prefs.get('mtu', 'auto')}"),
        dns=t(lang, f"pro.dns_{prefs.get('dns', 'cf')}"),
    )
    await edit(event, body, settings_keyboard(lang, prefs))


@router.callback_query(F.data == "wg:set")
async def on_settings(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return
    await show_settings(call, lang)
    await call.answer()


@router.callback_query(F.data.startswith("wg:set:"))
async def on_setting_change(call: CallbackQuery, lang: str) -> None:
    parts = (call.data or "").split(":")
    kind = parts[2] if len(parts) > 2 else ""
    value = parts[3] if len(parts) > 3 else ""
    if kind == "int" and value in wgpro.INTENSITIES:
        await wgpro.save_prefs(call.from_user.id, intensity=value)
    elif kind == "mtu" and value in wgpro.MTU_MODES:
        await wgpro.save_prefs(call.from_user.id, mtu=value)
    elif kind == "dns" and value in {code for code, _ in wgpro.DNS_CHOICES}:
        await wgpro.save_prefs(call.from_user.id, dns=value)
    else:
        await call.answer()
        return
    await show_settings(call, lang)
    await call.answer(t(lang, "admin.saved"))


# ------------------------------------------------------------------ backup


@router.callback_query(F.data == "wg:backup")
async def on_backup(call: CallbackQuery, lang: str) -> None:
    record = await db.get_warp_user(call.from_user.id)
    if record is None:
        await call.answer(t(lang, "pro.backup_none"), show_alert=True)
        return

    await call.answer()
    prefs = await wgpro.prefs_of(call.from_user.id)
    body = wgpro.backup_document(record["identity"], record.get("endpoints") or [], prefs)
    stamp = time.strftime("%Y-%m-%d")
    await call.message.answer_document(
        BufferedInputFile(body.encode("utf-8"), filename=f"{settings_brand()}-warp-backup-{stamp}.json"),
        caption=t(lang, "pro.backup_caption"),
        reply_markup=keyboards.simple_back(lang, "nav:warp"),
    )


def settings_brand() -> str:
    from ..config import settings

    return (settings.brand or "autovless").strip().lower().replace(" ", "-") or "autovless"


@router.callback_query(F.data == "wg:restore")
async def on_restore(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return
    await state.set_state(RestoreFlow.waiting)
    await edit(call, t(lang, "pro.restore_prompt"), keyboards.simple_back(lang, "nav:warp"))
    await call.answer()


async def _apply_backup(message: Message, lang: str, raw: str) -> None:
    try:
        identity, endpoints, prefs = wgpro.parse_backup(raw)
    except ValueError as error:
        await message.answer(t(lang, "pro.restore_bad", reason=esc(str(error))))
        return

    # The backup may carry stale endpoints; the failover engine keeps a live one
    # if it still answers and fills the rest from the current pool.
    fresh = await _refresh_endpoints(endpoints)
    await db.save_warp_user(message.from_user.id, identity, fresh)
    await wgpro.save_prefs(message.from_user.id, **prefs)
    await db.log_event("warp_restore", message.from_user.id, identity.get("account_type", ""))
    await message.answer(
        t(lang, "pro.restore_ok"),
        reply_markup=keyboards.warp_menu(lang, True),
    )


async def _refresh_endpoints(saved: list[dict]) -> list[dict]:
    """Pool-backed endpoint list that prefers the backup's own head."""
    from ..warpscan import warp_scanner

    try:
        return await warp_scanner.failover(saved or [])
    except Exception:  # noqa: BLE001
        return list(saved or [])


@router.message(RestoreFlow.waiting, F.document)
async def on_restore_file(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    document = message.document
    if document is None or (document.file_size or 0) > 256_000:
        await message.answer(t(lang, "pro.restore_bad", reason="file"))
        return
    try:
        downloaded = await message.bot.download(document)
        raw = downloaded.read().decode("utf-8")
    except Exception as error:  # noqa: BLE001
        await message.answer(t(lang, "pro.restore_bad", reason=esc(str(error)[:120])))
        return
    await _apply_backup(message, lang, raw)


@router.message(RestoreFlow.waiting, F.text, ~F.text.startswith("/"))
async def on_restore_text(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    await _apply_backup(message, lang, message.text or "")


# ----------------------------------------------------------------- benchmark


@router.callback_query(F.data == "wg:bench")
async def on_bench(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return
    record = await db.get_warp_user(call.from_user.id)
    if record is None:
        await call.answer(t(lang, "pro.backup_none"), show_alert=True)
        return

    candidates = await best_endpoints(10, stable_only=True)
    if not candidates:
        await call.answer(t(lang, "pro.bench_no_pool"), show_alert=True)
        return

    await call.answer()
    notice = await call.message.answer(
        t(
            lang,
            "pro.bench_started",
            count=num(len(candidates), lang),
            secs=num(max(4, len(candidates)), lang),
        )
    )

    task = asyncio.create_task(
        _run_benchmark(notice, lang, record["identity"], candidates),
        name=f"wg-bench-{call.from_user.id}",
    )
    _jobs.add(task)
    task.add_done_callback(_jobs.discard)


def _bench_table(lang: str, measured: list[dict]) -> str:
    lines = []
    for index, row in enumerate(measured, start=1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(index, "▫️")
        address = warpconf.host_port(row["ip"], row["port"])
        lines.append(
            f"{medal} <code>{esc(address)}</code> · <b>{ping_label(row['latency'], lang)}</b>"
        )
    return "\n".join(lines)


async def _run_benchmark(
    notice: Message,
    lang: str,
    identity: dict,
    candidates: list[dict],
) -> None:
    started = time.monotonic()
    measured, _ = await wgpro.benchmark(identity, count=len(candidates))
    elapsed = time.monotonic() - started
    log.info("warp benchmark: %s answered of %s in %.1fs", len(measured), len(candidates), elapsed)

    if not measured:
        try:
            await notice.edit_text(t(lang, "pro.bench_empty"), reply_markup=keyboards.warp_endpoints(lang))
        except Exception:  # noqa: BLE001
            pass
        return

    # Reorder the user's saved endpoints by what actually answered here, and
    # keep any stored endpoint the benchmark could not reach behind them.
    record = await db.get_warp_user(notice.chat.id) or {}
    saved = record.get("endpoints") or []
    measured_pairs = {(row["ip"], int(row["port"])) for row in measured}
    untouched = [
        row for row in saved if (str(row.get("ip")), int(row.get("port") or 0)) not in measured_pairs
    ]
    merged = measured + untouched
    await db.update_warp_endpoints(notice.chat.id, merged[: max(len(saved), len(measured))])
    await db.log_event("warp_bench", notice.chat.id, f"best={measured[0]['ip']}:{measured[0]['port']}")

    # Feed the operator leaderboard. The user's own network is the tag, so the
    # wins land on the operator that can actually use them - and the next person
    # on the same carrier gets endpoints this network has already proven.
    try:
        user = await db.get_user(notice.chat.id)
        operator = (user or {}).get("operator") if user else None
        await warpops.record(str(operator or "other"), measured)
    except Exception:  # noqa: BLE001
        log.debug("could not record benchmark into warp_ops", exc_info=True)

    body = t(lang, "pro.bench_done", table=_bench_table(lang, measured))
    try:
        await notice.edit_text(body, reply_markup=keyboards.warp_menu(lang, True))
    except Exception:  # noqa: BLE001
        await notice.answer(body, reply_markup=keyboards.warp_menu(lang, True))
