"""Extras: WARP / WireGuard generation and link conversion."""

from __future__ import annotations

import base64
import json
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from .. import keyboards, vless, warp
from ..config import settings
from ..i18n import num, t
from ..utils import edit, esc

log = logging.getLogger("autovless.extras")
router = Router(name="extras")


class ConvertFlow(StatesGroup):
    link = State()


@router.callback_query(F.data == "nav:warp")
async def on_warp(call: CallbackQuery, lang: str) -> None:
    await call.answer()
    notice = await call.message.answer(t(lang, "warp_building"))

    try:
        identity = await warp.provision()
    except warp.WarpError as error:
        log.warning("warp provisioning failed: %s", error)
        await notice.edit_text(t(lang, "warp_failed"))
        return

    conf = warp.wireguard_conf(identity)
    await notice.edit_text(
        t(
            lang,
            "warp_ready",
            account=esc(identity["account_type"]),
            endpoint=esc(identity["endpoint"]),
        )
    )
    await call.message.answer_document(
        BufferedInputFile(conf.encode("utf-8"), filename=f"{settings.brand}-warp.conf"),
    )
    await call.message.answer(
        f"<code>{esc(warp.warp_link(identity, f'{settings.brand}-WARP'))}</code>",
        reply_markup=keyboards.simple_back(lang),
    )


@router.callback_query(F.data == "nav:convert")
async def on_convert(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.set_state(ConvertFlow.link)
    await edit(call, t(lang, "convert_prompt"), keyboards.simple_back(lang))
    await call.answer()


@router.message(ConvertFlow.link, F.text)
async def on_convert_input(message: Message, state: FSMContext, lang: str) -> None:
    candidates = [
        line.strip()
        for line in (message.text or "").replace(",", "\n").splitlines()
        if line.strip().lower().startswith("vless://")
    ]

    parsed: list[dict] = []
    for link in candidates:
        try:
            parsed.append(vless.parse_vless(link))
        except ValueError:
            continue

    if not parsed:
        await message.answer(t(lang, "convert_bad"))
        return

    await state.clear()

    blob = base64.b64encode("\n".join(candidates).encode("utf-8")).decode("ascii")
    await message.answer_document(
        BufferedInputFile(clash_yaml(parsed).encode("utf-8"), filename="converted-clash.yaml")
    )
    await message.answer_document(
        BufferedInputFile(singbox_json(parsed).encode("utf-8"), filename="converted-singbox.json")
    )
    await message.answer_document(
        BufferedInputFile(blob.encode("ascii"), filename="converted-sub.txt"),
        caption=t(lang, "convert_done", count=num(len(parsed), lang)),
        reply_markup=keyboards.simple_back(lang),
    )


def clash_yaml(items: list[dict]) -> str:
    proxies: list[str] = []
    names: list[str] = []

    for index, item in enumerate(items, start=1):
        secure = item["security"] == "tls"
        name = f"{item['name']} #{index}".replace('"', "'")
        names.append(f'      - "{name}"')
        lines = [
            f'  - name: "{name}"',
            "    type: vless",
            f"    server: {item['ip']}",
            f"    port: {item['port']}",
            f"    uuid: {item['uuid']}",
            "    udp: true",
            f"    tls: {'true' if secure else 'false'}",
        ]
        if secure:
            lines += [f"    servername: {item['host']}", "    client-fingerprint: chrome"]
        lines += [
            "    network: ws",
            "    ws-opts:",
            f'      path: "{item["path"]}"',
            "      headers:",
            f"        Host: {item['host']}",
        ]
        proxies.append("\n".join(lines))

    return "\n".join(
        [
            f"# converted by {settings.brand}",
            "mixed-port: 7890",
            "mode: rule",
            "proxies:",
            "\n".join(proxies),
            "proxy-groups:",
            f'  - name: "{settings.brand}"',
            "    type: url-test",
            "    url: http://cp.cloudflare.com/generate_204",
            "    interval: 300",
            "    proxies:",
            "\n".join(names),
            "rules:",
            f"  - MATCH,{settings.brand}",
            "",
        ]
    )


def singbox_json(items: list[dict]) -> str:
    outbounds = []
    for index, item in enumerate(items, start=1):
        entry: dict = {
            "type": "vless",
            "tag": f"{item['name']} #{index}",
            "server": item["ip"],
            "server_port": int(item["port"]),
            "uuid": item["uuid"],
            "packet_encoding": "xudp",
            "transport": {
                "type": "ws",
                "path": item["path"],
                "headers": {"Host": item["host"]},
                "early_data_header_name": "Sec-WebSocket-Protocol",
            },
        }
        if item["security"] == "tls":
            entry["tls"] = {
                "enabled": True,
                "server_name": item["host"],
                "utls": {"enabled": True, "fingerprint": "chrome"},
            }
        outbounds.append(entry)
    return json.dumps({"outbounds": outbounds}, indent=2, ensure_ascii=False)
