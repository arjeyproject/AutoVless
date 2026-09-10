"""The device and operator pickers, and the admin controls for both pools.

Two audiences, one file, because they are two ends of the same pipe.

**Users** press build and are asked exactly two questions.

*Which device.* This is not a nicety. An AmneziaWG config carries ``Jc``,
``Jmin``, ``Jmax``, ``S1``-``S4`` and ``H1``-``H4`` inside ``[Interface]``, and
the official WireGuard app on iOS is a strict parser: it meets a key it does not
recognise, decides the file is not a WireGuard config, and refuses all of it with
no usable error. Every config the bot handed out was AmneziaWG, so every iPhone
user got "the protocol does not run" and blamed the endpoint. iPhone and macOS now
get clean standard WireGuard; Android and Windows keep the full junk train. The
answer travels in the callback data rather than FSM state, because a navigation in
between used to clear the state and the next tap did nothing at all.

*Which operator.* Irancell gets an IPv6 endpoint because that is the path MTN
leaves alone; everyone else gets IPv4. Nothing is guessed from the phone number or
the language: a wrong guess here is a config that cannot connect and a user who
blames the bot.

**Admins** get a pool screen with four verbs. *Refresh* goes hunting for new
endpoints in the background. *Full check* re-pings everything already stored,
deletes the dead, re-sorts the survivors by ping and prints a straight verdict:
healthy, short, or empty. *Add IPv4* and *Add IPv6* pin endpoints the admin
already trusts into one pool each. Between presses the agent in ``bot.warppool``
does the automatic half of that job on a timer, so the buttons exist to see its
work and to force it, never to be the only thing that does it.

Why hand entry earns its buttons
--------------------------------
Cloudflare's IPv6 WARP prefixes are reachable from an Irancell handset and not
from most Iranian VPS hosts, so the box that scans usually has no IPv6 route and
the IPv6 pool - the one Irancell users are served from - can never fill by
itself. The admin, meanwhile, has a list of IPv6 endpoints that work. Two
buttons, one per family, never mixed: the family *is* the operator mapping, so it
is a decision the admin makes explicitly and not one inferred from a paste.

A pinned endpoint is not a privileged one. It goes through the same real
handshake, the same WarpEP health floor and the same ``warp_pool.pick`` as a
scanned one, so "only healthy endpoints reach users" still holds. What it does
get is permanence: hygiene never trims it away, and if it dies it is sidelined
and shown as dead rather than silently deleted.

Every screen here also has to answer *why* when the answer is zero. A refresh
that reports "48 addresses swept, 0 answered" is true and useless: the cause is
either no route for that family on this host, a probing key Cloudflare does not
answer, or genuine filtering, and those three need three completely different
fixes. ``report.note`` carries the diagnosis and this module prints it.

This router is registered ahead of ``handlers.warp`` so ``wg:net`` and the device
picker land here. No handler in this module ever awaits a scan: every sweep runs
as a background task and edits the message that started it.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from .. import db, keyboards, operators, warpconf, warpep, warpmanual, warpstore
from .. import warp as warpcore
from ..config import settings
from ..i18n import device_label, num, t
from ..platforms import default_platform, normalise_platform
from ..utils import ago, edit, esc, ping_label
from ..warpep import V4, V6
from ..warppool import AuditReport, RefreshReport, warp_pool
from ..warptune import TUNE

log = logging.getLogger("autovless.handlers.pool")
router = Router(name="pool")

# Which endpoint family each button hands out, and which operator profile it maps
# to. This table is the whole product decision, so it lives in one visible place.
CHOICES: dict[str, dict[str, str]] = {
    "mtn": {"family": V6, "operator": "mtn"},
    "other": {"family": V4, "operator": "other"},
}

# How each verdict on a pasted line is marked. The admin needs to see at a glance
# which of their addresses made it and which did not.
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

# Lines printed back after an import before the list is cut short.
REPORT_LINES = 24

# Live background jobs, held so the loop cannot collect them mid-sweep.
_jobs: set[asyncio.Task] = set()


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
    """Which button on the user side this pool feeds. Named on every screen."""
    return t(lang, "btn.wg_irancell" if family == V6 else "btn.wg_other")


def _app_link() -> str:
    """AmneziaVPN, as a real tappable store link rather than a bare app name."""
    return f'<a href="{keyboards.AMNEZIA_PLAY_URL}">AmneziaVPN</a>'


def _mark(full: bool) -> str:
    return "\u2705" if full else "\u26a0\ufe0f"


def _out_of(value: object, lang: str) -> str:
    return f"{num(int(value or 0), lang)}/{num(100, lang)}"


def _note_line(note: str, lang: str) -> str:
    """The one line that turns a zero into something an operator can act on."""
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


# --------------------------------------------------------------------- #
# user flow: which device, then which operator, then a config
# --------------------------------------------------------------------- #


async def show_device(event: CallbackQuery | Message, lang: str) -> None:
    """Step one of every WARP flow: which phone is this for.

    Asked rather than guessed, because the answer changes what is *inside* the
    file and getting it wrong means the file will not load at all.
    """
    await edit(event, t(lang, "wg.pick_device"), keyboards.device_picker(lang))


async def show_network(event: CallbackQuery | Message, lang: str, platform: str) -> None:
    """Step two: which operator. Shows how full each pool is, so nobody flies blind."""
    v4 = await warpstore.counts(V4)
    v6 = await warpstore.counts(V6)
    body = t(
        lang,
        "wg.pick_net",
        v4=num(v4["healthy"], lang),
        v6=num(v6["healthy"], lang),
        target=num(TUNE.pool_target, lang),
    )
    body += "\n\n" + t(lang, "wg.device_picked", device=device_label(platform, lang))
    await edit(event, body, keyboards.warp_network(lang, platform))


@router.callback_query(F.data == "wg:net")
async def on_pick_device(call: CallbackQuery, lang: str) -> None:
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return
    await show_device(call, lang)
    await call.answer()


# ``:f:`` in the tail means the device picker was opened by an export button, and
# ``handlers.warp`` owns that. Excluding it here matters because this router is
# registered first and would otherwise swallow the export flow.
@router.callback_query(F.data.startswith("wg:dev:") & ~F.data.contains(":f:"))
async def on_device_chosen(call: CallbackQuery, lang: str) -> None:
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return
    platform = normalise_platform((call.data or "").split(":")[2:3] and (call.data or "").split(":")[2])
    await show_network(call, lang, platform)
    await call.answer()


@router.callback_query(F.data.startswith("wg:net:"))
async def on_network_chosen(call: CallbackQuery, lang: str) -> None:
    """Build and deliver a config on an endpoint of the right family.

    Callback shapes, and why the platform is optional: keyboards already sitting
    in somebody's chat history predate the device picker, so a tail without a
    platform is honoured and falls back to Android rather than raising.

      wg:net:mtn[:platform]
      wg:net:other[:platform]
      wg:net:next:<family>[:platform]
    """
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return

    tail = (call.data or "").split(":")[2:]
    rotate = bool(tail and tail[0] == "next")
    if rotate:
        family = warpep.normalise_family(tail[1] if len(tail) > 1 else V4)
        operator = "mtn" if family == V6 else "other"
        platform = normalise_platform(tail[2] if len(tail) > 2 else default_platform())
    else:
        choice = CHOICES.get(tail[0] if tail else "other", CHOICES["other"])
        family = choice["family"]
        operator = choice["operator"]
        platform = normalise_platform(tail[1] if len(tail) > 1 else default_platform())

    await call.answer()
    notice = await call.message.answer(t(lang, "wg.making", family=_family_label(family, lang)))
    await _deliver(call, notice, lang, family, operator, rotate, platform)


async def _deliver(
    call: CallbackQuery,
    notice: Message,
    lang: str,
    family: str,
    operator: str,
    rotate: bool,
    platform: str,
) -> None:
    """Identity, endpoints, config, instructions. In that order, or not at all."""
    record = await db.get_warp_user(call.from_user.id)
    identity = (record or {}).get("identity")
    if not identity:
        try:
            identity = await warpcore.provision()
        except warpcore.WarpError as error:
            log.warning("warp provisioning failed: %s", error)
            await notice.edit_text(t(lang, "wg.identity_failed", reason=esc(error)))
            return

    endpoints = await warp_pool.pick(family, count=settings.warp_per_config)
    if rotate and len(endpoints) > 1:
        # "Next endpoint" has to mean the one after the address that just failed
        # them, not a reshuffle that can hand back the same one.
        endpoints = endpoints[1:] + endpoints[:1]

    if not endpoints:
        # ``pick`` has already kicked off a refresh. Say so plainly rather than
        # shipping a config built on an address nobody has tested. If the host has
        # no route for that family at all, say *that* instead: no amount of
        # waiting is going to fix it, but an admin pinning known good endpoints
        # by hand will.
        key = "wg.pool_no_route" if not warpep.reachable(family) else "wg.pool_cold"
        await notice.edit_text(
            t(lang, key, family=_family_label(family, lang)),
            reply_markup=keyboards.warp_network(lang, platform),
        )
        return

    await db.save_warp_user(call.from_user.id, identity, endpoints)
    await db.log_event("warp_build", call.from_user.id, f"{operator}/{family}/{platform}")

    # Everything from here is rendering and sending. It used to be unguarded, and
    # a single missing function in the renderer meant the user watched a notice
    # that never turned into a file. If this breaks again it says so on screen.
    try:
        await _send_config(call, notice, lang, family, operator, platform, identity, endpoints)
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001
        log.exception("could not render or deliver the warp config")
        try:
            await notice.edit_text(
                t(lang, "wg.render_failed", reason=esc(str(error)[:180])),
                reply_markup=keyboards.warp_network(lang, platform),
            )
        except TelegramBadRequest:
            log.info("could not report the delivery failure")


async def _send_config(
    call: CallbackQuery,
    notice: Message,
    lang: str,
    family: str,
    operator: str,
    platform: str,
    identity: dict,
    endpoints: list[dict],
) -> None:
    """Render for this exact platform, send the file, then the instructions."""
    clean = warpconf.is_clean_for(platform)
    profile = warpcore.obfuscation(identity.get("private_key", ""))
    body = warpconf.conf_for(identity, endpoints, platform=platform, profile=profile)
    device = device_label(platform, lang)

    # The endpoint actually written into the file, which is not always the first
    # row: iOS prefers IPv4 when the pool holds both.
    head_label = warpconf.label(endpoints, 0, platform)
    ordered = warpconf.order_for(endpoints, platform)
    head = ordered[0] if ordered else {}

    caption_key = "wg.caption_clean" if clean else "wg.caption"
    # The file first, then the instructions. A Telegram caption caps out around a
    # thousand characters and the how-to does not fit inside one.
    await call.message.answer_document(
        BufferedInputFile(
            body.encode("utf-8"),
            filename=warpconf.filename(family, "plain" if clean else "awg", platform),
        ),
        caption=t(
            lang,
            caption_key,
            family=_family_label(family, lang),
            device=device,
        ),
    )

    common = {
        "operator": esc(operators.label(operator, lang) or operator),
        "family": _family_label(family, lang),
        "endpoint": esc(head_label),
        "ping": ping_label(head.get("latency"), lang),
        "health": _out_of(head.get("health"), lang),
        "spares": num(max(0, len(endpoints) - 1), lang),
        "mtu": num(settings.warp_mtu, lang),
    }
    if clean:
        text = t(lang, "wg.sent_clean", device=device, **common)
    else:
        text = t(
            lang,
            "wg.sent",
            jc=num(profile["jc"], lang),
            jmin=num(profile["jmin"], lang),
            jmax=num(profile["jmax"], lang),
            app=_app_link(),
            **common,
        )

    try:
        await notice.edit_text(text, reply_markup=keyboards.warp_delivered(lang, family, platform))
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
    # The hand entered endpoints get their own line rather than more placeholders
    # inside ``pool.screen``: they are a different kind of thing from a scan
    # result and the admin needs to see at a glance how much of each pool is
    # theirs.
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
    """One stored endpoint, with everything that was actually proven about it.

    The hand icon matters: an admin looking at a thin pool needs to know which
    rows the scanner found and which ones they pinned themselves.
    """
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
    """The background half of the refresh button."""
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
    """Answers instantly. The sweep runs beside this handler and reports back."""
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
async def on_manual_ask(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    """Ask for a pasted list for exactly one family."""
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
        # The single most important sentence on this screen when it applies: the
        # host cannot test this family, so whatever is pasted is taken on trust.
        text += "\n" + t(lang, "pool.manual_no_route", family=_family_label(family, lang))
    await edit(call, text, keyboards.pool_manual_cancel(lang))
    await call.answer()


@router.message(PoolFlow.manual, F.text)
async def on_manual_text(message: Message, state: FSMContext, lang: str, is_admin: bool) -> None:
    """Take the paste, answer immediately, prove the endpoints in the background."""
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
    line = (
        f"{mark} <code>{esc(entry.label)}</code> \u00b7 "
        f"{t(lang, f'pool.manual_v_{entry.verdict}')}"
    )
    if entry.verdict in {"stored", "weak"}:
        line += (
            f" \u00b7 {ping_label(entry.latency, lang)} \u00b7 "
            f"\u2764\ufe0f {num(entry.health, lang)}"
        )
    return line


def _manual_text(report: warpmanual.ImportReport, lang: str) -> str:
    """The whole outcome of one paste, line by line. Nothing summarised away."""
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
    """The background half of hand entry: real handshakes, then the verdicts."""
    try:
        report = await warpmanual.import_pool(family, body)
        text = _manual_text(report, lang)
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001
        log.exception("manual endpoint import failed")
        text = t(lang, "pool.manual_failed", reason=esc(str(error)[:180]))
    counts = await warpmanual.both()
    try:
        await notice.edit_text(
            text,
            reply_markup=keyboards.pool_manual(lang, counts[V4]["total"], counts[V6]["total"]),
        )
    except TelegramBadRequest as error:
        log.info("could not update the manual import notice: %s", error)


async def show_manual(event: CallbackQuery | Message, lang: str) -> None:
    """Everything an admin has pinned, per family, with what it measured."""
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
    """Re-probe only the pinned endpoints. Cheaper than the full audit, and the
    question an admin staring at this screen is actually asking."""
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
            reply_markup=keyboards.pool_manual(lang, counts[V4]["total"], counts[V6]["total"]),
        )
    except TelegramBadRequest as error:
        log.info("could not update the manual check notice: %s", error)


@router.callback_query(F.data.startswith("pool:manual:ask:"))
async def on_manual_clear_ask(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    """Deleting a whole family's pinned list asks first. It is not recoverable."""
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
        return t(lang, "pool.audit_failed", reason=esc(report.reason or "-")) + _note_line(
            report.note, lang
        )

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
        target=num(TUNE.pool_target, lang),
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
    """Is the pool actually healthy? This is the button that answers it."""
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return
    await state.clear()

    await call.answer(t(lang, "btn.pool_audit"))
    notice = await call.message.answer(t(lang, "pool.audit_started"))
    _spawn(_run_audit(notice, lang), "pool-audit")
