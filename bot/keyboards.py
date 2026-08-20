"""Inline keyboards. Every screen is reachable and every screen has a way back."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .config import settings
from .i18n import t
from .operators import OPERATORS

CF_SIGNUP_URL = "https://dash.cloudflare.com/sign-up"
CF_TOKEN_URL = (
    "https://dash.cloudflare.com/profile/api-tokens"
    "?permissionGroupKeys=%5B%7B%22key%22%3A%22workers_scripts%22%2C%22type%22%3A%22edit%22%7D%2C"
    "%7B%22key%22%3A%22account_settings%22%2C%22type%22%3A%22read%22%7D%2C"
    "%7B%22key%22%3A%22zone%22%2C%22type%22%3A%22read%22%7D%2C"
    "%7B%22key%22%3A%22dns%22%2C%22type%22%3A%22edit%22%7D%5D"
    "&accountId=*&zoneId=all&name=AutoVless"
)

BULLET = "\u2022"
TICKET_MARKS = {"open": "\U0001f7e0", "answered": "\u2705", "closed": "\U0001f512"}


def _b(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def ticket_mark(status: object) -> str:
    return TICKET_MARKS.get(str(status), BULLET)


def back_row(lang: str, target: str = "nav:menu") -> list[InlineKeyboardButton]:
    return [_b(t(lang, "btn.back"), target)]


def main_menu(lang: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [_b(t(lang, "btn.build"), "nav:build")],
        [_b(t(lang, "btn.panel"), "nav:panel")],
        [_b(t(lang, "btn.warp"), "nav:warp")],
        [_b(t(lang, "btn.convert"), "nav:convert")],
        [_b(t(lang, "btn.apps"), "nav:apps"), _b(t(lang, "btn.guide"), "nav:guide")],
        [_b(t(lang, "btn.status"), "nav:status"), _b(t(lang, "btn.operator"), "nav:operator")],
        [_b(t(lang, "btn.support"), "nav:support"), _b(t(lang, "btn.donate"), "nav:donate")],
        [_b(t(lang, "btn.lang"), "nav:lang")],
    ]
    if is_admin:
        rows.append([_b(t(lang, "btn.admin"), "adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def token_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn.cf_signup"), url=CF_SIGNUP_URL)],
            [InlineKeyboardButton(text=t(lang, "btn.cf_token"), url=CF_TOKEN_URL)],
            back_row(lang),
        ]
    )


def panel_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.qr"), "panel:qr"), _b(t(lang, "btn.sub"), "panel:sub")],
            [_b(t(lang, "btn.clash"), "panel:clash"), _b(t(lang, "btn.singbox"), "panel:singbox")],
            [_b(t(lang, "btn.single"), "panel:single"), _b(t(lang, "btn.ping"), "panel:ping")],
            [_b(t(lang, "btn.rescan"), "panel:rescan")],
            [_b(t(lang, "btn.rebuild"), "panel:rebuild")],
            [_b(t(lang, "btn.delete"), "panel:delete")],
            back_row(lang),
        ]
    )


def confirm_menu(lang: str, yes: str, no: str = "nav:panel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_b(t(lang, "btn.confirm"), yes), _b(t(lang, "btn.cancel"), no)]]
    )


def operator_menu(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, profile in OPERATORS.items():
        builder.button(text=profile["en" if lang == "en" else "fa"], callback_data=f"op:{code}")
    builder.adjust(2)
    builder.row(*back_row(lang))
    return builder.as_markup()


def join_menu(lang: str, channels: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for channel in channels:
        title = channel.get("title") or channel.get("chat_id")
        invite = channel.get("invite")
        if invite:
            rows.append([InlineKeyboardButton(text=f"\U0001f4e2 {title}", url=invite)])
    rows.append([_b(t(lang, "btn.joined"), "join:check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def simple_back(lang: str, target: str = "nav:menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[back_row(lang, target)])


# ---------------------------------------------------------------- support


def support_menu(lang: str, has_thread: bool) -> InlineKeyboardMarkup:
    """User facing support home."""
    rows: list[list[InlineKeyboardButton]] = [[_b(t(lang, "btn.support_new"), "sup:new")]]
    if has_thread:
        rows.append([_b(t(lang, "btn.support_thread"), "sup:thread")])
    if settings.support_url:
        rows.append(
            [InlineKeyboardButton(text=t(lang, "btn.support_direct"), url=settings.support_url)]
        )
    rows.append(back_row(lang))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def support_user_reply(lang: str) -> InlineKeyboardMarkup:
    """Attached to an admin answer so the user can keep the thread going."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.support_new"), "sup:new")],
            back_row(lang),
        ]
    )


