"""Inline keyboards. Every screen is reachable and every screen has a way back."""

from __future__ import annotations

from typing import Optional

from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import apps as catalogue
from .config import settings
from .i18n import t
from .operators import OPERATORS
from .platforms import ORDER as PLATFORM_ORDER
from .platforms import label_key, normalise_platform, should_include_amnezia_keys

CF_SIGNUP_URL = "https://dash.cloudflare.com/sign-up"
# The pre-filled token template. Pages panels need Cloudflare Pages: Edit on
# top of the Workers permissions (the worker path stays as the fallback), so
# both permission sets ride along and the same token serves both targets.
CF_TOKEN_URL = (
    "https://dash.cloudflare.com/profile/api-tokens"
    "?permissionGroupKeys=%5B%7B%22key%22%3A%22page%22%2C%22type%22%3A%22edit%22%7D%2C"
    "%7B%22key%22%3A%22workers_scripts%22%2C%22type%22%3A%22edit%22%7D%2C"
    "%7B%22key%22%3A%22account_settings%22%2C%22type%22%3A%22read%22%7D%2C"
    "%7B%22key%22%3A%22zone%22%2C%22type%22%3A%22read%22%7D%2C"
    "%7B%22key%22%3A%22workers_routes%22%2C%22type%22%3A%22edit%22%7D%2C"
    "%7B%22key%22%3A%22dns%22%2C%22type%22%3A%22edit%22%7D%5D"
    "&accountId=*&zoneId=all&name=AutoVless"
)

# Telegram colours buttons natively since Bot API 9.4: ``style`` accepts
# "success" (green), "primary" (blue) and "danger" (red); a button without one
# gets the app-specific soft glass look.
#
# The palette system ("قرینه و یکدست") - one rule everywhere, and it is the rule
# the owner asked for by name:
#
#   1. ONE green button per menu: the first one, the action the screen exists
#      for (build the panel, open the subscription, run the smart scan).
#      Everything after it is blue. No alternation, no checkerboard - a menu
#      reads as "one leader, one rank of soldiers", symmetric down the page.
#   2. Pickers (devices, operators) are a rank with no leader: every choice is
#      blue, so no choice is promoted over another.
#   3. Semantic exceptions keep their meaning everywhere: destructive = red
#      (delete, wipe), navigation and copy buttons = glass. The user learns
#      the exceptions once and every menu in the bot looks like it was painted
#      by the same hand.
OK = "success"    # green - the one leading action of a menu
GO = "primary"    # blue - every other action
BAD = "danger"    # destructive only
SOFT = None       # navigation, copy, secondary


def checker(row: int, col: int = 0) -> str:
    """The one source of order: green at the top of the menu, blue after it.

    The name is kept because every existing call site already speaks it; the
    semantics are now the uniform ladder instead of a checkerboard."""
    return OK if row == 0 and col == 0 else GO


def _paint(text: str, *colour: str) -> str:
    """Kept for callers that still pass a legacy colour constant.

    Labels carry exactly one emoji of their own now, so nothing is prefixed;
    the argument is only consumed to keep every existing call site valid.
    """
    return text

AMNEZIA_PLAY_URL = "https://play.google.com/store/apps/details?id=org.amnezia.vpn"
AMNEZIA_WIN_URL = "https://github.com/amnezia-vpn/amnezia-client/releases/latest"
# The official WireGuard app. This is the one an iPhone config is built for, and
# sending an iPhone user to Google Play was its own small bug.
WIREGUARD_IOS_URL = "https://apps.apple.com/app/wireguard/id1441195209"
STREISAND_IOS_URL = "https://apps.apple.com/app/streisand/id6450534064"

BULLET = "\u2022"
TICKET_MARKS = {"open": "\U0001f7e0", "answered": "\u2705", "closed": "\U0001f512"}


def _b(text: str, data: str, style: Optional[str] = None) -> InlineKeyboardButton:
    kwargs: dict = {"text": text, "callback_data": data}
    if style:
        # Bot API 9.4 button colouring. aiogram passes the extra field through
        # untouched, so older clients simply ignore it and newer ones paint it.
        kwargs["style"] = style
    return InlineKeyboardButton(**kwargs)


