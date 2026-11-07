"""Cloudflare token intake and the panel build flow."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import db, deploy, edge, keyboards, operators, pages, screens, store, subgw, vless
from ..cloudflare import token_looks_valid
from ..i18n import num, t
from ..utils import edit, esc, ping_label

log = logging.getLogger("autovless.build")
router = Router(name="build")

_in_flight: set[int] = set()


class BuildFlow(StatesGroup):
    token = State()


def _domain_note(lang: str, host: str) -> str:
    """Say plainly which front door the configs use, and what to do about it."""
    dev_host = edge.is_dev_host(host) or pages.is_pages_host(host)
    if not dev_host:
        if lang == "en":
            return (
                "\n\n\U0001f6e1 Your configs use your own domain "
                f"<code>{esc(host)}</code> instead of the platform default, which is what "
                "lets them get past filtering in Iran."
            )
        return (
            "\n\n\U0001f6e1 کانفیگ‌ها به جای دامنه‌ی پیش‌فرض پلتفرم روی دامنه‌ی خودت "
            f"<code>{esc(host)}</code> ساخته شدند؛ همین باعث می‌شود از فیلترینگ ایران رد شوند."
        )
    if lang == "en":
        return (
            "\n\n\u26a0\ufe0f No domain was found on your Cloudflare account, so these "
            "configs still use the platform default host, which is filtered on most Iranian "
            "networks. Add any domain (a free one works) to Cloudflare, create a new "
            "token with the button (it now includes the Pages permission), then "
            "press Rebuild. The bot moves the panel onto the domain by itself."
        )
    return (
        "\n\n\u26a0\ufe0f روی اکانت کلادفلرت دامنه‌ای پیدا نشد و کانفیگ‌ها هنوز روی "
        "هاست پیش‌فرض پلتفرم هستند که روی بیشتر اینترنت‌های ایران فیلتر است. یک دامنه (حتی "
        "رایگان) به کلادفلر اضافه کن، با دکمه‌ی ساخت توکن یک توکن جدید بساز (حالا "
        "دسترسی Pages هم دارد) و «بازسازی پنل» را بزن؛ ربات خودش پنل "
        "را روی دامنه منتقل می‌کند."
    )


@router.callback_query(F.data == "nav:build")
async def on_build(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    if not await db.get_flag("builds_enabled"):
        await call.answer(t(lang, "builds_off"), show_alert=True)
        return
    await state.set_state(BuildFlow.token)
    await state.update_data(mode="create")
    await edit(call, t(lang, "token_intro"), keyboards.token_menu(lang))
    await call.answer()


@router.message(BuildFlow.token, F.text)
async def on_token(message: Message, state: FSMContext, lang: str) -> None:
    tg_id = message.from_user.id
    raw = (message.text or "").strip()

    if not token_looks_valid(raw):
        await message.answer(t(lang, "token_bad_format"))
        return

    # Never leave a live API token sitting in the chat history.
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        log.debug("could not delete the token message")

    if tg_id in _in_flight:
        await message.answer(t(lang, "busy"))
        return

    data = await state.get_data()
    mode = data.get("mode", "create")
    await state.clear()

    reuse = None
    if mode == "rebuild":
        existing = await db.get_panel(tg_id)
        if existing:
            reuse = {
                "account_id": existing["account_id"],
                "script_name": existing["script_name"],
                "uuid": existing["uuid"],
            }

    await run_build(message, tg_id, lang, raw, reuse=reuse)


async def run_build(
    message: Message,
    tg_id: int,
    lang: str,
    token: str,
    reuse: dict | None = None,
    force_scan: bool = False,
) -> None:
    """Drive a build, streaming progress into a single message.

    The per-user lock is shared with the mini app's build flow: two guards
    that did not know about each other once let a bot rebuild and a mini app
    build race onto one Cloudflare account, and the slower one's save quietly
    reverted the faster one's custom-domain host.
    """
    if deploy.build_lock(tg_id).locked():
        await message.answer(t(lang, "busy"))
        return

    progress_message = await message.answer(
        t(lang, "build_progress", steps=deploy.render_steps(lang, 0, t))
    )

    async def on_step(index: int) -> None:
        await progress_message.edit_text(
            t(lang, "build_progress", steps=deploy.render_steps(lang, index, t))
        )

    _in_flight.add(tg_id)
    try:
        async with deploy.build_lock(tg_id):
            panel = await deploy.build(token, reuse=reuse, progress=on_step, force_scan=force_scan)
    except deploy.DeployError as error:
        reason = str(error.reason)
        lowered = reason.lower()
        if "clean ip pool" in reason:
            await progress_message.edit_text(t(lang, "no_clean_ip"))
        elif any(mark in lowered for mark in ("flagged", "blocked", "abusereply")):
            await progress_message.edit_text(t(lang, "account_blocked"))
        else:
            await progress_message.edit_text(t(lang, "token_rejected", reason=esc(reason)))
        await db.log_event("build_failed", tg_id, reason)
        return
    except Exception as error:  # noqa: BLE001
        log.exception("unexpected build failure")
        await progress_message.edit_text(t(lang, "error_generic", reason=esc(error)))
        await db.log_event("build_error", tg_id, str(error))
        return
    finally:
        _in_flight.discard(tg_id)

    await db.save_panel(
        tg_id=tg_id,
        account_id=panel.account_id,
        script_name=panel.script,
        host=panel.host,
        uuid=panel.uuid,
        token=token,
        endpoints=panel.endpoints,
        build_ms=panel.build_ms,
        relays=panel.relays,
        healthy=panel.healthy,
        deploy_target=panel.target,
    )
    await db.log_event("build_ok", tg_id, panel.host)

    # The chain pin was chosen before the panel row existed, so the UPDATE in
    # store.set_chain_pin silently hit nothing. The row is here now: write it
    # so every refresh reuses this exact relay until it actually dies.
    if panel.chain_relays:
        try:
            await store.set_chain_pin(panel.uuid, panel.chain_relays[0], panel.chain_country)
        except Exception:  # noqa: BLE001
            log.debug("could not record the chain pin after save", exc_info=True)

    user = await db.get_user(tg_id)
    operator = operators.label(user["operator"] if user else None, lang) or (
        "all operators" if lang == "en" else "\u0647\u0645\u0647 \u0627\u067e\u0631\u0627\u062a\u0648\u0631\u0647\u0627"
    )
    latencies = [e.get("latency") or 0 for e in panel.endpoints]
    ports = sorted({int(e["port"]) for e in panel.endpoints})

    # The one link the user actually needs: every endpoint, every protocol,
    # served from our own domain and refreshed by Update alone. The gateway
    # link when it exists - workers.dev does not resolve in Iran.
    if subgw.enabled():
        sub = subgw.link(tg_id, panel.uuid)
    else:
        sub = vless.sub_url(panel.uuid, panel.host)

    body = t(
        lang,
        "panel_ready",
        seconds=num(round(panel.build_ms / 1000, 1), lang),
        best=ping_label(min((v for v in latencies if v), default=None), lang),
        fast=num(sum(1 for value in latencies if value and value < 700), lang),
        count=num(len(panel.endpoints), lang),
        ports=" \u00b7 ".join(num(p, lang) for p in ports),
        operator=esc(operator),
        host=esc(panel.host),
        sub=esc(sub),
    )
    if not panel.healthy:
        body = f"{body}\n\n{t(lang, 'health_warn')}"
    body += _domain_note(lang, panel.host)

    await progress_message.edit_text(body, reply_markup=keyboards.panel_ready_menu(lang, sub))


@router.callback_query(F.data == "nav:panel")
async def on_panel(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    text, markup = await screens.panel_overview(call.from_user.id, lang)
    await edit(call, text, markup)
    await call.answer()
