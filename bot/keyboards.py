"""Inline keyboards. Every screen is reachable and every screen has a way back."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import apps as catalogue
from .config import settings
from .i18n import t
from .operators import OPERATORS
from .platforms import ORDER as PLATFORM_ORDER
from .platforms import label_key, normalise_platform, should_include_amnezia_keys

CF_SIGNUP_URL = "https://dash.cloudflare.com/sign-up"
CF_TOKEN_URL = (
    "https://dash.cloudflare.com/profile/api-tokens"
    "?permissionGroupKeys=%5B%7B%22key%22%3A%22workers_scripts%22%2C%22type%22%3A%22edit%22%7D%2C"
    "%7B%22key%22%3A%22account_settings%22%2C%22type%22%3A%22read%22%7D%2C"
    "%7B%22key%22%3A%22zone%22%2C%22type%22%3A%22read%22%7D%2C"
    "%7B%22key%22%3A%22dns%22%2C%22type%22%3A%22edit%22%7D%5D"
    "&accountId=*&zoneId=all&name=AutoVless"
)

AMNEZIA_PLAY_URL = "https://play.google.com/store/apps/details?id=org.amnezia.vpn"
AMNEZIA_WIN_URL = "https://github.com/amnezia-vpn/amnezia-client/releases/latest"
# The official WireGuard app. This is the one an iPhone config is built for, and
# sending an iPhone user to Google Play was its own small bug.
WIREGUARD_IOS_URL = "https://apps.apple.com/app/wireguard/id1441195209"
STREISAND_IOS_URL = "https://apps.apple.com/app/streisand/id6450534064"

BULLET = "\u2022"
TICKET_MARKS = {"open": "\U0001f7e0", "answered": "\u2705", "closed": "\U0001f512"}


def _b(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _u(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


def glass_button(text: str, callback: str) -> InlineKeyboardButton:
    """A full-width button. Telegram gives us one row per button and that is the
    only "glass" affordance the API has, so a glass button is simply a button
    that owns its row."""
    return _b(text, callback)


# ---------------------------------------------------------------- devices


def device_picker(lang: str, flow: str = "", back: str = "nav:warp") -> InlineKeyboardMarkup:
    """Which phone is this for. The first step of every WARP flow.

    ``flow`` is carried through in the callback data so the answer survives
    without any FSM state: empty means "go on to build a config", and
    ``f:<kind>`` means "render that export for the platform I just picked".
    Depending on state here is what used to make the picker a dead end - a
    navigation in between cleared it and the next tap did nothing at all.
    """
    tail = f":{flow}" if flow else ""
    rows = [
        [glass_button(t(lang, label_key(name)), f"wg:dev:{name}{tail}")]
        for name in PLATFORM_ORDER
    ]
    rows.append(back_row(lang, back))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def platform_picker(lang: str, flow: str = "") -> InlineKeyboardMarkup:
    """Older name for ``device_picker``, kept so nothing breaks mid-deploy."""
    return device_picker(lang, flow)


def _client_link(lang: str, platform: str) -> InlineKeyboardButton:
    """The store link that matches the file we just handed over."""
    name = normalise_platform(platform)
    if name in {"ios", "macos"}:
        return _u(t(lang, "btn.wireguard_ios"), WIREGUARD_IOS_URL)
    if name == "windows":
        return _u(t(lang, "btn.amnezia"), AMNEZIA_WIN_URL)
    return _u(t(lang, "btn.amnezia"), AMNEZIA_PLAY_URL)


def ticket_mark(status: object) -> str:
    return TICKET_MARKS.get(str(status), BULLET)


def back_row(lang: str, target: str = "nav:menu") -> list[InlineKeyboardButton]:
    return [_b(t(lang, "btn.back"), target)]


def main_menu(lang: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [_b(t(lang, "btn.build"), "nav:build")],
        [_b(t(lang, "btn.panel"), "nav:panel")],
        [_b(t(lang, "btn.warp"), "nav:warp")],
        [_b(t(lang, "btn.apps"), "nav:apps")],
        [_b(t(lang, "btn.guide"), "nav:guide"), _b(t(lang, "btn.convert"), "nav:convert")],
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
            [_u(t(lang, "btn.cf_signup"), CF_SIGNUP_URL)],
            [_u(t(lang, "btn.cf_token"), CF_TOKEN_URL)],
            back_row(lang),
        ]
    )


def panel_menu(lang: str) -> InlineKeyboardMarkup:
    """The turbo panel.

    Fragment owns a full row of its own because it is the one button that fixes
    the most common complaint on Iranian mobile networks: the config connects on
    wifi and dies on the handshake behind DPI. Trojan sits next to the single
    configs, since both are "give me links I can paste somewhere else".

    The screen used to be eleven stacked rows and read like a settings page. It is
    now paired down the middle: fewer taps to reach anything, and considerably
    less to look at.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.qr"), "panel:qr"), _b(t(lang, "btn.sub"), "panel:sub")],
            [_b(t(lang, "btn.fragment"), "panel:fragment")],
            [_b(t(lang, "btn.trojan"), "panel:trojan"), _b(t(lang, "btn.single"), "panel:single")],
            [_b(t(lang, "btn.clash"), "panel:clash"), _b(t(lang, "btn.singbox"), "panel:singbox")],
            [_b(t(lang, "btn.ping"), "panel:ping"), _b(t(lang, "btn.ai"), "panel:ai")],
            [_b(t(lang, "btn.apply"), "panel:apply"), _b(t(lang, "btn.rescan"), "panel:rescan")],
            [_b(t(lang, "btn.rebuild"), "panel:rebuild"), _b(t(lang, "btn.apps"), "nav:apps")],
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
                _b(t(lang, "btn.apps_android"), "apps:android"),
                _b(t(lang, "btn.apps_ios"), "apps:ios"),
            ],
            [
                _b(t(lang, "btn.apps_windows"), "apps:windows"),
                _b(t(lang, "btn.apps_macos"), "apps:macos"),
            ],
            [_b(t(lang, "btn.apps_linux"), "apps:linux")],
            [_b(t(lang, "btn.guide"), "nav:guide")],
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
        _b(t(lang, f"btn.apps_{code}"), f"apps:{code}:{tag}" if tag else f"apps:{code}")
        for code in others
    ]
    for index in range(0, len(switch), 2):
        rows.append(switch[index : index + 2])

    rows.append([_b(t(lang, "btn.guide"), "nav:guide")])
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
        [_b(t(lang, "btn.warp_link"), "wg:link"), _b(t(lang, "btn.warp_plain"), target("plain"))]
    )
    rows.append(
        [
            _b(t(lang, "btn.warp_singbox"), target("singbox")),
            _b(t(lang, "btn.warp_clash"), target("clash")),
        ]
    )
    return rows