def _u(text: str, url: str, style: Optional[str] = None) -> InlineKeyboardButton:
    kwargs: dict = {"text": text, "url": url}
    if style:
        kwargs["style"] = style
    return InlineKeyboardButton(**kwargs)


def _c(text: str, data: str, colour: Optional[str] = None) -> InlineKeyboardButton:
    """A coloured action button.

    Callers written against the old emoji palette pass a literal like GREEN or
    BLUE; those map onto the real styles, and the new names (OK/GO/BAD/SOFT)
    pass straight through.
    """
    return _b(text, data, LEGACY_STYLES.get(colour, colour))


def _cu(text: str, url: str, colour: Optional[str] = None) -> InlineKeyboardButton:
    return _u(text, url, LEGACY_STYLES.get(colour, colour))


def glass_button(text: str, callback: str, style: Optional[str] = OK) -> InlineKeyboardButton:
    """A full-width button. Telegram gives us one row per button and that is the
    only "glass" affordance the API has, so a glass button is simply a button
    that owns its row."""
    return _b(text, callback, style)


def copy_button(label: str, payload: str) -> InlineKeyboardButton:
    """A copy_text button: the client copies ``payload`` without sending anything.

    This is the Bot API 7.2 button type; every client that can render the
    coloured styles is far newer than it needs to be for this. Copy is a
    neutral tool, so it is always glass."""
    return InlineKeyboardButton(text=label, copy_text=CopyTextButton(text=payload), style=SOFT)


# Old call sites still hand the emoji constants over; map them so a rebuild
# mid-deploy keeps painting instead of silently going grey.
LEGACY_STYLES = {
    "\U0001f7e2": OK,      # green circle
    "\U0001f535": GO,      # blue circle
    "\U0001f534": BAD,     # red circle
    "\u26aa\ufe0f": SOFT,  # white circle
}


# ---------------------------------------------------------------- devices


def device_picker(lang: str, flow: str = "", back: str = "nav:warp") -> InlineKeyboardMarkup:
    """Which phone is this for. The first step of every WARP flow.

    ``flow`` is carried through in the callback data so the answer survives
    without any FSM state: empty means "go on to build a config", and
    ``f:<kind>`` means "render that export for the platform I just picked".
    Depending on state here is what used to make the picker a dead end - a
    navigation in between cleared it and the next tap did nothing at all.

    A picker has no leader: every device is blue, one uniform rank.
    """
    tail = f":{flow}" if flow else ""
    styles = (GO, GO, GO, GO, GO, GO)
    rows = [
        [_c(t(lang, label_key(name)), f"wg:dev:{name}{tail}", styles[index % len(styles)])]
        for index, name in enumerate(PLATFORM_ORDER)
    ]
    rows.append(back_row(lang, back))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def platform_picker(lang: str, flow: str = "") -> InlineKeyboardMarkup:
    """Older name for ``device_picker``, kept so nothing breaks mid-deploy."""
    return device_picker(lang, flow)


def ticket_mark(status: object) -> str:
    return TICKET_MARKS.get(str(status), BULLET)


def back_row(lang: str, target: str = "nav:menu") -> list[InlineKeyboardButton]:
    return [_c(t(lang, "btn.back"), target, SOFT)]


def main_menu(lang: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    """One green leader - build the panel - and a blue rank under it."""
    rows: list[list[InlineKeyboardButton]] = [
        [_c(t(lang, "btn.build"), "nav:build", OK)],
        [_c(t(lang, "btn.panel"), "nav:panel", GO)],
        [_c(t(lang, "btn.warp"), "nav:warp", GO)],
        [_c(t(lang, "btn.apps"), "nav:apps", GO)],
        [_c(t(lang, "btn.guide"), "nav:guide", SOFT), _c(t(lang, "btn.support"), "nav:support", GO)],
        [_c(t(lang, "btn.donate"), "nav:donate", GO), _c(t(lang, "btn.lang"), "nav:lang", SOFT)],
    ]
    if is_admin:
        rows.append([_c(t(lang, "btn.admin"), "adm:menu", BAD)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def token_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_cu(t(lang, "btn.cf_signup"), CF_SIGNUP_URL, GO)],
            [_cu(t(lang, "btn.cf_token"), CF_TOKEN_URL, GO)],
            back_row(lang),
        ]
    )


