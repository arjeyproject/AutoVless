"""The selectable protocol menu: one tap per protocol, or everything at once.

Until now the protocols lived on separate buttons scattered across two screens
(single configs, trojan, fragment, clash, sing-box on the panel; the free
versions behind the free menu), and a user who wanted "just XHTTP" or "give me
all of them" had to know where each one hid. This screen is the missing index:
every protocol the panel speaks gets a button, a QR code of its first link, and
a one-tap ZIP that bundles the lot.

Each protocol button renders from the panel the user already owns - same uuid,
same host, same endpoints - so nothing here needs a rebuild or a re-upload to
work. Shadowsocks only shows when the SS engine is on, exactly like the
AmneziaWG rows hide on clients that cannot read them.
"""

from __future__ import annotations

import io
import logging
import zipfile

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from .. import db, fragment, keyboards, profiles, qrimg, shadowsocks, trojan, vless
from .. import warp as warpcore
from ..config import settings
from ..i18n import num, t
from ..utils import chunked, edit, esc

log = logging.getLogger("autovless.handlers.protocols")
router = Router(name="protocols")

# Plain-latin protocol names. They ride inside QR captions and file names where
# a translated label would be unreadable, so they stay untranslated on purpose.
NAMES: dict[str, str] = {
    "vless": "VLESS / WS",
    "httpupgrade": "HTTPUpgrade",
    "xhttp": "XHTTP",
    "trojan": "Trojan",
    "ss": "Shadowsocks",
    "sub": "Subscription",
    "warp": "WARP / WireGuard",
    "clash": "Clash",
    "singbox": "sing-box",
    "fragment": "Fragment Xray",
}

NOTE_KEY: dict[str, str] = {
    "vless": "proto.vless_note",
    "httpupgrade": "proto.up_note",
    "xhttp": "proto.xhttp_note",
    "trojan": None,  # keeps the original rich trojan screen wording
    "ss": "proto.ss_note",
}

FILE_KINDS = {"clash", "singbox", "fragment"}


def _links_for(kind: str, panel: dict) -> list[str]:
    """Links of one protocol, built from the panel the user already owns."""
    uuid, host = str(panel["uuid"]), str(panel["host"])
    endpoints = panel["endpoints"] or []
    brand = settings.brand
    if kind == "vless":
        return vless.build_links(uuid, host, endpoints, brand, "ws")
    if kind == "httpupgrade":
        if not settings.httpupgrade:
            return []
        return vless.build_links(uuid, host, endpoints, brand, "httpupgrade")
    if kind == "xhttp":
        if not settings.xhttp:
            return []
        return vless.build_links(uuid, host, endpoints, brand, "xhttp")
    if kind == "trojan":
        return trojan.build_links(uuid, host, endpoints, brand)
    if kind == "ss":
        return shadowsocks.build_links(uuid, host, endpoints, brand)
    return []


def _has_ss() -> bool:
    return shadowsocks.enabled()


async def _panel_of(call: CallbackQuery) -> dict | None:
    return await db.get_panel(call.from_user.id)


def _menu_body(lang: str, panel: dict) -> str:
    return t(
        lang,
        "proto.menu",
        rule=t(lang, "rule"),
        host=esc(panel["host"]),
        count=num(len(panel["endpoints"] or []), lang),
    )


async def show_menu(event: CallbackQuery, lang: str) -> None:
    panel = await _panel_of(event)
    if panel is None:
        await edit(event, t(lang, "proto.menu_free"), keyboards.free_hint_menu(lang))
        await event.answer()
        return
    back = "nav:panel" if panel else "nav:menu"
    await edit(event, _menu_body(lang, panel), keyboards.protocols_menu(lang, _has_ss(), back))
    await event.answer()


@router.callback_query(F.data == "nav:protocols")
async def on_protocols(call: CallbackQuery, lang: str) -> None:
    await show_menu(call, lang)


# ------------------------------------------------------------ one protocol


