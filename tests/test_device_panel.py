"""Dependency-isolated regression tests, not device or live-network tests.

Run: python -m unittest discover -s tests -v
Loads actual function bodies via AST without importing the application's startup
side effects. Telegram, storage, scanning and Cloudflare are test doubles. These
checks do NOT establish full aiogram integration, iOS import or carrier access.
"""
from __future__ import annotations
import ast
import asyncio
import configparser
import copy
import logging
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]


def functions(path, names, env):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    body = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
    found = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            node.decorator_list = []
            body.append(node)
            found.add(node.name)
    if found != set(names):
        raise AssertionError(f"Missing functions in {path}: {set(names) - found}")
    exec(compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])), path, "exec"), env)
    return env


class Button(N):
    def __init__(self, **kw):
        super().__init__(**{"text": "", "url": None, "callback_data": None, **kw})


class File:
    def __init__(self, data, filename):
        self.data, self.filename = data, filename


class CFError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


IDENTITY = {"private_key": "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE=",
            "peer_public_key": "AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI=",
            "v4": "172.16.0.2", "v6": "2606:4700:110::2"}
ROWS = [{"ip": "162.159.192.1", "port": 2408},
        {"ip": "162.159.192.1", "port": 500},
        {"ip": "188.114.96.1", "port": 2408}]
V6ROW = [{"ip": "2606:4700:d0::a29f:c001", "port": 2408}]


def call(data="wg:net:mtn:ios"):
    return N(data=data, from_user=N(id=7), answer=AsyncMock(),
             message=N(answer=AsyncMock(), answer_document=AsyncMock()))


def pool_env():
    settings = N(warp_per_config=6, warp_mtu=1000, warp_dns="1.1.1.1")
    core = N(provision=AsyncMock(return_value=dict(IDENTITY)), WarpError=CFError,
             obfuscation=lambda _: {"jc": 4, "jmin": 80, "jmax": 400, "i1": "test"})
    ep = N(**functions("bot/warpep.py", ["host_port", "family_of"], {"V4": "v4", "V6": "v6"}))
    conf = N(**functions("bot/warpconf.py", ["addresses", "endpoint_of", "family_of", "label", "wireguard_conf", "amnezia_conf"],
                        {"settings": settings, "warpcore": core, "warpep": ep}))
    kb = N(AMNEZIA_PLAY_URL="https://play.google.com/store/apps/details?id=org.amnezia.vpn",
           back_row=lambda lang, target: [Button(callback_data=target)],
           warp_network=lambda lang: N(inline_keyboard=[
               [Button(callback_data="wg:net:mtn")], [Button(callback_data="wg:net:other")],
               [Button(callback_data="nav:warp")]]),
           warp_exports=lambda lang: None)
    kb.warp_delivered = lambda lang, family: N(inline_keyboard=[
        [Button(callback_data=f"wg:net:next:{family}")], [Button(url=kb.AMNEZIA_PLAY_URL)]])
    env = {"PLATFORMS": ("android", "ios"), "V4": "v4", "V6": "v6", "_building": set(),
           "CHOICES": {"mtn": {"family": "v6", "operator": "mtn"}, "other": {"family": "v4", "operator": "other"}},
           "WIREGUARD_IOS": "https://apps.apple.com/app/wireguard/id1441195209",
           "InlineKeyboardButton": Button, "InlineKeyboardMarkup": N,
           "BufferedInputFile": File, "TelegramBadRequest": CFError,
           "keyboards": kb, "settings": settings, "warpcore": core, "warpconf": conf,
           "db": N(get_flag=AsyncMock(return_value=True), get_warp_user=AsyncMock(return_value=None),
                   save_warp_user=AsyncMock(), log_event=AsyncMock()),
           "warp_pool": N(pick=AsyncMock(return_value=copy.deepcopy(V6ROW))),
           "warpstore": N(counts=AsyncMock(return_value={"healthy": 1})), "TUNE": N(pool_target=40),
           "t": lambda lang, key, **kw: key, "num": lambda n, lang: str(n), "esc": str,
           "ping_label": lambda v, lang: str(v), "_out_of": lambda v, lang: str(v),
           "_family_label": lambda v, lang: v, "_app_link": lambda p: p,
           "operators": N(label=lambda op, lang: op), "log": logging.getLogger("tests"), "edit": AsyncMock()}
    return functions("bot/handlers/pool.py", ["_next_endpoints", "_device_menu", "_network_menu", "_delivered_menu",
                     "on_pick_network", "on_device_chosen", "on_network_chosen", "_deliver"], env)


class DeviceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.e = pool_env()

    def test_rotation_uses_ip_and_port_and_wraps(self):
        f = self.e["_next_endpoints"]
        for i in range(3):
            self.assertEqual(f(ROWS, [ROWS[i]])[0], ROWS[(i + 1) % 3])
        self.assertEqual(f(ROWS, []), ROWS)
        self.assertEqual(f([], ROWS), [])
        self.assertEqual(f(ROWS, V6ROW), ROWS)

    def test_menus_keep_platform_and_offer_both_devices(self):
        for lang in ("en", "fa"):
            menu = self.e["_device_menu"](lang)
            self.assertEqual([b.callback_data for b in menu.inline_keyboard[0]],
                             ["wg:device:android", "wg:device:ios"])
            for platform in ("android", "ios"):
                menu = self.e["_network_menu"](lang, platform)
                self.assertEqual(menu.inline_keyboard[0][0].callback_data, f"wg:net:mtn:{platform}")
                delivered = self.e["_delivered_menu"](lang, "v6", platform)
                self.assertEqual(delivered.inline_keyboard[0][0].callback_data, f"wg:net:next:v6:{platform}")
                if platform == "ios":
                    self.assertIn("apps.apple.com", delivered.inline_keyboard[2][0].url)
                for row in delivered.inline_keyboard:
                    for b in row:
                        if b.callback_data:
                            self.assertLessEqual(len(b.callback_data.encode()), 64)

    async def test_old_and_invalid_callbacks_return_to_picker(self):
        picker = self.e["on_pick_network"] = AsyncMock()
        self.e["_deliver"] = AsyncMock()
        for data in ("wg:net:mtn", "wg:net:next:v6", "wg:net:nope:ios", "wg:net:mtn:bad", "wg:net:next:bad:ios"):
            await self.e["on_network_chosen"](call(data), "fa")
        self.assertEqual(picker.await_count, 5)
        self.e["_deliver"].assert_not_awaited()

    async def test_device_to_operator_screen(self):
        await self.e["on_device_chosen"](call("wg:device:ios"), "en")
        menu = self.e["edit"].await_args.args[2]
        self.assertEqual(menu.inline_keyboard[1][0].callback_data, "wg:net:other:ios")

    async def test_busy_and_failed_delivery_release_guard(self):
        self.e["_building"].add(7)
        self.e["_deliver"] = AsyncMock(side_effect=RuntimeError("test"))
        await self.e["on_network_chosen"](call(), "en")
        self.e["_deliver"].assert_not_awaited()
        self.e["_building"].clear()
        with self.assertRaises(RuntimeError):
            await self.e["on_network_chosen"](call(), "en")
        self.assertEqual(self.e["_building"], set())

    async def test_empty_pool_does_not_register_or_deliver(self):
        self.e["warp_pool"].pick.return_value = []
        c = call()
        await self.e["_deliver"](c, N(edit_text=AsyncMock()), "en", "v6", "mtn", False, "ios")
        self.e["warpcore"].provision.assert_not_awaited()
        self.e["db"].save_warp_user.assert_not_awaited()
        c.message.answer_document.assert_not_awaited()

    async def test_ios_standard_config_and_android_awg_both_families(self):
        for platform in ("ios", "android"):
            for family, rows in (("v4", ROWS), ("v6", V6ROW)):
                with self.subTest(platform=platform, family=family):
                    self.e["warp_pool"].pick.return_value = copy.deepcopy(rows)
                    c = call()
                    await self.e["_deliver"](c, N(edit_text=AsyncMock()), "en", family, "other", False, platform)
                    file = c.message.answer_document.await_args.args[0]
                    parser = configparser.ConfigParser()
                    parser.read_string(file.data.decode())
                    self.assertEqual(parser.getint("Interface", "MTU"), 1280)
                    expected = "[2606:4700:d0::a29f:c001]:2408" if family == "v6" else "162.159.192.1:2408"
                    self.assertEqual(parser["Peer"]["Endpoint"], expected)
                    self.assertEqual("Jc" in parser["Interface"], platform == "android")
                    self.assertNotIn("I1", parser["Interface"])
                    self.assertNotIn("Reserved", parser["Peer"])
                    self.assertLessEqual(len(Path(file.filename).stem), 15)
                    self.assertEqual(self.e["db"].save_warp_user.await_args.args[1]["platform"], platform)

    async def test_existing_identity_is_reused(self):
        self.e["db"].get_warp_user.return_value = {"identity": dict(IDENTITY), "endpoints": ROWS}
        await self.e["_deliver"](call(), N(edit_text=AsyncMock()), "fa", "v6", "mtn", False, "ios")
        self.e["warpcore"].provision.assert_not_awaited()

    async def test_exports_use_ipv6_safe_renderer(self):
        e = self.e
        e["_profile"] = e["warpcore"].obfuscation
        e["_filename"] = lambda suffix: "test" + suffix
        functions("bot/handlers/warp.py", ["on_file"], e)
        e["db"].get_warp_user.return_value = {"identity": {**IDENTITY, "platform": "ios"}, "endpoints": V6ROW}
        for kind in ("plain", "awg", "awg2"):
            c = call(f"wg:file:{kind}")
            await e["on_file"](c, "en")
            file = c.message.answer_document.await_args.args[0]
            self.assertIn("Endpoint = [2606:4700:d0::a29f:c001]:2408", file.data.decode())
            self.assertLessEqual(len(Path(file.filename).stem), 15)
        e["db"].get_warp_user.return_value["endpoints"] = []
        c = call("wg:file:plain")
        await e["on_file"](c, "en")
        c.message.answer_document.assert_not_awaited()