def panel_menu(lang: str) -> InlineKeyboardMarkup:
    """The turbo panel, reorganised around what a user actually takes away.

    One green leader - the all-in-one subscription link - then the protocol
    menu in symmetric pairs: singles + QR, Trojan + Clash, sing-box + Fragment,
    and one full-width refresh. The diagnostics (live ping, the AI/chain
    report, the second rescan, the second rebuild, an apps shortcut the main
    menu already owns) are gone: each was a button a user pressed once and
    never needed again, and five of them stood between the user and the
    configs. Delete stays the only red on the screen.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_c(t(lang, "btn.sub"), "panel:sub", OK)],
            [_c(t(lang, "btn.single"), "panel:single", GO), _c(t(lang, "btn.qr"), "panel:qr", GO)],
            [_c(t(lang, "btn.trojan"), "panel:trojan", GO), _c(t(lang, "btn.clash"), "panel:clash", GO)],
            [_c(t(lang, "btn.singbox"), "panel:singbox", GO), _c(t(lang, "btn.fragment"), "panel:fragment", GO)],
            [_c(t(lang, "btn.apply"), "panel:apply", GO)],
            [_c(t(lang, "btn.delete"), "panel:delete", BAD)],
            back_row(lang),
        ]
    )


def panel_ready_menu(lang: str, sub: str = "") -> InlineKeyboardMarkup:
    """Delivered under a fresh build.

    The subscription link is the product: open it, copy it, done. Copy is
    glass; the singles and the QR follow in one symmetric blue pair."""
    rows: list[list[InlineKeyboardButton]] = [
        [_c(t(lang, "btn.sub"), "panel:sub", OK)],
    ]
    if sub:
        rows.append([copy_button(t(lang, "btn.copy_sub"), sub)])
    rows += [
        [_c(t(lang, "btn.single"), "panel:single", GO), _c(t(lang, "btn.qr"), "panel:qr", GO)],
        [_c(t(lang, "btn.apply"), "panel:apply", GO), _c(t(lang, "btn.panel"), "nav:panel", GO)],
        back_row(lang, "nav:menu"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_menu(lang: str, yes: str, no: str = "nav:panel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_c(t(lang, "btn.confirm"), yes, OK), _c(t(lang, "btn.cancel"), no, SOFT)]
        ]
    )


def free_hint_menu(lang: str) -> InlineKeyboardMarkup:
    """Shown when the protocol menu is opened with no panel: build, or go free."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_c(t(lang, "btn.build"), "nav:build", OK)],
            [_c(t(lang, "btn.free"), "nav:free", GO)],
            back_row(lang),
        ]
    )