async def _deliver_links(call: CallbackQuery, lang: str, kind: str) -> None:
    panel = await _panel_of(call)
    if panel is None:
        await edit(call, t(lang, "proto.menu_free"), keyboards.free_hint_menu(lang))
        await call.answer()
        return

    links = _links_for(kind, panel)
    if not links:
        await edit(call, t(lang, "proto.no_tls"), keyboards.protocols_menu(lang, _has_ss()))
        await call.answer()
        return

    await call.answer()
    note_key = NOTE_KEY[kind]
    if note_key:
        body = (
            t(lang, note_key, count=num(len(links), lang), links="")
            + "\n\n"
            + "\n\n".join(f"<code>{esc(link)}</code>" for link in links)
        )
    else:
        # Trojan keeps its original screen: count, subscription and password.
        sub = _sub_links(panel)["trojan"]
        body = t(
            lang,
            "trojan_configs",
            count=num(len(links), lang),
            sub=esc(sub),
            password=esc(trojan.password_for(panel["uuid"])),
        )
        body += "\n\n" + "\n\n".join(
            f"<b>#{num(index, lang)}</b>\n<code>{esc(link)}</code>"
            for index, link in enumerate(links, start=1)
        )

    parts = chunked(body)
    # The QR leads: scan it, or read the links under it - same config either way.
    await call.message.answer_photo(
        qrimg.file_photo(links[0]),
        caption=t(lang, "proto.qr_caption", name=NAMES[kind]),
    )
    for index, part in enumerate(parts):
        await call.message.answer(
            part,
            reply_markup=keyboards.protocols_menu(lang, _has_ss())
            if index == len(parts) - 1
            else None,
            disable_web_page_preview=True,
        )
    await db.log_event("proto", call.from_user.id, f"{kind}={len(links)}")


def _sub_links(panel: dict) -> dict[str, str]:
    """Direct subscription URLs, one lookup, no gateway mixing here."""
    uuid, host = str(panel["uuid"]), str(panel["host"])
    return {
        "sub": vless.sub_url(uuid, host),
        "mix": vless.sub_url(uuid, host, "mix"),
        "trojan": trojan.sub_url(uuid, host),
        "clash": vless.sub_url(uuid, host, "clash"),
        "singbox": vless.sub_url(uuid, host, "singbox"),
    }


@router.callback_query(F.data.in_({"proto:vless", "proto:httpupgrade", "proto:xhttp", "proto:trojan", "proto:ss"}))
async def on_protocol(call: CallbackQuery, lang: str) -> None:
    await _deliver_links(call, lang, (call.data or "").split(":", 1)[1])


# ------------------------------------------------------------------ files


async def _deliver_file(call: CallbackQuery, lang: str, kind: str) -> None:
    panel = await _panel_of(call)
    if panel is None:
        await edit(call, t(lang, "proto.menu_free"), keyboards.free_hint_menu(lang))
        await call.answer()
        return
    uuid, host, endpoints = panel["uuid"], panel["host"], panel["endpoints"] or []

    await call.answer()
    if kind == "clash":
        payload, name = profiles.clash(uuid, host, endpoints), profiles.filename("clash")
        caption = None
    elif kind == "singbox":
        payload, name = profiles.singbox(uuid, host, endpoints), profiles.filename("singbox")
        caption = None
    else:
        payload = fragment.xray_config(uuid, host, endpoints)
        name = fragment.filename()
        caption = t(
            lang,
            "fragment_ready",
            count=num(len(fragment.outbounds(uuid, host, endpoints)), lang),
            length=fragment.TLS_FRAGMENT["length"],
            interval=fragment.TLS_FRAGMENT["interval"],
        )

    await call.message.answer_document(
        BufferedInputFile(payload.encode("utf-8"), filename=name),
        caption=caption,
        reply_markup=keyboards.protocols_menu(lang, _has_ss()),
    )
    await db.log_event("proto", call.from_user.id, kind)


@router.callback_query(F.data.in_({"proto:clash", "proto:singbox", "proto:fragment"}))
async def on_file_protocol(call: CallbackQuery, lang: str) -> None:
    await _deliver_file(call, lang, (call.data or "").split(":", 1)[1])


# --------------------------------------------------------------------- QR


@router.callback_query(F.data == "proto:qr")
async def on_qr_menu(call: CallbackQuery, lang: str) -> None:
    panel = await _panel_of(call)
    if panel is None:
        await edit(call, t(lang, "proto.menu_free"), keyboards.free_hint_menu(lang))
        await call.answer()
        return
    await edit(call, t(lang, "proto.qr_screen"), keyboards.protocols_qr(lang, _has_ss()))
    await call.answer()


@router.callback_query(F.data.startswith("proto:qr:"))
async def on_qr_protocol(call: CallbackQuery, lang: str) -> None:
    panel = await _panel_of(call)
    if panel is None:
        await edit(call, t(lang, "proto.menu_free"), keyboards.free_hint_menu(lang))
        await call.answer()
        return
    kind = (call.data or "").split(":")[-1]

    if kind == "sub":
        url = _sub_links(panel)["sub"]
    else:
        links = _links_for(kind, panel)
        if not links:
            await call.answer(t(lang, "proto.qr_empty"), show_alert=True)
            return
        url = links[0]

    await call.message.answer_photo(
        qrimg.file_photo(url),
        caption=t(lang, "proto.qr_caption", name=NAMES.get(kind, NAMES["sub"])),
        reply_markup=keyboards.simple_back(lang, "nav:protocols"),
    )
    await call.answer()


