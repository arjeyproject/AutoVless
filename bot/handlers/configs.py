"""The Configurations screen: real ping tests, real exit IPs, and the Proxy Chain.

This screen is the answer to two long-standing complaints:

* "none of the configs ping" - because the old ping was a TCP handshake to the
  entry address, which proved nothing about the tunnel. Here every test opens
  the actual client path (TLS with the panel's SNI, the upgrade, the VLESS or
  Trojan request) and reads the exit address from inside the tunnel. A green
  mark means a destination outside Cloudflare answered through the config.
* "the configs all look the same" - each config now has a card with its own
  status, its own exit country, its own server vs exit IP, and actions that
  actually act: test, details, enable/disable, remove, chain.

The Proxy Chain is real chaining: hops wired with Xray's ``proxySettings`` in
the exported config, validated for loops, tested end-to-end through the core
when one is installed.
"""

from __future__ import annotations

import asyncio
import logging
import time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message

from .. import chain as chainmod
from .. import db, deploy, keyboards, pages, pingtest, vless, xraycore
from ..i18n import num, t
from ..utils import ago, edit, esc, ping_label

log = logging.getLogger("autovless.configs")
router = Router(name="configs")

# One background test batch at a time per user, and one panel push at a time.
_test_jobs: dict[int, asyncio.Task] = {}
_pushing: set[int] = set()

FRESH_WINDOW = 600  # a test result younger than this is "current"


class ChainFlow(StatesGroup):
    hop = State()
    name = State()


def _status_mark(record: dict | None, disabled: bool, lang: str) -> str:
    if disabled:
        return "\u26d4"
    if record is None:
        return "\u26aa"
    fresh = int(record.get("tested_at") or 0) > time.time() - 3600
    if not fresh:
        return "\u26aa"
    return "\U0001f7e2" if record.get("ok") else "\U0001f534"


def _flag(cc: str) -> str:
    return pingtest.flag_emoji(cc) or "\U0001f3f3"


def _endpoint_links(panel: dict) -> list[dict]:
    """One card per panel endpoint, with its canonical (ws) link."""
    uuid, host = str(panel["uuid"]), str(panel["host"])
    cards: list[dict] = []
    for index, ep in enumerate(panel.get("endpoints") or []):
        link = vless.build_link(uuid, host, ep, index + 1, settings_brand(), "ws")
        cards.append({
            "index": index,
            "endpoint": ep,
            "link": link,
            "addr": f"{ep['ip']}:{ep['port']}",
            "tls": vless.is_tls(int(ep["port"])),
            "disabled": bool(ep.get("disabled")),
        })
    return cards


def settings_brand() -> str:
    from ..config import settings

    return settings.brand
    def ping_of(card: dict) -> float:
        record = results.get(db.test_key(card["link"])) or {}
        value = record.get("latency_ms")
        return float(value) if record.get("ok") and value else 999_999.0

    def status_of(card: dict) -> int:
        record = results.get(db.test_key(card["link"])) or {}
        if card["disabled"]:
            return 3
        if not record:
            return 2
        return 0 if record.get("ok") else 1

    if mode == "ping":
        return sorted(cards, key=ping_of)
    if mode == "status":
        return sorted(cards, key=status_of)
    if mode == "proto":
        return sorted(cards, key=lambda c: (0 if c["tls"] else 1, ping_of(c)))
    return cards


def _filter_cards(cards: list[dict], results: dict[str, dict], flt: str) -> list[dict]:
    if flt == "all":
        return cards
    out = []
    for card in cards:
        record = results.get(db.test_key(card["link"])) or {}
        if flt == "online" and record.get("ok"):
            out.append(card)
        elif flt == "offline" and record and not record.get("ok"):
            out.append(card)
        elif flt == "tls" and card["tls"]:
            out.append(card)
        elif flt == "http" and not card["tls"]:
            out.append(card)
    return out


# --------------------------------------------------------------------- #
# the screen
# --------------------------------------------------------------------- #


def _chain_status_line(row: dict, lang: str) -> str:
    result = row.get("last_result") or {}
    if result.get("ok"):
        return t(
            lang,
            "chain_status_ok",
            ping=ping_label(result.get("latency_ms"), lang),
            flag=_flag(str(result.get("exit_country") or "")),
            exit=esc(str(result.get("exit_ip") or "-")),
        )
    if result.get("error_kind"):
        return t(
            lang,
            "chain_status_bad",
            error=esc(pingtest.describe_error(str(result.get("error_kind")), lang)),
        )
    return t(lang, "chain_status_untested")