def join_menu(lang: str, channels: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for channel in channels:
        title = channel.get("title") or channel.get("chat_id")
        invite = channel.get("invite")
        if invite:
            rows.append([_u(f"\U0001f4e2 {title}", invite)])
    rows.append([_b(t(lang, "btn.joined"), "join:check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def simple_back(lang: str, target: str = "nav:menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[back_row(lang, target)])


# -------------------------------------------------------------------- apps


def apps_platforms(lang: str) -> InlineKeyboardMarkup:
    """Device picker for the app catalogue. Two per row so labels stay readable."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _b(t(lang, "btn.apps_android"), "apps:android", checker(0, 0)),
                _b(t(lang, "btn.apps_ios"), "apps:ios", checker(0, 1)),
            ],
            [
                _b(t(lang, "btn.apps_windows"), "apps:windows", checker(1, 0)),
                _b(t(lang, "btn.apps_macos"), "apps:macos", checker(1, 1)),
            ],
            [_b(t(lang, "btn.apps_linux"), "apps:linux", checker(2, 0))],
            [_b(t(lang, "btn.guide"), "nav:guide", SOFT)],
            back_row(lang),
        ]
    )


def apps_list(lang: str, platform: str, tag: str = "") -> InlineKeyboardMarkup:
    """One tappable link per app, recommended first, then the other platforms."""
    rows: list[list[InlineKeyboardButton]] = []
    for item in catalogue.listing(platform, tag):
        rows.append([_u(catalogue.label(item), item["url"])])

    others = [code for code in catalogue.PLATFORMS if code != platform]
    switch = [
        _b(t(lang, f"btn.apps_{code}"), f"apps:{code}:{tag}" if tag else f"apps:{code}", GO)
        for code in others
    ]
    for index in range(0, len(switch), 2):
        rows.append(switch[index : index + 2])

    rows.append([_b(t(lang, "btn.guide"), "nav:guide", SOFT)])
    rows.append(back_row(lang, "nav:apps"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ------------------------------------------------------------------- warp


def _warp_export_rows(lang: str, platform: str = "") -> list[list[InlineKeyboardButton]]:
    """The export buttons.

    With a known platform the file is rendered straight away (``wg:exp``). Without
    one the device is asked first (``wg:file``), because rendering AmneziaWG for
    somebody who turns out to hold an iPhone is the original bug.

    The AmneziaWG buttons are hidden entirely on a platform whose client rejects
    them: offering a button that cannot produce a working file is worse than not
    offering it.
    """
    name = normalise_platform(platform) if platform else ""
    if name:
        def target(kind: str) -> str:
            return f"wg:exp:{name}:{kind}"
    else:
        def target(kind: str) -> str:
            return f"wg:file:{kind}"

    rows: list[list[InlineKeyboardButton]] = []
    if not name or should_include_amnezia_keys(name):
        rows.append(
            [
                _b(t(lang, "btn.warp_awg"), target("awg")),
                _b(t(lang, "btn.warp_awg2"), target("awg2")),
            ]
        )
    rows.append(
        [
            _b(t(lang, "btn.warp_link"), "wg:link"),
            _b(t(lang, "btn.warp_qr"), "wg:qr"),
        ]
    )
    rows.append([_b(t(lang, "btn.warp_plain"), target("plain"))])
    rows.append(
        [
            _b(t(lang, "btn.warp_singbox"), target("singbox")),
            _b(t(lang, "btn.warp_clash"), target("clash")),
        ]
    )
    return rows


def _warp_identity_rows(lang: str) -> list[list[InlineKeyboardButton]]:
    """The actions that only mean anything once a user owns a WARP identity.

    The 3.0 pro layer rides along here: tuning and the backup pair sit with the
    other identity actions, so a user who already holds a config finds them
    without hunting through menus.
    """
    return [
        [_b(t(lang, "btn.warp_rebuild"), "wg:rebuild")],
        [
            _b(t(lang, "btn.wg_set"), "wg:set"),
            _b(t(lang, "btn.wg_bench"), "wg:bench"),
        ],
        [
            _b(t(lang, "btn.wg_backup"), "wg:backup"),
            _b(t(lang, "btn.wg_restore"), "wg:restore"),
        ],
        [
            _b(t(lang, "btn.warp_license"), "wg:license"),
            _b(t(lang, "btn.warp_delete"), "wg:del"),
        ],
    ]


def warp_menu(lang: str, has_identity: bool = False) -> InlineKeyboardMarkup:
    """The WARP home screen: one button, and it is the one everybody presses.

    This screen used to carry sixteen buttons - two AmneziaWG variants, plain
    WireGuard, a v2rayNG link, Clash, sing-box, an endpoint list, two kinds of
    scan, a licence field, a delete, an explainer - and the whole lot was a
    decision tree the user had to solve before getting anything. Every one of
    those was a question the bot can answer better itself, because the correct
    export follows from the platform and the correct endpoint follows from the
    operator, and both of those are asked next anyway.

    So: build. The flow behind it is auto WARP build, then platform, then
    operator, and the exports appear under the delivered config, where they are a
    follow up rather than a quiz. ``has_identity`` is still accepted so every
    existing caller keeps working.
    """
    rows: list[list[InlineKeyboardButton]] = [
        [glass_button(t(lang, "btn.warp_build"), "wg:net", OK)],
        back_row(lang),
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def warp_network(lang: str, platform: str = "") -> InlineKeyboardMarkup:
    """Every operator, one button each, two per row.

    Used to be a two-button question (Irancell vs everything else). Clean IPs
    are now ranked per operator - port priors plus the learned wins of that
    network's own users - so each of the six gets a real button of its own. The
    device picked a moment ago still rides along in the callback data so the
    config is rendered for the right client without any state to lose.
    """
    tail = f":{normalise_platform(platform)}" if platform else ""
    rows: list[list[InlineKeyboardButton]] = []
    pair: list[InlineKeyboardButton] = []
    for index, (code, profile) in enumerate(OPERATORS.items()):
        if not pair:
            # A picker has no leader: every operator is the same blue rank.
            row_styles = (GO, GO)
        pair.append(_c(profile["en" if lang == "en" else "fa"], f"wg:net:{code}{tail}", row_styles[len(pair)]))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    if platform:
        rows.append([_c(t(lang, "btn.wg_change_device"), "wg:net", SOFT)])
    rows.append(back_row(lang, "nav:warp"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def warp_delivered(lang: str, family: str, platform: str = "") -> InlineKeyboardMarkup:
    """Attached under a delivered config.

    This screen used to hand out the client link, four export pairs, the next
    endpoint and six identity actions right under a file the user has not even
    opened yet. All of that is gone on purpose: after every build the keyboard
    is exactly two buttons - change the device, or go back to the main menu.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_c(t(lang, "btn.wg_change_device"), "wg:net", GO)],
            [_c(t(lang, "btn.back_home"), "nav:menu", SOFT)],
        ]
    )