def support_list(
    lang: str,
    tickets: list[dict],
    scope: str = "open",
    enabled: bool = True,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for ticket in tickets:
        who = ticket.get("username") or ticket.get("first_name") or ticket.get("tg_id")
        unread = ticket.get("unread_admin") or 0
        badge = f" ({unread})" if unread else ""
        label = f"{ticket_mark(ticket.get('status'))} #{ticket['id']} \u00b7 {who}{badge}"
        rows.append([_b(label, f"sup:open:{ticket['id']}")])
    toggle = (
        ("btn.tickets_all", "sup:list:all")
        if scope != "all"
        else ("btn.tickets_open", "sup:list:open")
    )
    rows.append([_b(t(lang, toggle[0]), toggle[1])])
    rows.append([_b(t(lang, "support.toggle_on" if enabled else "support.toggle_off"), "sup:toggle")])
    rows.append(back_row(lang, "adm:menu"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def support_ticket(
    lang: str,
    ticket_id: int,
    closed: bool = False,
    scope: str = "open",
) -> InlineKeyboardMarkup:
    action = (
        ("btn.reopen_ticket", f"sup:reopen:{ticket_id}")
        if closed
        else ("btn.close_ticket", f"sup:close:{ticket_id}")
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.reply"), f"sup:reply:{ticket_id}")],
            [_b(t(lang, action[0]), action[1])],
            [_b(t(lang, "btn.tickets"), f"sup:list:{scope}")],
            back_row(lang, "adm:menu"),
        ]
    )


# ------------------------------------------------------------------ admin


def admin_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.stats"), "adm:stats"), _b(t(lang, "btn.users"), "adm:users")],
            [_b(t(lang, "btn.broadcast"), "adm:broadcast"), _b(t(lang, "btn.channels"), "adm:channels")],
            [_b(t(lang, "btn.engine"), "adm:engine"), _b(t(lang, "btn.options"), "adm:options")],
            [_b(t(lang, "btn.panels"), "adm:panels"), _b(t(lang, "btn.logs"), "adm:logs")],
            [_b(t(lang, "btn.tickets"), "sup:list:open"), _b(t(lang, "btn.backup"), "adm:backup")],
            back_row(lang),
        ]
    )


def admin_channels(lang: str, channels: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for channel in channels:
        title = channel.get("title") or channel["chat_id"]
        rows.append([_b(f"\U0001f5d1 {title}", f"adm:chdel:{channel['chat_id']}")])
    rows.append([_b(t(lang, "btn.add"), "adm:chadd")])
    rows.append(back_row(lang, "adm:menu"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_options(lang: str, values: dict[str, bool]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key, enabled in values.items():
        mark = "\u2705" if enabled else "\u26aa\ufe0f"
        rows.append([_b(f"{mark} {t(lang, f'opt.{key}')}", f"adm:opt:{key}")])
    rows.append(back_row(lang, "adm:menu"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_engine(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.scan_now"), "adm:scan")],
            back_row(lang, "adm:menu"),
        ]
    )


def admin_user(lang: str, tg_id: int, banned: bool) -> InlineKeyboardMarkup:
    action = ("btn.unban", f"adm:unban:{tg_id}") if banned else ("btn.ban", f"adm:ban:{tg_id}")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, action[0]), action[1])],
            [_b(t(lang, "btn.users"), "adm:users")],
            back_row(lang, "adm:menu"),
        ]
    )