async def chain_screen(tg_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    rows = await db.list_chains(tg_id)
    if not rows:
        return t(lang, "chain_none"), _chain_home_markup(lang, None)

    blocks = []
    for row in rows:
        hops = chainmod.normalise_hops(row.get("hops"))
        visual = chainmod.describe(hops, lang)
        blocks.append(
            t(
                lang,
                "chain_row",
                state_mark=t(lang, "chain_enabled_mark" if row.get("enabled") else "chain_disabled_mark"),
                name=esc(str(row.get("name") or "chain")),
                visual=esc(visual),
                status_line=_chain_status_line(row, lang),
            )
        )
    text = t(lang, "chain_screen", chains="\n\n".join(blocks))

    from aiogram.types import InlineKeyboardButton

    tail: list[list] = []
    for row in rows:
        tail.append([
            InlineKeyboardButton(text=f"\u2699 {str(row.get('name'))[:18]}", callback_data=f"cfg:chain:one:{row['id']}"),
        ])
    return text, _chain_home_markup(lang, tail)


def _chain_home_markup(lang: str, chain_rows: list[list] | None) -> InlineKeyboardMarkup:
    from aiogram.types import InlineKeyboardButton

    rows: list[list] = list(chain_rows or [])
    rows.append([keyboards._c(t(lang, "btn.chain_add"), "cfg:chain:add", keyboards.GO)])
    rows.append(keyboards.back_row(lang, "cfg:home"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def configs_screen(tg_id: int, lang: str, sort: str = "ping", flt: str = "all") -> tuple[str, InlineKeyboardMarkup]:
    panel = await db.get_panel(tg_id)
    if panel is None:
        return t(lang, "panel_none"), keyboards.simple_back(lang, "nav:panel")

    cards = _endpoint_links(panel)
    if not cards:
        return t(lang, "configs_empty"), keyboards.panel_menu(lang)

    results = await db.get_test_results([card["link"] for card in cards if card["link"]])
    visible = _filter_cards(_sort_cards(cards, results, sort), results, flt)
    if not visible:
        return t(lang, "no_match"), _configs_markup(lang, sort, flt, [])

    rows = []
    for card in visible:
        record = results.get(db.test_key(card["link"])) or {}
        i = card["index"] + 1
        if card["disabled"]:
            rows.append(t(lang, "config_row_disabled", i=num(i, lang), addr=esc(card["addr"])))
        elif record:
            if record.get("ok"):
                flag = _flag(str(record.get("exit_country") or ""))
                rows.append(
                    t(
                        lang,
                        "config_row_online",
                        i=num(i, lang),
                        addr=esc(card["addr"]),
                        flag=flag,
                        ping=ping_label(record.get("latency_ms"), lang),
                        exit=esc(str(record.get("exit_ip") or "-")),
                    )
                )
            else:
                rows.append(
                    t(
                        lang,
                        "config_row_offline",
                        i=num(i, lang),
                        addr=esc(card["addr"]),
                        error=esc(pingtest.describe_error(str(record.get("error_kind") or "internal"), lang)),
                    )
                )
        else:
            rows.append(t(lang, "config_row_unknown", i=num(i, lang), addr=esc(card["addr"])))

    text = t(lang, "configs_screen", count=num(len(visible), lang), cards="\n".join(rows))
    text += "\n\n" + t(
        lang,
        "configs_filter_note",
        filter=esc(t(lang, f"flt_{flt}")),
        sort=esc(t(lang, f"sort_{sort}")),
    )
    return text, _configs_markup(lang, sort, flt, visible)


def _configs_markup(lang: str, sort: str, flt: str, visible: list[dict]) -> InlineKeyboardMarkup:
    from aiogram.types import InlineKeyboardButton

    rows: list[list] = [
        [
            keyboards._c(t(lang, "btn.test_all"), "cfg:testall", keyboards.OK),
            keyboards._c(t(lang, "btn.refresh_list"), f"cfg:home:{sort}:{flt}", keyboards.GO),
        ],
        [
            InlineKeyboardButton(text=f"\u21c5 {t(lang, 'sort_ping')}", callback_data="cfg:sort:ping"),
            InlineKeyboardButton(text=f"\u21c5 {t(lang, 'sort_status')}", callback_data="cfg:sort:status"),
            InlineKeyboardButton(text=f"\u21c5 {t(lang, 'sort_proto')}", callback_data="cfg:sort:proto"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "flt_all"), callback_data="cfg:flt:all"),
            InlineKeyboardButton(text=t(lang, "flt_online"), callback_data="cfg:flt:online"),
            InlineKeyboardButton(text=t(lang, "flt_offline"), callback_data="cfg:flt:offline"),
            InlineKeyboardButton(text=t(lang, "flt_tls"), callback_data="cfg:flt:tls"),
        ],
    ]
    for card in visible:
        i = card["index"]
        state = "\u23f8" if card["disabled"] else "\u25b6"
        rows.append([
            InlineKeyboardButton(text=f"#{num(i + 1, lang)} \U0001f484", callback_data=f"cfg:det:{i}:{sort}:{flt}"),
            InlineKeyboardButton(text=f"#{num(i + 1, lang)} \U0001f52c", callback_data=f"cfg:test:{i}:{sort}:{flt}"),
            InlineKeyboardButton(text=f"#{num(i + 1, lang)} {state}", callback_data=f"cfg:tog:{i}:{sort}:{flt}"),
            InlineKeyboardButton(text=f"#{num(i + 1, lang)} \U0001f5d1", callback_data=f"cfg:del:{i}:{sort}:{flt}"),
        ])
    rows.append([keyboards._c(t(lang, "btn.chain"), "cfg:chain", keyboards.GO)])
    rows.append(keyboards.back_row(lang, "nav:panel"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --------------------------------------------------------------------- #
# handlers - the configs list
# --------------------------------------------------------------------- #


@router.callback_query(F.data == "panel:configs")
async def on_configs(call: CallbackQuery, lang: str) -> None:
    text, markup = await configs_screen(call.from_user.id, lang)
    await edit(call, text, markup)
    await call.answer()


@router.callback_query(F.data.regexp(r"^cfg:home:(\w+):(\w+)$"))
async def on_home(call: CallbackQuery, lang: str) -> None:
    _, _, sort, flt = call.data.split(":")
    text, markup = await configs_screen(call.from_user.id, sort, flt)
    await edit(call, text, markup)
    await call.answer()


@router.callback_query(F.data.regexp(r"^cfg:sort:(\w+)$"))
async def on_sort(call: CallbackQuery, lang: str) -> None:
    sort = call.data.split(":")[2]
    text, markup = await configs_screen(call.from_user.id, sort, "all")
    await edit(call, text, markup)
    await call.answer()


@router.callback_query(F.data.regexp(r"^cfg:flt:(\w+)$"))
async def on_filter(call: CallbackQuery, lang: str) -> None:
    flt = call.data.split(":")[2]
    text, markup = await configs_screen(call.from_user.id, "ping", flt)
    await edit(call, text, markup)
    await call.answer()


# --------------------------------------------------------------------- #
# details
# --------------------------------------------------------------------- #


async def _detail_text(tg_id: int, index: int, lang: str) -> tuple[str | None, dict | None, list[str]]:
    panel = await db.get_panel(tg_id)
    if panel is None:
        return None, None, []
    cards = _endpoint_links(panel)
    card = next((c for c in cards if c["index"] == index), None)
    if card is None:
        return None, None, []
    endpoint = card["endpoint"]
    record = (await db.get_test_results([card["link"]])).get(db.test_key(card["link"])) or {}
    server_ip = str(record.get("server_ip") or "") or str(endpoint.get("ip") or "-")
    exit_ip = str(record.get("exit_ip") or "")
    if record.get("ok") and exit_ip:
        exit_line = f"{_flag(str(record.get('exit_country') or ''))} <code>{esc(exit_ip)}</code>"
    else:
        exit_line = t(lang, "exit_unknown")
    ping_line = ping_label(record.get("latency_ms"), lang) if record.get("ok") else "-"
    tested_line = ago(record.get("tested_at"), lang) if record else t(lang, "never")
    error_line = (
        esc(pingtest.describe_error(str(record.get("error_kind")), lang))
        if record and not record.get("ok")
        else esc(t(lang, "no_error"))
    )
    secure = card["tls"]
    text = t(
        lang,
        "config_detail",
        i=num(index + 1, lang),
        host=esc(str(panel["host"])),
        addr=esc(card["addr"]),
        security="TLS" if secure else "none",
        transport=esc(str(endpoint.get("transport") or "ws")),
        colo=esc(str(endpoint.get("colo") or "CF")),
        server_ip=esc(server_ip),
        exit_line=exit_line,
        ping_line=ping_line,
        tested_line=tested_line,
        error_line=error_line,
    )
    return text, card, [card["link"]]


@router.callback_query(F.data.regexp(r"^cfg:det:(\d+):(\w+):(\w+)$"))
async def on_detail(call: CallbackQuery, lang: str) -> None:
    _, _, index_s, sort, flt = call.data.split(":")
    index = int(index_s)
    text, card, links = await _detail_text(call.from_user.id, index, lang)
    if text is None or card is None:
        await call.answer(t(lang, "configs_empty"), show_alert=True)
        return

    from aiogram.types import InlineKeyboardButton

    rows: list[list] = [
        [keyboards._c(t(lang, "btn.test_one"), f"cfg:test:{index}:{sort}:{flt}", keyboards.OK)],
        [
            InlineKeyboardButton(
                text=t(lang, "btn.enable" if card["disabled"] else "btn.toggle"),
                callback_data=f"cfg:tog:{index}:{sort}:{flt}",
            ),
            InlineKeyboardButton(text=t(lang, "btn.remove"), callback_data=f"cfg:del:{index}:{sort}:{flt}"),
        ],
        keyboards.back_row(lang, f"cfg:home:{sort}:{flt}"),
    ]
    await edit(
        call,
        text + f"\n\n<pre>{esc(card['link'])}</pre>",
        InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await call.answer()


# --------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------- #


async def _run_one_test(tg_id: int, index: int, lang: str, sort: str, flt: str) -> None:
    """Test one endpoint now, redraw the screen with the result."""
    panel = await db.get_panel(tg_id)
    if panel is None:
        return
    cards = _endpoint_links(panel)
    card = next((c for c in cards if c["index"] == index), None)
    if card is None or not card["link"]:
        return
    result = await pingtest.test_link(card["link"])
    await db.save_test_result(tg_id, card["link"], card["addr"], result.as_dict())


@router.callback_query(F.data.regexp(r"^cfg:test:(\d+):(\w+):(\w+)$"))
async def on_test_one(call: CallbackQuery, lang: str) -> None:
    _, _, index_s, sort, flt = call.data.split(":")
    index = int(index_s)
    await call.answer(t(lang, "testing_one", i=num(index + 1, lang)))
    await _run_one_test(call.from_user.id, index, lang, sort, flt)
    text, markup = await configs_screen(call.from_user.id, sort, flt)
    await edit(call, text, markup)


@router.callback_query(F.data == "cfg:testall")
async def on_test_all(call: CallbackQuery, lang: str) -> None:
    tg_id = call.from_user.id
    if tg_id in _test_jobs and not _test_jobs[tg_id].done():
        await call.answer(t(lang, "test_still_running"), show_alert=True)
        return

    panel = await db.get_panel(tg_id)
    if panel is None:
        await call.answer(t(lang, "panel_none"), show_alert=True)
        return
    cards = _endpoint_links(panel)
    if not cards:
        await call.answer(t(lang, "configs_empty"), show_alert=True)
        return

    await call.answer()
    notice = await call.message.answer(t(lang, "testing_all", done=num(0, lang), total=num(len(cards), lang)))

    async def job() -> None:
        jobs = [(str(card["index"]), card["link"]) for card in cards if card["link"]]
        done = 0
        ok_count = bad_count = 0
        try:
            async for key, result in pingtest.test_many(jobs, concurrency=4):
                done += 1
                ok_count += 1 if result.ok else 0
                bad_count += 0 if result.ok else 1
                card = next((c for c in cards if str(c["index"]) == key), None)
                if card is not None:
                    await db.save_test_result(tg_id, card["link"], card["addr"], result.as_dict())
                if done % 2 == 0 or done == len(jobs):
                    try:
                        await notice.edit_text(
                            t(lang, "testing_all", done=num(done, lang), total=num(len(jobs), lang))
                        )
                    except Exception:  # noqa: BLE001
                        pass
            await notice.edit_text(
                t(lang, "test_all_done", ok_count=num(ok_count, lang), bad_count=num(bad_count, lang))
            )
            text, markup = await configs_screen(tg_id, "ping", "all")
            await call.message.answer(text, reply_markup=markup, disable_web_page_preview=True)
        except Exception:  # noqa: BLE001
            log.exception("test-all batch failed")
            try:
                await notice.edit_text(t(lang, "error_generic", reason="test batch"))
            except Exception:  # noqa: BLE001
                pass

    _test_jobs[tg_id] = asyncio.create_task(job(), name=f"cfg-testall-{tg_id}")


# --------------------------------------------------------------------- #
# enable / disable / remove + panel re-push
# --------------------------------------------------------------------- #


async def _push_panel_bindings(tg_id: int, lang: str) -> None:
    """Re-upload the worker with the current endpoint list.

    Runs in the background: a Pages deployment takes up to a minute and a
    button press must answer instantly. One push at a time per user.
    """
    if tg_id in _pushing:
        return
    _pushing.add(tg_id)
    try:
        panel = await db.get_panel(tg_id)
        if panel is None or not panel.get("token"):
            return
        endpoints = [ep for ep in (panel.get("endpoints") or []) if not ep.get("disabled")]
        relays = panel.get("relays") or []
        variables = pages.bindings(
            str(panel["uuid"]),
            str(panel["host"]),
            endpoints,
            relays,
            [str(panel.get("ai_relay") or "")] if panel.get("ai_relay") else [],
            [str(panel.get("chain_relay") or "")] if panel.get("chain_relay") else [],
        )
        code = deploy._read_worker()
        if str(panel.get("deploy_target") or "workers") == "pages":
            await pages.push(
                str(panel["token"]),
                str(panel["account_id"]),
                pages.project_name(str(panel["script_name"])),
                code,
                variables,
            )
        else:
            from ..cloudflare import CloudflareClient

            async with CloudflareClient(str(panel["token"])) as cf:
                await cf.upload_script(
                    str(panel["account_id"]),
                    str(panel["script_name"]),
                    code,
                    deploy._bindings(
                        str(panel["uuid"]),
                        str(panel["host"]),
                        endpoints,
                        relays,
                        [str(panel.get("ai_relay") or "")] if panel.get("ai_relay") else [],
                        [str(panel.get("chain_relay") or "")] if panel.get("chain_relay") else [],
                    ),
                )
    except Exception as error:  # noqa: BLE001
        log.warning("config push failed for %s: %s", tg_id, error)
    finally:
        _pushing.discard(tg_id)


def _spawn_push(tg_id: int) -> None:
    asyncio.create_task(_push_panel_bindings(tg_id, "fa"), name=f"cfg-push-{tg_id}")


@router.callback_query(F.data.regexp(r"^cfg:tog:(\d+):(\w+):(\w+)$"))
async def on_toggle(call: CallbackQuery, lang: str) -> None:
    _, _, index_s, sort, flt = call.data.split(":")
    index = int(index_s)
    tg_id = call.from_user.id
    panel = await db.get_panel(tg_id)
    if panel is None or index >= len(panel.get("endpoints") or []):
        await call.answer(t(lang, "configs_empty"), show_alert=True)
        return
    endpoint = panel["endpoints"][index]
    endpoint["disabled"] = not endpoint.get("disabled")
    await db.update_panel_endpoints(tg_id, panel["endpoints"], int(panel.get("build_ms") or 0))
    _spawn_push(tg_id)
    await call.answer()
    text, markup = await configs_screen(tg_id, sort, flt)
    await edit(call, text, markup)


@router.callback_query(F.data.regexp(r"^cfg:del:(\d+):(\w+):(\w+)$"))
async def on_delete_ask(call: CallbackQuery, lang: str) -> None:
    _, _, index_s, sort, flt = call.data.split(":")
    index = int(index_s)
    panel = await db.get_panel(call.from_user.id)
    if panel is None or index >= len(panel.get("endpoints") or []):
        await call.answer(t(lang, "configs_empty"), show_alert=True)
        return
    if len(panel.get("endpoints") or []) <= 1:
        await call.answer("\u26a0\ufe0f \u0622\u062e\u0631\u06cc\u0646 \u06a9\u0627\u0646\u0641\u06cc\u06af \u0642\u0627\u0628\u0644 \u062d\u0630\u0641 \u0646\u06cc\u0633\u062a.", show_alert=True)
        return
    addr = f"{panel['endpoints'][index]['ip']}:{panel['endpoints'][index]['port']}"
    await edit(
        call,
        t(lang, "delete_confirm_cfg", i=num(index + 1, lang), addr=esc(addr)),
        keyboards.confirm_menu(lang, f"cfg:delok:{index}:{sort}:{flt}", f"cfg:home:{sort}:{flt}"),
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^cfg:delok:(\d+):(\w+):(\w+)$"))
async def on_delete_yes(call: CallbackQuery, lang: str) -> None:
    _, _, index_s, sort, flt = call.data.split(":")
    index = int(index_s)
    tg_id = call.from_user.id
    panel = await db.get_panel(tg_id)
    if panel is None or index >= len(panel.get("endpoints") or []):
        await call.answer(t(lang, "configs_empty"), show_alert=True)
        return
    endpoints = panel.get("endpoints") or []
    if len(endpoints) <= 1:
        await call.answer("\u26a0\ufe0f \u0622\u062e\u0631\u06cc\u0646 \u06a9\u0627\u0646\u0641\u06cc\u06af \u0642\u0627\u0628\u0644 \u062d\u0630\u0641 \u0646\u06cc\u0633\u062a.", show_alert=True)
        return
    removed = endpoints.pop(index)
    await db.update_panel_endpoints(tg_id, endpoints, int(panel.get("build_ms") or 0))
    _spawn_push(tg_id)
    await db.log_event("config_removed", tg_id, f"{removed.get('ip')}:{removed.get('port')}")
    await call.answer()
    text, markup = await configs_screen(tg_id, sort, flt)
    await edit(call, text, markup)


# --------------------------------------------------------------------- #
# proxy chain
# --------------------------------------------------------------------- #


@router.callback_query(F.data == "cfg:chain")
async def on_chain_home(call: CallbackQuery, lang: str) -> None:
    text, markup = await chain_screen(call.from_user.id, lang)
    await edit(call, text, markup)
    await call.answer()


@router.callback_query(F.data == "cfg:chain:add")
async def on_chain_add(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.set_state(ChainFlow.hop)
    await state.update_data(hops=[])
    if call.message is not None:
        await _hop_screen(call.message, call.from_user.id, state, lang)
    await call.answer()


async def _hop_screen(target: Message, tg_id: int, state: FSMContext, lang: str, *, fresh: bool = False) -> None:
    data = await state.get_data()
    hops = list(data.get("hops") or [])
    panel = await db.get_panel(tg_id)

    from aiogram.types import InlineKeyboardButton

    rows: list[list] = []
    if panel is not None:
        picked = []
        for hop in hops:
            try:
                picked.append(pingtest.parse_link(hop))
            except pingtest.LinkError:
                pass
        used = {(str(p["host"]), int(p["port"])) for p in picked}
        buttons = []
        for card in _endpoint_links(panel):
            if (str(card["endpoint"]["ip"]), int(card["endpoint"]["port"])) in used:
                continue
            buttons.append(
                InlineKeyboardButton(
                    text=t(lang, "chain_pick", i=num(card["index"] + 1, lang), addr=esc(card["addr"])),
                    callback_data=f"cfg:chain:pick:{card['index']}",
                )
            )
        rows += [pair for pair in [buttons[i : i + 2] for i in range(0, len(buttons), 2)] if pair]
    rows.append([
        InlineKeyboardButton(text=t(lang, "chain_done"), callback_data="cfg:chain:finish"),
        InlineKeyboardButton(text=t(lang, "btn.back"), callback_data="cfg:chain"),
    ])
    text = t(lang, "chain_add_prompt", i=num(len(hops) + 1, lang), max=num(chainmod.MAX_HOPS, lang))
    if hops:
        text += "\n\n" + t(lang, "chain_current", visual=esc(chainmod.describe(hops, lang)))
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    if fresh:
        await target.answer(text, reply_markup=markup, disable_web_page_preview=True)
    else:
        try:
            await target.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
        except Exception:  # noqa: BLE001
            await target.answer(text, reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(ChainFlow.hop, F.data.regexp(r"^cfg:chain:pick:(\d+)$"))
async def on_chain_pick(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    tg_id = call.from_user.id
    index = int(call.data.split(":")[3])
    panel = await db.get_panel(tg_id)
    if panel is None:
        await call.answer(t(lang, "panel_none"), show_alert=True)
        return
    cards = _endpoint_links(panel)
    card = next((c for c in cards if c["index"] == index), None)
    if card is None or not card["link"]:
        await call.answer(t(lang, "configs_empty"), show_alert=True)
        return
    data = await state.get_data()
    hops = list(data.get("hops") or [])
    error = await _append_hop(state, hops, card["link"], lang)
    if error:
        await call.answer(error, show_alert=True)
        return
    await call.answer()
    if call.message is not None:
        await _hop_screen(call.message, tg_id, state, lang)


async def _append_hop(state: FSMContext, hops: list[str], link: str, lang: str) -> str:
    """Validate and append. Returns a user-facing reason on refusal."""
    if len(hops) >= chainmod.MAX_HOPS:
        return t(lang, "chain_too_long", max=num(chainmod.MAX_HOPS, lang))
    try:
        parsed = pingtest.parse_link(link)
    except pingtest.LinkError as error:
        return t(lang, "chain_bad_hop", reason=esc(str(error)))
    server = (str(parsed["host"]).lower(), int(parsed["port"]))
    for hop in hops:
        try:
            other = pingtest.parse_link(hop)
        except pingtest.LinkError:
            continue
        if (str(other["host"]).lower(), int(other["port"])) == server:
            return t(lang, "chain_loop")
    hops.append(link.strip())
    await state.update_data(hops=hops)
    return ""


@router.message(ChainFlow.hop, F.text)
async def on_chain_hop_link(message: Message, state: FSMContext, lang: str) -> None:
    text = (message.text or "").strip()
    if text.startswith("/done"):
        await _finish_chain(message, state, lang)
        return
    if text.startswith("/cancel"):
        await state.clear()
        await message.answer(t(lang, "cancelled"))
        return
    data = await state.get_data()
    hops = list(data.get("hops") or [])
    error = await _append_hop(state, hops, text, lang)
    if error:
        await message.answer(error)
        return
    if len(hops) >= chainmod.MAX_HOPS:
        await _finish_chain(message, state, lang)
        return
    await _hop_screen(message, message.from_user.id, state, lang)


async def _finish_chain(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    hops = list(data.get("hops") or [])
    await state.clear()
    if not hops:
        await message.answer(t(lang, "chain_empty"))
        return
    ok, reason, parsed = chainmod.validate(hops)
    if not ok:
        await message.answer(t(lang, reason, max=num(chainmod.MAX_HOPS, lang)))
        return
    tg_id = message.from_user.id
    name = f"chain-{len(hops)}hop-{parsed[0]['host']}"[:40]
    chain_id = await db.create_chain(tg_id, name, hops)
    await db.log_event("chain_created", tg_id, f"hops={len(hops)}")
    await message.answer(t(lang, "chain_saved", name=esc(name)))
    text, markup = await chain_screen(tg_id, lang)
    await message.answer(text, reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(ChainFlow.hop, F.data == "cfg:chain:finish")
async def on_chain_finish_cb(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    if call.message is None:
        await call.answer()
        return
    await _finish_chain(call.message, state, lang)
    await call.answer()


@router.callback_query(F.data.regexp(r"^cfg:chain:one:(\d+)$"))
async def on_chain_one(call: CallbackQuery, lang: str) -> None:
    chain_id = int(call.data.split(":")[3])
    tg_id = call.from_user.id
    row = await db.get_chain(tg_id, chain_id)
    if row is None:
        await call.answer(t(lang, "chain_none"), show_alert=True)
        return
    hops = chainmod.normalise_hops(row.get("hops"))
    visual = chainmod.describe(hops, lang)
    text = t(
        lang,
        "chain_detail",
        name=esc(str(row.get("name") or "chain")),
        visual=esc(visual),
        status_line=_chain_status_line(row, lang),
    )
    from aiogram.types import InlineKeyboardButton

    mark = t(lang, "chain_disabled_mark") if not row.get("enabled") else t(lang, "chain_enabled_mark")
    rows: list[list] = [
        [keyboards._c(t(lang, "btn.chain_test"), f"cfg:chain:test:{chain_id}", keyboards.OK)],
        [
            InlineKeyboardButton(
                text=(t(lang, "btn.enable") if not row.get("enabled") else t(lang, "btn.toggle")),
                callback_data=f"cfg:chain:en:{chain_id}",
            ),
            InlineKeyboardButton(text=t(lang, "btn.chain_export"), callback_data=f"cfg:chain:export:{chain_id}"),
        ],
        [InlineKeyboardButton(text=t(lang, "btn.remove"), callback_data=f"cfg:chain:del:{chain_id}")],
        keyboards.back_row(lang, "cfg:chain"),
    ]
    await edit(call, text, InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()


@router.callback_query(F.data.regexp(r"^cfg:chain:test:(\d+)$"))
async def on_chain_test(call: CallbackQuery, lang: str) -> None:
    chain_id = int(call.data.split(":")[3])
    tg_id = call.from_user.id
    row = await db.get_chain(tg_id, chain_id)
    if row is None:
        await call.answer(t(lang, "chain_none"), show_alert=True)
        return
    if not xraycore.available():
        await call.answer(t(lang, "chain_core_missing"), show_alert=True)
        return
    await call.answer(t(lang, "chain_test_running"))
    hops = chainmod.normalise_hops(row.get("hops"))
    ok, reason, parsed = chainmod.validate(hops)
    if not ok:
        await call.message.answer(t(lang, reason, max=num(chainmod.MAX_HOPS, lang)))
        return
    result = await chainmod.test(parsed)
    await db.set_chain_result(tg_id, chain_id, result.as_dict())
    mark = "\u2705" if result.ok else "\u274c"
    if result.ok:
        status_line = t(
            lang,
            "chain_status_ok",
            ping=ping_label(result.latency_ms, lang),
            flag=_flag(result.exit_country),
            exit=esc(result.exit_ip or "-"),
        )
    else:
        status_line = t(lang, "chain_status_bad", error=esc(pingtest.describe_error(result.error_kind, lang)))
    await call.message.answer(t(lang, "chain_test_done", mark=mark, status_line=status_line))


@router.callback_query(F.data.regexp(r"^cfg:chain:en:(\d+)$"))
async def on_chain_enable(call: CallbackQuery, lang: str) -> None:
    chain_id = int(call.data.split(":")[3])
    tg_id = call.from_user.id
    row = await db.get_chain(tg_id, chain_id)
    if row is None:
        await call.answer(t(lang, "chain_none"), show_alert=True)
        return
    await db.set_chain_enabled(tg_id, chain_id, not row.get("enabled"))
    await db.log_event("chain_toggled", tg_id, f"id={chain_id} on={not row.get('enabled')}")
    await call.answer(t(lang, "chain_enabled_on" if not row.get("enabled") else "chain_enabled_off"))
    await on_chain_one(call, lang)


@router.callback_query(F.data.regexp(r"^cfg:chain:del:(\d+)$"))
async def on_chain_delete(call: CallbackQuery, lang: str) -> None:
    chain_id = int(call.data.split(":")[3])
    tg_id = call.from_user.id
    await db.delete_chain(tg_id, chain_id)
    await call.answer(t(lang, "chain_deleted"))
    text, markup = await chain_screen(tg_id, lang)
    await edit(call, text, markup)


@router.callback_query(F.data.regexp(r"^cfg:chain:export:(\d+)$"))
async def on_chain_export(call: CallbackQuery, lang: str) -> None:
    chain_id = int(call.data.split(":")[3])
    tg_id = call.from_user.id
    row = await db.get_chain(tg_id, chain_id)
    if row is None:
        await call.answer(t(lang, "chain_none"), show_alert=True)
        return
    hops = chainmod.normalise_hops(row.get("hops"))
    ok, reason, parsed = chainmod.validate(hops)
    if not ok:
        await call.answer(t(lang, reason, max=num(chainmod.MAX_HOPS, lang)), show_alert=True)
        return
    import json as _json

    config = chainmod.build_config(parsed)
    payload = _json.dumps(config, indent=2, ensure_ascii=False)
    await call.message.answer_document(
        BufferedInputFile(payload.encode("utf-8"), filename=f"autovless-chain-{chain_id}.json"),
        caption=t(lang, "chain_export_done"),
        reply_markup=keyboards.simple_back(lang, "cfg:chain"),
    )
    await call.answer()