def warp_exports(
    lang: str, has_identity: bool = True, platform: str = ""
) -> InlineKeyboardMarkup:
    rows = _warp_export_rows(lang, platform)
    if has_identity:
        rows += _warp_identity_rows(lang)
    rows.append([_b(t(lang, "btn.warp_apps"), "wg:apps")])
    rows.append(back_row(lang, "nav:warp"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def warp_endpoints(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.warp_rescan"), "wg:rescan")],
            back_row(lang, "nav:warp"),
        ]
    )


# ------------------------------------------------------------- warp pools


def pool_menu(lang: str) -> InlineKeyboardMarkup:
    """Admin controls for the two family pools, plus the operator leaderboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.pool_refresh"), "pool:refresh", OK)],
            [
                _b(t(lang, "btn.pool_refresh_v4"), "pool:refresh:v4", GO),
                _b(t(lang, "btn.pool_refresh_v6"), "pool:refresh:v6", GO),
            ],
            [
                _b(t(lang, "btn.pool_add_v4"), "pool:add:v4", GO),
                _b(t(lang, "btn.pool_add_v6"), "pool:add:v6", GO),
            ],
            [_b(t(lang, "btn.pool_manual"), "pool:manual", GO)],
            [_b(t(lang, "btn.pool_audit"), "pool:audit", GO)],
            [_b(t(lang, "btn.pool_ops"), "pool:ops", GO)],
            [_b(t(lang, "btn.pool_list"), "pool:list", GO)],
            back_row(lang, "adm:menu"),
        ]
    )


def pool_manual(lang: str, v4: int = 0, v6: int = 0) -> InlineKeyboardMarkup:
    """The hand entered endpoints screen: add, re-check, clear."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            _b(t(lang, "btn.pool_add_v4"), "pool:add:v4", checker(0, 0)),
            _b(t(lang, "btn.pool_add_v6"), "pool:add:v6", checker(0, 1)),
        ],
        [_b(t(lang, "btn.pool_manual_check"), "pool:manual:check", checker(1, 0))],
    ]
    clear: list[InlineKeyboardButton] = []
    if v4:
        clear.append(_b(t(lang, "btn.pool_manual_clear_v4"), "pool:manual:ask:v4", BAD))
    if v6:
        clear.append(_b(t(lang, "btn.pool_manual_clear_v6"), "pool:manual:ask:v6", BAD))
    if clear:
        rows.append(clear)
    rows.append([_b(t(lang, "btn.pool"), "pool:home", SOFT)])
    rows.append(back_row(lang, "adm:menu"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pool_manual_cancel(lang: str) -> InlineKeyboardMarkup:
    """Shown while the bot is waiting for a pasted list."""
    return InlineKeyboardMarkup(inline_keyboard=[[_b(t(lang, "btn.cancel"), "pool:manual", SOFT)]])


def pool_manual_confirm(lang: str, family: str) -> InlineKeyboardMarkup:
    """Deleting a whole family's pinned list is worth one extra tap."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _b(t(lang, "btn.confirm"), f"pool:manual:wipe:{family}", BAD),
                _b(t(lang, "btn.cancel"), "pool:manual", SOFT),
            ]
        ]
    )


def pool_back(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.pool"), "pool:home", SOFT)],
            back_row(lang, "adm:menu"),
        ]
    )


# ---------------------------------------------------------------- support


def support_menu(lang: str, has_thread: bool) -> InlineKeyboardMarkup:
    """User facing support home."""
    rows: list[list[InlineKeyboardButton]] = [[_b(t(lang, "btn.support_new"), "sup:new", OK)]]
    if has_thread:
        rows.append([_b(t(lang, "btn.support_thread"), "sup:thread", GO)])
    if settings.support_url:
        rows.append([_u(t(lang, "btn.support_direct"), settings.support_url, GO)])
    rows.append(back_row(lang))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def support_user_reply(lang: str) -> InlineKeyboardMarkup:
    """Attached to an admin answer so the user can keep the thread going."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.support_new"), "sup:new", OK)],
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
    rows.append([_b(t(lang, toggle[0]), toggle[1], GO)])
    rows.append(
        [_b(t(lang, "support.toggle_on" if enabled else "support.toggle_off"), "sup:toggle", OK)]
    )
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
            [_b(t(lang, "btn.reply"), f"sup:reply:{ticket_id}", OK)],
            [_b(t(lang, action[0]), action[1], GO)],
            [_b(t(lang, "btn.tickets"), f"sup:list:{scope}", SOFT)],
            back_row(lang, "adm:menu"),
        ]
    )


