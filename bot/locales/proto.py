"""Strings for the protocol picker, the operator leaderboard and the new QR screens.

Merged last in ``i18n`` so this catalogue owns every key it names - including
the ``wg.pick_net`` override that turns the two-button operator question into
the full six-operator picker.
"""

PROTO: dict[str, dict[str, str]] = {
    "fa": {
        # ------------------------------------------------------------ buttons
        "btn.protocols": "\U0001f39b \u0645\u0646\u0648\u06cc \u067e\u0631\u0648\u062a\u06a9\u0644\u200c\u0647\u0627",
        "btn.proto_all": "\U0001f381 \u062f\u0631\u06cc\u0627\u0641\u062a \u0647\u0645\u0647 \u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627 \u06cc\u06a9\u062c\u0627",
        "btn.proto_qr": "\U0001f4f7 \u0628\u0627\u0631\u06a9\u062f \u067e\u0631\u0648\u062a\u06a9\u0644",
        "btn.pool_ops": "\U0001f3c5 \u062c\u062f\u0648\u0644 \u0627\u067e\u0631\u0627\u062a\u0648\u0631\u0647\u0627",
        "btn.proto_vless": "VLESS / WS",
        "btn.proto_httpup": "HTTPUpgrade",
        "btn.proto_xhttp": "XHTTP",
        "btn.proto_trojan": "Trojan",
        "btn.proto_ss": "Shadowsocks",
        "btn.warp_qr": "\U0001f4f7 \u0628\u0627\u0631\u06a9\u062f \u0644\u06cc\u0646\u06a9 \u0648\u0627\u0631\u067e",
        # -------------------------------------------------------- picker text
        "proto.menu": (
            "\u200f\U0001f391 <b>\u0645\u0646\u0648\u06cc \u067e\u0631\u0648\u062a\u06a9\u0644\u200c\u0647\u0627</b>\n"
            "\u200f{rule}\n"
            "\u200f\u0647\u0631 \u067e\u0631\u0648\u062a\u06a9\u0644 \u0631\u0627 \u062c\u062f\u0627\u06af\u0627\u0646\u0647 \u0628\u06af\u06cc\u0631 \u06cc\u0627 \u062a\u0645\u0627\u0645 \u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627 \u0631\u0627 \u06cc\u06a9\u062c\u0627 \u062f\u0631\u06cc\u0627\u0641\u062a \u06a9\u0646.\n"
            "\u200f\U0001f30d \u0645\u06cc\u0632\u0628\u0627\u0646: <code>{host}</code> \u00b7 \U0001f4e6 \u06a9\u0627\u0646\u0641\u06cc\u06af: <b>{count}</b>\n"
            "\u200f{rule}\n"
            "\u200f\u00b7 <b>VLESS WS</b> \u2014 \u067e\u0627\u06cc\u0647\u060c \u062f\u0631 \u0647\u0645\u0647 \u06a9\u0644\u0627\u06cc\u0646\u062a\u200c\u0647\u0627\n"
            "\u200f\u00b7 <b>HTTPUpgrade</b> \u2014 \u0647\u0645\u0627\u0646 \u0645\u0633\u06cc\u0631 \u0628\u0627 \u062f\u0633\u062a\u0634\u0647 \u062a\u0642\u0648\u06cc\u062a\u200c\u0634\u062f\u0647\n"
            "\u200f\u00b7 <b>XHTTP</b> \u2014 \u0645\u062f stream-one\u060c \u0641\u0642\u0637 TLS\n"
            "\u200f\u00b7 <b>Trojan</b> \u2014 \u0647\u0646\u062f\u0634\u06cc\u06a9 \u0645\u062a\u0641\u0627\u0648\u062a\u060c \u0631\u0648\u06cc \u0647\u0645\u0627\u0646 \u0648\u0631\u06a9\u0631\n"
            "\u200f\u00b7 <b>Shadowsocks</b> \u2014 \u0633\u0627\u062f\u0647 \u0648 \u0633\u0631\u06cc\u0639\n"
            "\u200f\u00b7 <b>WARP / WireGuard</b> \u2014 \u062a\u0648\u0646\u0644 \u0627\u062e\u062a\u0635\u0627\u0635\u06cc \u06a9\u0644\u0627\u062f\u0641\u0644\u0631"
        ),
        "proto.menu_free": (
            "\u200f\u26a0\ufe0f \u0647\u0646\u0648\u0632 \u067e\u0646\u0644\u06cc \u0633\u0627\u062e\u062a\u0647 \u0646\u0634\u062f\u0647\u060c \u0628\u0646\u0627\u0628\u0631\u0627\u06cc\u0646 \u067e\u0631\u0648\u062a\u06a9\u0644\u200c\u0647\u0627\u06cc \u0634\u062e\u0635\u06cc \u0646\u062f\u0627\u0631\u06cc.\n"
            "\u200f\U0001f381 \u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627\u06cc \u0631\u0627\u06cc\u06af\u0627\u0646 \u0628\u0627 \u0647\u0645\u0647 \u067e\u0631\u0648\u062a\u06a9\u0644\u200c\u0647\u0627 \u0627\u0632 \u062f\u06a9\u0645\u0647\u06cc \u06a9\u0627\u0646\u0641\u06cc\u06af \u0631\u0627\u06cc\u06af\u0627\u0646 \u062f\u0631 \u0645\u0646\u0648\u06cc \u0627\u0635\u0644\u06cc \u062f\u0631\u062f\u0633\u062a \u0627\u0633\u062a."
        ),
        "proto.warp_hint": (
            "\u200f\U0001f7eb WARP \u0648 \u0648\u0627\u06cc\u0631\u06af\u0627\u0631\u062f \u0628\u062e\u0634 \u062e\u0648\u062f\u0634 \u0631\u0627 \u062f\u0627\u0631\u0646\u062f: \u0627\u0632 \u062f\u06a9\u0645\u0647\u06cc WARP \u062f\u0631 \u0645\u0646\u0648 \u0627\u0635\u0644\u06cc\u060c "
            "\u0628\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u0627\u067e\u0631\u0627\u062a\u0648\u0631 \u0648 \u062f\u0631\u06cc\u0627\u0641\u062a \u06a9\u0627\u0646\u0641\u06cc\u06af \u0622\u0645\u0627\u062f\u0647."
        ),
        # --------------------------------------------------------- delivery
        "proto.vless_note": (
            "\u200f\U0001f4a0 <b>VLESS / WebSocket</b> \u2014 {count} \u06a9\u0627\u0646\u0641\u06cc\u06af\n"
            "\u200f{links}"
        ),
        "proto.up_note": (
            "\u200f\u267b\ufe0f <b>HTTPUpgrade</b> \u2014 {count} \u06a9\u0627\u0646\u0641\u06cc\u06af\n"
            "\u200f{links}"
        ),
        "proto.xhttp_note": (
            "\u200f\U0001f680 <b>XHTTP (stream-one)</b> \u2014 {count} \u06a9\u0627\u0646\u0641\u06cc\u06af\n"
            "\u200f{links}\n\n"
            "\u200f\u2139\ufe0f \u0641\u0642\u0637 \u0631\u0648\u06cc \u067e\u0648\u0631\u062a\u200c\u0647\u0627\u06cc TLS \u0633\u0627\u062e\u062a\u0647 \u0645\u06cc\u200c\u0634\u0648\u062f\u061b \u062f\u0631 v2rayNG \u0648 Hiddify \u062a\u0633\u062a \u06a9\u0646."
        ),
        "proto.ss_note": (
            "\u200f\U0001f510 <b>Shadowsocks</b> \u2014 {count} \u06a9\u0627\u0646\u0641\u06cc\u06af\n"
            "\u200f{links}"
        ),
        "proto.no_tls": (
            "\u200f\u274c \u0627\u06cc\u0646 \u067e\u0631\u0648\u062a\u06a9\u0644 \u0628\u0647 \u067e\u0648\u0631\u062a\u200c\u0647\u0627\u06cc TLS \u0646\u06cc\u0627\u0632 \u062f\u0627\u0631\u062f \u0648 \u0627\u06cc\u0646 \u0645\u0648\u0642\u0639 \u067e\u0648\u0631\u062a TLS \u0633\u0627\u0644\u0645 \u0646\u062f\u0627\u0631\u06cc\u0645. "
            "\u200f\u062f\u06a9\u0645\u0647\u06cc \u00ab\u0627\u0639\u0645\u0627\u0644 \u0622\u06cc\u200c\u067e\u06cc \u062a\u0645\u06cc\u0632\u00bb \u0631\u0627 \u0628\u0632\u0646 \u062a\u0627 \u067e\u0648\u0631\u062a \u062a\u0627\u0632\u0647 \u0628\u06cc\u0627\u06cc\u062f."
        ),
        "proto.zip_caption": (
            "\u200f\U0001f381 <b>\u0628\u0633\u062a\u0647\u06cc \u06a9\u0627\u0645\u0644 \u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627</b> \u2014 {count} \u0641\u0627\u06cc\u0644\n"
            "\u200f{rule}\n"
            "\u200f\u062f\u0631\u0648\u0646 \u0632\u06cc\u067e: \u0644\u06cc\u0646\u06a9\u200c\u0647\u0627\u06cc VLESS \u0648 HTTPUpgrade \u0648 XHTTP \u0648 Trojan \u0648 Shadowsocks\u060c "
            "\u062e\u0631\u0648\u062c\u06cc Clash \u0648 sing-box\u060c \u06a9\u0627\u0646\u0641\u06cc\u06af Fragment Xray \u0648 \u0644\u06cc\u0646\u06a9\u200c\u0647\u0627\u06cc WARP.\n"
            "\u200f\U0001f4e5 \u0647\u0631 \u0641\u0627\u06cc\u0644 \u062c\u062f\u0627 \u0647\u0645 \u062f\u0631 \u0647\u0645\u06cc\u0646 \u06af\u0641\u062a\u06af\u0648 \u0627\u0631\u0633\u0627\u0644 \u0634\u062f\u0647 \u0627\u0633\u062a."
        ),
        "proto.all_summary": (
            "\u200f\u2705 <b>\u0647\u0645\u0647 \u067e\u0631\u0648\u062a\u06a9\u0644\u200c\u0647\u0627 \u0622\u0645\u0627\u062f\u0647 \u0634\u062f\u0646\u062f</b>\n"
            "\u200f{rule}\n{lines}"
        ),
        "proto.all_line": "\u200f\u00b7 {name}: <b>{count}</b>",
        "proto.all_skip": "\u200f\u00b7 {name}: \u2014",
        # ------------------------------------------------------------- QR
        "proto.qr_caption": "\U0001f4f7 \u0628\u0627\u0631\u06a9\u062f {name} \u2014 \u0628\u0627 \u062f\u0648\u0631\u0628\u06cc\u0646 \u0628\u062e\u0648\u0627\u0646 \u06cc\u0627 \u062f\u0631 \u06a9\u0644\u0627\u06cc\u0646\u062a Import \u06a9\u0646",
        "proto.qr_screen": (
            "\u200f\U0001f4f7 <b>\u0628\u0627\u0631\u06a9\u062f \u06a9\u062f \u067e\u0631\u0648\u062a\u06a9\u0644\u200c\u0647\u0627</b>\n"
            "\u200f{rule}\n"
            "\u200f\u067e\u0631\u0648\u062a\u06a9\u0644 \u0645\u0648\u0631\u062f \u0646\u0638\u0631 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646 \u062a\u0627 \u0628\u0627\u0631\u06a9\u062f \u0627\u0648\u0644\u06cc\u0646 \u06a9\u0627\u0646\u0641\u06cc\u06af \u0622\u0646 \u0627\u0631\u0633\u0627\u0644 \u0634\u0648\u062f."
        ),
        "proto.qr_empty": "\u200f\u274c \u0628\u0631\u0627\u06cc \u0627\u06cc\u0646 \u067e\u0631\u0648\u062a\u06a9\u0644 \u0644\u06cc\u0646\u06a9 \u0633\u0627\u0644\u0645\u06cc \u067e\u06cc\u062f\u0627 \u0646\u0634\u062f.",
        # --------------------------------------------- operator-aware WARP
        "wg.pick_net": (
            "\u200f\U0001f9ec <b>\u0633\u0627\u062e\u062a WARP / WireGuard</b>\n"
            "\u200f{rule}\n"
            "\u200f\u0627\u067e\u0631\u0627\u062a\u0648\u0631\u062a \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646 \u062a\u0627 \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a\u200c\u0647\u0627\u06cc \u062a\u0645\u06cc\u0632 \u0648 \u0633\u0627\u0644\u0645 \u0647\u0645\u0627\u0646 \u0634\u0628\u06a9\u0647 \u0631\u0627 \u0628\u06af\u06cc\u0631\u06cc.\n"
            "\u200f\U0001f3af \u0628\u0631\u0627\u06cc \u0647\u0631 \u0627\u067e\u0631\u0627\u062a\u0648\u0631\u060c \u067e\u0648\u0631\u062a\u200c\u0647\u0627\u06cc \u0645\u0646\u0627\u0633\u0628 \u0627\u0648\u0644\u0648\u06cc\u062a \u0645\u06cc\u200c\u06af\u06cc\u0631\u0646\u062f \u0648 \u0646\u062a\u0627\u06cc\u062c \u0628\u0646\u0634\u0645\u0627\u0631\u200c\u0647\u0627\u06cc \u0648\u0627\u0642\u0639\u06cc \u06a9\u0627\u0631\u0628\u0631\u0627\u0646 \u0647\u0645\u0627\u0646 \u0634\u0628\u06a9\u0647 \u0627\u0646\u062f\u06cc\u0632 \u0645\u06cc\u200c\u0634\u0648\u062f.\n"
            "\u200f\U0001f407 \u0627\u06cc\u0631\u0627\u0646\u0633\u0644 \u2190 \u0645\u0633\u06cc\u0631 IPv6 \u062f\u0631 \u0627\u0648\u0644\u0648\u06cc\u062a \u0627\u0633\u062a.\n\n"
            "\u200f\U0001f3c0 \u0627\u0633\u062a\u062e\u0631 IPv4: <b>{v4}</b>/{target} \u00b7 IPv6: <b>{v6}</b>/{target}\n"
            "\u200f\U0001f465 \u0634\u0648\u0627\u0647\u062f \u0627\u067e\u0631\u0627\u062a\u0648\u0631\u200c\u0647\u0627: {ops}\n"
            "\u200f\u26a1 \u062a\u0645\u0627\u0645 \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a\u200c\u0647\u0627 \u0628\u0627 \u0647\u0646\u062f\u0634\u06cc\u06a9 \u0648\u0627\u0642\u0639\u06cc WireGuard \u062a\u0633\u062a \u0634\u062f\u0647\u200c\u0627\u0646\u062f."
        ),
        "wg.ops_count": "{op} <b>{proven}</b>/{known}",
        "wg.operator_tip": "\u200f\U0001f4a1 \u0646\u06a9\u062a\u0647\u06cc {operator}: {tip}",
        "wg.op_learned": "\u200f\U0001f396 \u0648\u06cc\u0698\u06af\u06cc \u0627\u067e\u0631\u0627\u062a\u0648\u0631: {detail}",
        # --------------------------------------------- admin ops leaderboard
        "pool.ops_screen": (
            "\u200f\U0001f3c5 <b>\u062c\u062f\u0648\u0644 \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a \u0628\u0647 \u062a\u0641\u06a9\u06cc\u06a9 \u0627\u067e\u0631\u0627\u062a\u0648\u0631</b>\n"
            "\u200f{rule}\n"
            "\u200f\u062f\u0631 \u0627\u06cc\u0646 \u062c\u062f\u0648\u0644\u060c \u0646\u062a\u0627\u06cc\u062c \u0628\u0646\u0634\u0645\u0627\u0631\u200c\u0647\u0627\u06cc \u0648\u0627\u0642\u0639\u06cc \u06a9\u0627\u0631\u0628\u0631\u0627\u0646 \u0647\u0631 \u0634\u0628\u06a9\u0647 \u0627\u0646\u062f\u06cc\u0632 \u0645\u06cc\u200c\u0634\u0648\u062f: "
            "\u0647\u0631 \u0628\u0646\u0634\u0645\u0627\u0631 wg:bench \u06cc\u06a9 \u062a\u0633\u062a \u062b\u0628\u062a \u0645\u06cc\u200c\u06a9\u0646\u062f \u0648 \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a\u200c\u0647\u0627\u06cc \u0628\u0631\u0646\u062f\u0647 \u0628\u0647 \u0628\u0627\u0632\u062f\u06cc\u062f\u0646\u062f\u0647\u200c\u0647\u0627\u06cc \u0622\u06cc\u0646\u062f\u0647\u0654 \u0647\u0645\u0627\u0646 \u0627\u067e\u0631\u0627\u062a\u0648\u0631 \u062a\u0645\u0627\u06cc\u0644 \u0645\u06cc\u200c\u06af\u06cc\u0631\u0646\u062f.\n"
            "\u200f{rule}\n{body}\n"
            "\u200f{rule}\n"
            "\u200f\U0001f4a1 \u062f\u0631\u0648\u0646 \u0627\u0633\u062a\u062e\u0631 \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a: IPv4 <b>{v4}</b> \u00b7 IPv6 <b>{v6}</b> \u2014 "
            "\u0627\u0648\u0644\u0648\u06cc\u062a \u067e\u0648\u0631\u062a \u0647\u0631 \u0627\u067e\u0631\u0627\u062a\u0648\u0631 \u0627\u0632 \u067e\u0631\u0648\u0641\u0627\u06cc\u0644 \u0647\u0645\u0627\u0646 \u0634\u0628\u06a9\u0647 \u0645\u06cc\u200c\u0622\u06cc\u062f."
        ),
        "pool.ops_section": "\u200f\U0001f4f6 <b>{op}</b> \u2014 \u0634\u0648\u0627\u0647\u062f: {known} \u00b7 \u0628\u0631\u0646\u062f\u0647: {proven}",
        "pool.ops_line": "\u200f\u00b7 <code>{endpoint}</code> \u00b7 \U0001f3c5 {wins}/{tests} \u00b7 {ping}",
        "pool.ops_empty": "\u200f\u00b7 \u0647\u0646\u0648\u0632 \u0634\u0648\u0627\u0647\u062f\u06cc \u062b\u0628\u062a \u0646\u0634\u062f\u0647 \u0627\u0633\u062a.",
        "pool.ops_footer": (
            "\u200f\U0001f4a1 \u062f\u0631\u0648\u0646 \u0627\u0633\u062a\u062e\u0631 \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a: IPv4 <b>{v4}</b> \u00b7 IPv6 <b>{v6}</b> \u2014 "
            "\u0627\u0648\u0644\u0648\u06cc\u062a \u067e\u0648\u0631\u062a \u0647\u0631 \u0627\u067e\u0631\u0627\u062a\u0648\u0631 \u0627\u0632 \u067e\u0631\u0648\u0641\u0627\u06cc\u0644 \u0647\u0645\u0627\u0646 \u0634\u0628\u06a9\u0647 \u0645\u06cc\u200c\u0622\u06cc\u062f."
        ),
    },
    "en": {
        "btn.protocols": "\U0001f391 Protocol menu",
        "btn.proto_all": "\U0001f381 Get every config",
        "btn.proto_qr": "\U0001f4f7 Protocol QR",
        "btn.pool_ops": "\U0001f3c5 Operator leaderboard",
        "btn.proto_vless": "VLESS / WS",
        "btn.proto_httpup": "HTTPUpgrade",
        "btn.proto_xhttp": "XHTTP",
        "btn.proto_trojan": "Trojan",
        "btn.proto_ss": "Shadowsocks",
        "btn.warp_qr": "\U0001f4f7 WARP link QR",
        "proto.menu": (
            "\U0001f391 <b>Protocol menu</b>\n"
            "{rule}\n"
            "Take each protocol on its own, or grab every config at once.\n"
            "\U0001f30d Host: <code>{host}</code> \u00b7 \U0001f4e6 Configs: <b>{count}</b>\n"
            "{rule}\n"
            "\u00b7 <b>VLESS WS</b> \u2014 the baseline, works in every client\n"
            "\u00b7 <b>HTTPUpgrade</b> \u2014 same route, upgraded handshake\n"
            "\u00b7 <b>XHTTP</b> \u2014 stream-one mode, TLS only\n"
            "\u00b7 <b>Trojan</b> \u2014 a different handshake on the same worker\n"
            "\u00b7 <b>Shadowsocks</b> \u2014 simple and fast\n"
            "\u00b7 <b>WARP / WireGuard</b> \u2014 Cloudflare's own tunnel"
        ),
        "proto.menu_free": (
            "\u26a0\ufe0f No panel yet, so there are no personal protocols to hand out.\n"
            "\U0001f381 The free configs - all protocols included - are on the Free configs button in the main menu."
        ),
        "proto.warp_hint": (
            "\U0001f7eb WARP and WireGuard have their own section: the WARP button in the main menu, "
            "pick an operator and get a ready config."
        ),
        "proto.vless_note": "\U0001f4a0 <b>VLESS / WebSocket</b> \u2014 {count} configs\n{links}",
        "proto.up_note": "\u267b\ufe0f <b>HTTPUpgrade</b> \u2014 {count} configs\n{links}",
        "proto.xhttp_note": (
            "\U0001f680 <b>XHTTP (stream-one)</b> \u2014 {count} configs\n{links}\n\n"
            "\u2139\ufe0f Built on TLS ports only; test it in v2rayNG or Hiddify."
        ),
        "proto.ss_note": "\U0001f510 <b>Shadowsocks</b> \u2014 {count} configs\n{links}",
        "proto.no_tls": (
            "\u274c This protocol needs TLS ports and the panel has no healthy TLS port right now. "
            "Press Apply clean IPs so fresh ports land."
        ),
        "proto.zip_caption": (
            "\U0001f381 <b>The full config bundle</b> \u2014 {count} files\n"
            "{rule}\n"
            "Inside the zip: VLESS, HTTPUpgrade, XHTTP, Trojan and Shadowsocks links, "
            "Clash and sing-box exports, the fragmented Xray config and the WARP links.\n"
            "\U0001f4e5 Every file was also sent separately in this chat."
        ),
        "proto.all_summary": "\u2705 <b>Every protocol is ready</b>\n{rule}\n{lines}",
        "proto.all_line": "\u00b7 {name}: <b>{count}</b>",
        "proto.all_skip": "\u00b7 {name}: \u2014",
        "proto.qr_caption": "\U0001f4f7 {name} QR \u2014 scan it or import it into the client",
        "proto.qr_screen": (
            "\U0001f4f7 <b>Protocol QR codes</b>\n"
            "{rule}\n"
            "Pick a protocol and the QR of its first config arrives as a photo."
        ),
        "proto.qr_empty": "\u274c No working link found for this protocol.",
        "wg.pick_net": (
            "\U0001f9ec <b>Build WARP / WireGuard</b>\n"
            "{rule}\n"
            "Pick your operator and I will hand you the clean, healthy endpoints of that exact network.\n"
            "\U0001f3af Each operator gets its own port priority, and real benchmark wins from users on the "
            "same network feed back into the ranking.\n"
            "\U0001f407 Irancell \u2190 IPv6 route first.\n\n"
            "\U0001f3c0 IPv4 pool: <b>{v4}</b>/{target} \u00b7 IPv6: <b>{v6}</b>/{target}\n"
            "\U0001f465 Operator evidence: {ops}\n"
            "\u26a1 Every pool endpoint passed a real WireGuard handshake."
        ),
        "wg.ops_count": "{op} <b>{proven}</b>/{known}",
        "wg.operator_tip": "\U0001f4a1 {operator} tip: {tip}",
        "wg.op_learned": "\U0001f396 Operator fit: {detail}",
        "pool.ops_screen": (
            "\U0001f3c5 <b>Endpoint leaderboard, by operator</b>\n"
            "{rule}\n"
            "Real benchmark results from users on each network accumulate here: every wg:bench run "
            "records a test, and winning endpoints lean the future picks of that same operator.\n"
            "{rule}\n{body}\n"
            "{rule}\n"
            "\U0001f4a1 Pool right now: IPv4 <b>{v4}</b> \u00b7 IPv6 <b>{v6}</b> \u2014 each operator's port priority "
            "comes from its own profile."
        ),
        "pool.ops_section": "\U0001f4f6 <b>{op}</b> \u2014 evidence: {known} \u00b7 winners: {proven}",
        "pool.ops_line": "\u00b7 <code>{endpoint}</code> \u00b7 \U0001f3c5 {wins}/{tests} \u00b7 {ping}",
        "pool.ops_empty": "\u00b7 No evidence recorded yet.",
        "pool.ops_footer": (
            "\U0001f4a1 Pool right now: IPv4 <b>{v4}</b> \u00b7 IPv6 <b>{v6}</b> \u2014 each operator's port priority "
            "comes from its own profile."
        ),
    },
}