def deploy_env():
    cf = N(verify_token=AsyncMock(), first_account=AsyncMock(return_value={"id": "account"}),
           ensure_subdomain=AsyncMock(return_value="example"), upload_script=AsyncMock(), enable_workers_dev=AsyncMock())
    class Context:
        async def __aenter__(self): return cf
        async def __aexit__(self, *args): return False
    env = {"CloudflareClient": lambda token: Context(), "CloudflareError": CFError, "DeployError": CFError,
           "Panel": lambda **kw: N(**kw), "time": time, "log": logging.getLogger("tests"),
           "_read_worker": lambda: "test worker", "_announce": AsyncMock(),
           "_select_endpoints": AsyncMock(return_value=copy.deepcopy(ROWS[:1])), "_select_relays": AsyncMock(return_value=[]),
           "_bindings": lambda uuid, host, endpoints, relays: {"endpoints": endpoints},
           "vless": N(new_uuid=lambda: "test-uuid"), "script_name": lambda: "test-script",
           "_demote_dead_relays": AsyncMock(), "_remember_reference": AsyncMock(),
           "settings": N(health_attempts=2), "asyncio": N(sleep=AsyncMock())}
    functions("bot/deploy.py", ["_endpoint_keys", "_require_healthy", "_health", "build", "refresh"], env)
    env["_health"] = AsyncMock(return_value=(True, {"ok": True}))
    env["_ship"] = AsyncMock(return_value=(copy.deepcopy(ROWS[1:]), []))
    return env, cf


class PanelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self): self.e, self.cf = deploy_env()

    async def test_fully_healed_list_is_republished(self):
        panel = await self.e["build"]("test-token")
        self.assertEqual(self.cf.upload_script.await_count, 2)
        self.assertEqual(self.cf.upload_script.await_args.args[3]["endpoints"], panel.endpoints)
        self.assertEqual(panel.rejected, 0)

    async def test_same_list_avoids_redundant_upload(self):
        self.e["_ship"].return_value = (copy.deepcopy(ROWS[:1]), [])
        await self.e["build"]("test-token")
        self.assertEqual(self.cf.upload_script.await_count, 1)

    async def test_empty_accepted_list_fails(self):
        self.e["_ship"].return_value = ([], ROWS)
        with self.assertRaisesRegex(CFError, "no endpoint"):
            await self.e["build"]("test-token")
        self.e["_remember_reference"].assert_not_awaited()

    async def test_failed_republish_is_not_reported_ready(self):
        self.cf.upload_script.side_effect = [None, CFError("denied")]
        with self.assertRaisesRegex(CFError, "verified endpoint list"):
            await self.e["build"]("test-token")
        self.e["_remember_reference"].assert_not_awaited()

    async def test_unhealthy_panel_never_demotes_endpoint_pool(self):
        self.e["_health"].return_value = (False, {"reason": "HTTP 403"})
        with self.assertRaisesRegex(CFError, "HTTP 403"):
            await self.e["build"]("test-token")
        self.e["_ship"].assert_not_awaited()
        self.e["_demote_dead_relays"].assert_not_awaited()

    async def test_unhealthy_refresh_does_not_scan_or_upload(self):
        self.e["_health"].return_value = (False, {"reason": "HTTP 429"})
        with self.assertRaises(CFError):
            await self.e["refresh"]({"token": "test", "host": "test.invalid", "uuid": "id"})
        self.cf.upload_script.assert_not_awaited()
        self.e["_select_endpoints"].assert_not_awaited()
        self.e["_ship"].assert_not_awaited()

    async def test_health_rejects_malformed_json_shapes_and_access_errors(self):
        env = self.e
        functions("bot/deploy.py", ["_health"], env)
        for responses in ([N(status_code=403)], [N(status_code=429)],
                          [N(status_code=200, json=lambda: [])] * 2,
                          [N(status_code=200, json=lambda: {"ok": True}), N(status_code=200, json=lambda: [])]):
            client = N(get=AsyncMock(side_effect=responses))
            class Context:
                async def __aenter__(self): return client
                async def __aexit__(self, *args): return False
            env["httpx"] = N(AsyncClient=lambda **kw: Context(), HTTPError=CFError)
            healthy, report = await env["_health"]("test.invalid", "id")
            self.assertFalse(healthy)
            self.assertIn("reason", report)


if __name__ == "__main__":
    unittest.main()