# ------------------------------------------------------------------ admin


def admin_menu(lang: str) -> InlineKeyboardMarkup:
    """Same uniform ladder as every user menu: one green leader, blue rank."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_c(t(lang, "btn.stats"), "adm:stats", OK), _c(t(lang, "btn.users"), "adm:users", GO)],
            [
                _c(t(lang, "btn.broadcast"), "adm:broadcast", GO),
                _c(t(lang, "btn.channels"), "adm:channels", GO),
            ],
            [_c(t(lang, "btn.engine"), "adm:engine", GO), _c(t(lang, "btn.options"), "adm:options", GO)],
            [_c(t(lang, "btn.pool"), "pool:home", GO)],
            [_c(t(lang, "btn.panels"), "adm:panels", GO), _c(t(lang, "btn.logs"), "adm:logs", GO)],
            [_c(t(lang, "btn.tickets"), "sup:list:open", GO), _c(t(lang, "btn.backup"), "adm:backup", GO)],
            back_row(lang),
        ]
    )


def admin_channels(lang: str, channels: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for channel in channels:
        title = channel.get("title") or channel["chat_id"]
        rows.append([_b(f"\U0001f5d1 {title}", f"adm:chdel:{channel['chat_id']}", BAD)])
    rows.append([_b(t(lang, "btn.add"), "adm:chadd", OK)])
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
    """One scanner to rule both engines.

    The clean-IP sweep and the WARP endpoint sweep used to have two buttons, two
    screens and two vocabularies. They are one button now: ``adm:smart`` fires
    both engines at once, the automatic cadence (300 s) does it between taps,
    and the survivors land in the pools the panels are built from.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [glass_button(t(lang, "btn.smart_scan"), "adm:smart", OK)],
            [
                _b(t(lang, "btn.sync_now"), "adm:sync", GO),
                _b(t(lang, "btn.curate"), "adm:curate", GO),
            ],
            [_b(t(lang, "btn.pool"), "pool:home", SOFT)],
            back_row(lang, "adm:menu"),
        ]
    )


def admin_user(lang: str, tg_id: int, banned: bool) -> InlineKeyboardMarkup:
    action = ("btn.unban", f"adm:unban:{tg_id}") if banned else ("btn.ban", f"adm:ban:{tg_id}")
    # The moderation verb keeps its semantic colour: unban green, ban red.
    style = OK if banned else BAD
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, action[0]), action[1], style)],
            [_b(t(lang, "btn.users"), "adm:users", GO)],
            back_row(lang, "adm:menu"),
        ]
    )