# --------------------------------------------------------------- everything


def _zip_entry(kind: str, links: list[str]) -> tuple[str, str] | None:
    if not links:
        return None
    return (f"links-{kind}.txt", "\n".join(links))


@router.callback_query(F.data == "proto:all")
async def on_all(call: CallbackQuery, lang: str) -> None:
    """Every protocol, one tap: links per protocol, files, and the ZIP of it all."""
    panel = await _panel_of(call)
    if panel is None:
        await edit(call, t(lang, "proto.menu_free"), keyboards.free_hint_menu(lang))
        await call.answer()
        return

    uuid, host, endpoints = panel["uuid"], panel["host"], panel["endpoints"] or []
    groups: dict[str, list[str]] = {}
    for kind in ("vless", "httpupgrade", "xhttp", "trojan", "ss"):
        links = _links_for(kind, panel)
        if links:
            groups[kind] = links

    if not groups:
        await edit(call, t(lang, "proto.no_tls"), keyboards.protocols_menu(lang, _has_ss()))
        await call.answer()
        return

    await call.answer()
    names = [t(lang, f"btn.proto_{key}") for key in groups]

    # Per protocol: QR first, then the links. Same shape as the single-protocol
    # buttons, so a user who came from either screen recognises the layout.
    for kind, links in groups.items():
        await call.message.answer_photo(
            qrimg.file_photo(links[0]),
            caption=t(lang, "proto.qr_caption", name=NAMES[kind]),
        )
        note_key = NOTE_KEY[kind]
        body = (
            t(lang, note_key, count=num(len(links), lang), links="")
            + "\n\n".join(f"<code>{esc(link)}</code>" for link in links)
            if note_key
            else t(
                lang,
                "trojan_configs",
                count=num(len(links), lang),
                sub=esc(_sub_links(panel)["trojan"]),
                password=esc(trojan.password_for(panel["uuid"])),
            )
            + "\n\n"
            + "\n\n".join(
                f"<b>#{num(index, lang)}</b>\n<code>{esc(link)}</code>"
                for index, link in enumerate(links, start=1)
            )
        )
        for index, part in enumerate(chunked(body)):
            await call.message.answer(part, disable_web_page_preview=True)

    # The client files, each sent on its own as well as inside the zip.
    files: list[tuple[str, str]] = [
        ("clash.yaml", profiles.clash(uuid, host, endpoints)),
        ("singbox.json", profiles.singbox(uuid, host, endpoints)),
        (fragment.filename(), fragment.xray_config(uuid, host, endpoints)),
    ]
    for name, payload in files:
        await call.message.answer_document(BufferedInputFile(payload.encode("utf-8"), filename=name))

    # The WARP links, when the user already holds an identity.
    warp_links: list[str] = []
    record = await db.get_warp_user(call.from_user.id)
    if record is not None:
        try:
            warp_links = warpcore.links(record["identity"], record.get("endpoints") or [])
            warp_links.append(
                warpcore.hiddify_link(
                    record["identity"],
                    record.get("endpoints") or [],
                    name=f"{settings.brand}-WARP-Hiddify",
                )
            )
        except Exception:  # noqa: BLE001
            log.debug("could not build warp links for the bundle", exc_info=True)

    zip_files: list[tuple[str, str]] = []
    for kind, links in groups.items():
        entry = _zip_entry(kind, links)
        if entry:
            zip_files.append(entry)
    zip_files += files
    if warp_links:
        zip_files.append(("links-warp.txt", "\n".join(warp_links)))
    subs = _sub_links(panel)
    zip_files.append(
        (
            "subscriptions.txt",
            "\n".join(f"{key}: {url}" for key, url in subs.items()),
        )
    )

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in zip_files:
            archive.writestr(name, payload)
    stamp = panel.get("updated_at") or 0
    zip_name = f"{settings.brand.lower()}-all-configs-{stamp}.zip"

    summary = t(
        lang,
        "proto.all_summary",
        rule=t(lang, "rule"),
        lines="\n".join(
            t(lang, "proto.all_line", name=name, count=num(len(groups[key]), lang))
            for key, name in zip(groups, names)
        ),
    )
    await call.message.answer_document(
        BufferedInputFile(stream.getvalue(), filename=zip_name),
        caption=t(lang, "proto.zip_caption", count=num(len(zip_files), lang)),
        reply_markup=keyboards.protocols_menu(lang, _has_ss()),
    )
    await call.message.answer(summary, reply_markup=keyboards.simple_back(lang, "nav:protocols"))
    await db.log_event("proto_all", call.from_user.id, f"kinds={len(groups)} files={len(zip_files)}")
