"""The operator picker, and the admin controls for the two endpoint pools.

Two audiences, one file, because they are two ends of the same pipe.

**Users** press build and are asked one question: which operator. Irancell gets an
IPv6 endpoint because that is the path MTN leaves alone; everyone else gets IPv4.
Nothing is guessed from the phone number or the language, because a wrong guess
here is a config that cannot connect and a user who blames the bot.

**Admins** get a pool screen with exactly two verbs. *Refresh* goes hunting for
new endpoints in the background. *Full check* re-pings everything already stored,
deletes the dead, re-sorts the survivors by ping and prints a straight verdict:
healthy, short, or empty. Between presses the agent in ``bot.warppool`` does the
same job on a timer, so the buttons exist to see its work and to force it, never
to be the only thing that does it.

Every screen here also has to answer *why* when the answer is zero. A refresh
that reports "48 addresses swept, 0 answered" is true and useless: the cause is
either no route for that family on this host, a probing key Cloudflare does not
answer, or genuine filtering, and those three need three completely different
fixes. ``report.note`` carries the diagnosis and this module prints it.

This router is registered ahead of ``handlers.warp`` so ``wg:net`` lands here.
No handler in this module ever awaits a scan: every sweep runs as a background
task and edits the message that started it.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from .. import db, keyboards, operators, warpconf, warpep, warpstore
from .. import warp as warpcore
from ..config import settings
from ..i18n import num, t
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

# Live background jobs, held so the loop cannot collect them mid-sweep.
_jobs: set[asyncio.Task] = set()


def _spawn(coro, name: str) -> None:
    task = asyncio.create_task(coro, name=name)
    _jobs.add(task)
    task.add_done_callback(_jobs.discard)


def _family_label(family: str, lang: str) -> str:
    return t(lang, "wg.family_v6" if family == V6 else "wg.family_v4")


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
    return f"{esc(str(status.get('identity') or '-'))} · {state}"


def _routes_line(status: dict, lang: str) -> str:
    routes = status.get("routes") or {}
    parts = []
    for family in (V4, V6):
        mark = "\u2705" if routes.get(family) else "\u26d4\ufe0f"
        parts.append(f"{_family_label(family, lang)} {mark}")
    return " · ".join(parts)


# --------------------------------------------------------------------- #
# user flow: pick an operator, get a config
# --------------------------------------------------------------------- #


@router.callback_query(F.data == "wg:net")
async def on_pick_network(call: CallbackQuery, lang: str) -> None:
    """The two glass buttons. Shows how full each pool is, so nobody flies blind."""
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return

    v4 = await warpstore.counts(V4)
    v6 = await warpstore.counts(V6)
    await edit(
        call,
        t(
            lang,
            "wg.pick_net",
            v4=num(v4["healthy"], lang),
            v6=num(v6["healthy"], lang),
            target=num(TUNE.pool_target, lang),
        ),
        keyboards.warp_network(lang),
    )
    await call.answer()


@router.callback_query(F.data.startswith("wg:net:"))
async def on_network_chosen(call: CallbackQuery, lang: str) -> None:
    """Build and deliver a config on an endpoint of the right family."""
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return

    tail = (call.data or "").split(":")[2:]
    rotate = bool(tail and tail[0] == "next")
    if rotate:
        family = warpep.normalise_family(tail[1] if len(tail) > 1 else V4)
        operator = "mtn" if family == V6 else "other"
    else:
        choice = CHOICES.get(tail[0] if tail else "other", CHOICES["other"])
        family = choice["family"]
        operator = choice["operator"]

    await call.answer()
    notice = await call.message.answer(t(lang, "wg.making", family=_family_label(family, lang)))
    await _deliver(call, notice, lang, family, operator, rotate)


async def _deliver(
    call: CallbackQuery,
    notice: Message,
    lang: str,
    family: str,
    operator: str,
    rotate: bool,
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
        # waiting is going to fix it.
        key = "wg.pool_no_route" if not warpep.reachable(family) else "wg.pool_cold"
        await notice.edit_text(
            t(lang, key, family=_family_label(family, lang)),
            reply_markup=keyboards.warp_network(lang),
        )
        return

    await db.save_warp_user(call.from_user.id, identity, endpoints)
    await db.log_event("warp_build", call.from_user.id, f"{operator}/{family}")

    profile = warpcore.obfuscation(identity.get("private_key", ""))
    body = warpconf.amnezia_conf(identity, endpoints, profile)
    head = endpoints[0]

    # The file first, then the instructions. A Telegram caption caps out around a
    # thousand characters and the how-to does not fit inside one.
    await call.message.answer_document(
        BufferedInputFile(body.encode("utf-8"), filename=warpconf.filename(family, "awg")),
        caption=t(lang, "wg.caption", family=_family_label(family, lang)),
    )
    try:
        await notice.edit_text(
            t(
                lang,
                "wg.sent",
                operator=esc(operators.label(operator, lang) or operator),
                family=_family_label(family, lang),
                endpoint=esc(warpconf.label(endpoints)),
                ping=ping_label(head.get("latency"), lang),
                health=_out_of(head.get("health"), lang),
                spares=num(max(0, len(endpoints) - 1), lang),
                jc=num(profile["jc"], lang),
                jmin=num(profile["jmin"], lang),
                jmax=num(profile["jmax"], lang),
                mtu=num(settings.warp_mtu, lang),
                app=_app_link(),
            ),
            reply_markup=keyboards.warp_delivered(lang, family),
        )
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
    await edit(event, text, keyboards.pool_menu(lang))


@router.callback_query(F.data == "pool:home")
async def on_pool_home(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not is_admin:
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    await show_pool(call, lang)
    await call.answer()


@router.callback_query(F.data == "pool:list")
async def on_pool_list(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    """Every endpoint in both pools, in ping order, with what was proven about it."""
    if not is_admin:
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return

    blocks: list[str] = []
    for family in (V4, V6):
        rows = await warpstore.pool(family, limit=TUNE.pool_target)
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
            flag = int(row.get("verified", -1) or -1)
            verified = True if flag == 1 else (False if flag == 0 else None)
            points = int(row.get("health") or 0)
            blocks.append(
                f"{num(index, lang)}. {warpep.badge(points, verified)} "
                f"<code>{esc(warpep.host_port(row['ip'], row['port']))}</code> \u00b7 "
                f"{ping_label(row['latency'], lang)} \u00b7 "
                f"\u2764\ufe0f {num(points, lang)}"
            )

    listing = "\n".join(blocks).strip() or t(lang, "pool.list_empty")
    await edit(call, t(lang, "pool.list", list=listing), keyboards.pool_menu(lang))
    await call.answer()


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
async def on_pool_refresh(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    """Answers instantly. The sweep runs beside this handler and reports back."""
    if not is_admin:
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return

    tail = (call.data or "").split(":")[2:]
    family = warpep.normalise_family(tail[0]) if tail else None

    await call.answer(t(lang, "btn.pool_refresh"))
    notice = await call.message.answer(t(lang, "pool.refresh_started"))
    _spawn(_run_refresh(notice, lang, family), f"pool-refresh-{family or 'all'}")


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
async def on_pool_audit(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    """Is the pool actually healthy? This is the button that answers it."""
    if not is_admin:
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    if not await db.get_flag("warp_enabled"):
        await call.answer(t(lang, "warp.off"), show_alert=True)
        return

    await call.answer(t(lang, "btn.pool_audit"))
    notice = await call.message.answer(t(lang, "pool.audit_started"))
    _spawn(_run_audit(notice, lang), "pool-audit")