def _warp_identity_rows(lang: str) -> list[list[InlineKeyboardButton]]:
    """The actions that only mean anything once a user owns a WARP identity."""
    return [
        [_b(t(lang, "btn.warp_rebuild"), "wg:rebuild")],
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
        [glass_button(t(lang, "btn.warp_build"), "wg:net")],
        back_row(lang),
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def warp_network(lang: str, platform: str = "") -> InlineKeyboardMarkup:
    """The two operator buttons: Irancell takes IPv6, everyone else takes IPv4.

    The device picked a moment ago rides along in the callback data so the config
    is rendered for the right client without any state to lose.
    """
    tail = f":{normalise_platform(platform)}" if platform else ""
    rows = [
        [glass_button(t(lang, "btn.wg_irancell"), f"wg:net:mtn{tail}")],
        [glass_button(t(lang, "btn.wg_other"), f"wg:net:other{tail}")],
    ]
    if platform:
        rows.append([_b(t(lang, "btn.wg_change_device"), "wg:net")])
    rows.append(back_row(lang, "nav:warp"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def warp_delivered(lang: str, family: str, platform: str = "") -> InlineKeyboardMarkup:
    """Attached under a delivered config: next endpoint, the client, the exports."""
    name = normalise_platform(platform) if platform else ""
    tail = f":{name}" if name else ""
    rows: list[list[InlineKeyboardButton]] = [
        [_b(t(lang, "btn.wg_next_ep"), f"wg:net:next:{family}{tail}")],
        [_client_link(lang, name or "android")],
    ]
    if name in {"ios", "macos"}:
        # Clean WireGuard has no obfuscation, so the one client that can carry an
        # obfuscated WARP link on iOS is worth a button of its own.
        rows.append([_u(t(lang, "btn.streisand_ios"), STREISAND_IOS_URL)])
    rows += _warp_export_rows(lang, name)
    rows += _warp_identity_rows(lang)
    rows.append([_b(t(lang, "btn.wg_change_device"), "wg:net")])
    rows.append([_b(t(lang, "btn.wg_pick_again"), f"wg:dev:{name or 'android'}")])
    rows.append(back_row(lang, "nav:warp"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    """Admin controls for the two family pools."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.pool_refresh"), "pool:refresh")],
            [
                _b(t(lang, "btn.pool_refresh_v4"), "pool:refresh:v4"),
                _b(t(lang, "btn.pool_refresh_v6"), "pool:refresh:v6"),
            ],
            [
                _b(t(lang, "btn.pool_add_v4"), "pool:add:v4"),
                _b(t(lang, "btn.pool_add_v6"), "pool:add:v6"),
            ],
            [_b(t(lang, "btn.pool_manual"), "pool:manual")],
            [_b(t(lang, "btn.pool_audit"), "pool:audit")],
            [_b(t(lang, "btn.pool_list"), "pool:list")],
            back_row(lang, "adm:menu"),
        ]
    )


def pool_manual(lang: str, v4: int = 0, v6: int = 0) -> InlineKeyboardMarkup:
    """The hand entered endpoints screen: add, re-check, clear."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            _b(t(lang, "btn.pool_add_v4"), "pool:add:v4"),
            _b(t(lang, "btn.pool_add_v6"), "pool:add:v6"),
        ],
        [_b(t(lang, "btn.pool_manual_check"), "pool:manual:check")],
    ]
    clear: list[InlineKeyboardButton] = []
    if v4:
        clear.append(_b(t(lang, "btn.pool_manual_clear_v4"), "pool:manual:ask:v4"))
    if v6:
        clear.append(_b(t(lang, "btn.pool_manual_clear_v6"), "pool:manual:ask:v6"))
    if clear:
        rows.append(clear)
    rows.append([_b(t(lang, "btn.pool"), "pool:home")])
    rows.append(back_row(lang, "adm:menu"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pool_manual_cancel(lang: str) -> InlineKeyboardMarkup:
    """Shown while the bot is waiting for a pasted list."""
    return InlineKeyboardMarkup(inline_keyboard=[[_b(t(lang, "btn.cancel"), "pool:manual")]])


def pool_manual_confirm(lang: str, family: str) -> InlineKeyboardMarkup:
    """Deleting a whole family's pinned list is worth one extra tap."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _b(t(lang, "btn.confirm"), f"pool:manual:wipe:{family}"),
                _b(t(lang, "btn.cancel"), "pool:manual"),
            ]
        ]
    )


def pool_back(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.pool"), "pool:home")],
            back_row(lang, "adm:menu"),
        ]
    )


# ---------------------------------------------------------------- support


def support_menu(lang: str, has_thread: bool) -> InlineKeyboardMarkup:
    """User facing support home."""
    rows: list[list[InlineKeyboardButton]] = [[_b(t(lang, "btn.support_new"), "sup:new")]]
    if has_thread:
        rows.append([_b(t(lang, "btn.support_thread"), "sup:thread")])
    if settings.support_url:
        rows.append([_u(t(lang, "btn.support_direct"), settings.support_url)])
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
    rows.append(
        [_b(t(lang, "support.toggle_on" if enabled else "support.toggle_off"), "sup:toggle")]
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
            [
                _b(t(lang, "btn.broadcast"), "adm:broadcast"),
                _b(t(lang, "btn.channels"), "adm:channels"),
            ],
            [_b(t(lang, "btn.engine"), "adm:engine"), _b(t(lang, "btn.options"), "adm:options")],
            [_b(t(lang, "btn.pool"), "pool:home")],
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
    """The scan controls, plus the WARP endpoint screens the user side no longer
    shows. They were taken off the user's WARP home on purpose, but an admin still
    needs to be able to look at the pool and force a sweep."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.scan_now"), "adm:scan")],
            [_b(t(lang, "btn.sync_now"), "adm:sync")],
            [_b(t(lang, "btn.warp_rescan"), "wg:rescan"), _b(t(lang, "btn.warp_eps"), "wg:eps")],
            [_b(t(lang, "btn.pool"), "pool:home")],
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
