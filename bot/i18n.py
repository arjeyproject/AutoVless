"""Bilingual copy. Persian is the default, English is a full peer."""

from __future__ import annotations

from typing import Any

from .config import settings

LANGS = ("fa", "en")
_PERSIAN_DIGITS = str.maketrans("0123456789", "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9")


def num(value: Any, lang: str) -> str:
    text = str(value)
    return text.translate(_PERSIAN_DIGITS) if lang == "fa" else text


TEXTS: dict[str, dict[str, str]] = {
    # ---------------------------------------------------------------- main
    "main_menu": {
        "fa": (
            "\u26a1 <b>{brand}</b> \u00b7 \u0646\u0633\u062e\u0647 \u062a\u0648\u0631\u0628\u0648 \u26a1\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\U0001f44b \u0633\u0644\u0627\u0645 <b>{name}</b> \u062c\u0627\u0646!\n"
            "\u0645\u0646 \u0631\u0648\u06cc \u0627\u06a9\u0627\u0646\u062a \u06a9\u0644\u0627\u062f\u0641\u0644\u0631 \u062e\u0648\u062f\u062a \u06cc\u06a9 \u067e\u0646\u0644 \u0627\u062e\u062a\u0635\u0627\u0635\u06cc \u0645\u06cc\u200c\u0633\u0627\u0632\u0645 "
            "\u0648 \u0633\u0631\u06cc\u0639\u200c\u062a\u0631\u06cc\u0646 \u0622\u06cc\u200c\u067e\u06cc\u200c\u0647\u0627\u06cc \u062a\u0645\u06cc\u0632 \u0631\u0627 \u062e\u0648\u062f\u06a9\u0627\u0631 \u0633\u0648\u0627\u0631 \u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627\u062a \u0645\u06cc\u200c\u06a9\u0646\u0645.\n\n"
            "\U0001f525 <b>\u0645\u0648\u062a\u0648\u0631 \u0632\u0646\u062f\u0647 \u0627\u06cc\u0646 \u0644\u062d\u0637\u0647</b>\n"
            "\U0001f4e1 \u0622\u06cc\u200c\u067e\u06cc \u062a\u0645\u06cc\u0632 \u0622\u0645\u0627\u062f\u0647: <b>{pool}</b>\n"
            "\U0001f680 \u0632\u06cc\u0631 \u06f7\u06f0\u06f0 \u0645\u06cc\u0644\u06cc\u200c\u062b\u0627\u0646\u06cc\u0647: <b>{fast}</b>\n"
            "\U0001f3c6 \u0628\u0647\u062a\u0631\u06cc\u0646 \u067e\u06cc\u0646\u06af: <b>{best}</b>\n"
            "\U0001f6e1 \u0631\u0644\u0647\u200c\u0647\u0627\u06cc \u0633\u0627\u0644\u0645: <b>{healthy}</b>\n\n"
            "\U0001f447 \u0627\u0632 \u062f\u06a9\u0645\u0647\u200c\u0647\u0627\u06cc \u067e\u0627\u06cc\u06cc\u0646 \u0634\u0631\u0648\u0639 \u06a9\u0646:"
        ),
        "en": (
            "\u26a1 <b>{brand}</b> \u00b7 turbo build \u26a1\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\U0001f44b Hey <b>{name}</b>!\n"
            "I build a private panel on your own Cloudflare account and mount the fastest clean IPs on your configs automatically.\n\n"
            "\U0001f525 <b>Live engine</b>\n"
            "\U0001f4e1 Clean IPs ready: <b>{pool}</b>\n"
            "\U0001f680 Under 700 ms: <b>{fast}</b>\n"
            "\U0001f3c6 Best ping: <b>{best}</b>\n"
            "\U0001f6e1 Healthy relays: <b>{healthy}</b>\n\n"
            "\U0001f447 Pick an option:"
        ),
    },
    "support_message": {
        "fa": (
            "\u2764\ufe0f <b>\u062d\u0645\u0627\u06cc\u062a \u0627\u0632 \u0645\u0627</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "{brand} \u06a9\u0627\u0645\u0644\u0627\u064b \u0631\u0627\u06cc\u06af\u0627\u0646 \u0627\u0633\u062a \u0648 \u0628\u0631\u0627\u06cc \u062f\u0633\u062a\u0631\u0633\u06cc \u0622\u0632\u0627\u062f \u0645\u0631\u062f\u0645 \u0628\u0647 \u0627\u06cc\u0646\u062a\u0631\u0646\u062a \u0633\u0627\u062e\u062a\u0647 \u0634\u062f\u0647.\n\n"
            "\u2022 \u0631\u0628\u0627\u062a \u0631\u0627 \u0628\u0647 \u062f\u0648\u0633\u062a\u0627\u0646\u062a \u0645\u0639\u0631\u0641\u06cc \u06a9\u0646\n"
            "\u2022 \u0628\u0647 \u067e\u0631\u0648\u0698\u0647 \u062f\u0631 \u06af\u06cc\u062a\u200c\u0647\u0627\u0628 \u0633\u062a\u0627\u0631\u0647 \u0628\u062f\u0647\n"
            "\u2022 \u0628\u0627\u06af \u06cc\u0627 \u067e\u06cc\u0634\u0646\u0647\u0627\u062f\u062a \u0631\u0627 \u0628\u0647 \u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc \u0628\u06af\u0648\n\n"
            "\U0001f34a \u0647\u0631 \u06a9\u0627\u0646\u0641\u06cc\u06af\u06cc \u06a9\u0647 \u0628\u0647 \u062f\u0633\u062a \u06cc\u06a9 \u0646\u0641\u0631 \u062f\u06cc\u06af\u0631 \u0628\u0631\u0633\u0627\u0646\u06cc\u060c \u06cc\u06a9 \u067e\u0646\u062c\u0631\u0647 \u062a\u0627\u0632\u0647 \u0628\u0627\u0632 \u06a9\u0631\u062f\u0647\u200c\u0627\u06cc."
        ),
        "en": (
            "\u2764\ufe0f <b>Support us</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "{brand} is free and exists so people can reach a free internet.\n\n"
            "\u2022 Share the bot with a friend\n"
            "\u2022 Star the project on GitHub\n"
            "\u2022 Send bugs and ideas to support\n\n"
            "\U0001f34a Every config you pass on opens one more window."
        ),
    },
    # ---------------------------------------------------------------- build
    "token_intro": {
        "fa": (
            "\U0001f680 <b>\u0633\u0627\u062e\u062a \u067e\u0646\u0644 \u062a\u0648\u0631\u0628\u0648</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\u0031\ufe0f\u20e3 \u0627\u06af\u0631 \u0627\u06a9\u0627\u0646\u062a \u06a9\u0644\u0627\u062f\u0641\u0644\u0631 \u0646\u062f\u0627\u0631\u06cc\u060c \u0627\u0648\u0644 <b>\u062b\u0628\u062a \u0646\u0627\u0645</b> \u06a9\u0646.\n"
            "\u0032\ufe0f\u20e3 \u062f\u06a9\u0645\u0647 <b>\u062f\u0631\u06cc\u0627\u0641\u062a \u062a\u0648\u06a9\u0646</b> \u0631\u0627 \u0628\u0632\u0646 (\u062f\u0633\u062a\u0631\u0633\u06cc\u200c\u0647\u0627 \u0627\u0632 \u0642\u0628\u0644 \u0627\u0646\u062a\u062e\u0627\u0628 \u0634\u062f\u0647\u200c\u0627\u0646\u062f).\n"
            "\u0033\ufe0f\u20e3 \u062f\u0631 \u06a9\u0644\u0627\u062f\u0641\u0644\u0631 <code>Continue to summary</code> \u0648 \u0628\u0639\u062f <code>Create Token</code>.\n"
            "\u0034\ufe0f\u20e3 \u062a\u0648\u06a9\u0646 \u0631\u0627 \u06a9\u067e\u06cc \u06a9\u0646 \u0648 \u0647\u0645\u06cc\u0646\u062c\u0627 \u0628\u0641\u0631\u0633\u062a.\n\n"
            "\U0001f512 \u062a\u0648\u06a9\u0646 \u0641\u0642\u0637 \u0631\u0648\u06cc \u0627\u06a9\u0627\u0646\u062a \u062e\u0648\u062f\u062a \u06a9\u0627\u0631 \u0645\u06cc\u200c\u06a9\u0646\u062f \u0648 \u0641\u0642\u0637 \u0628\u0631\u0627\u06cc \u0633\u0627\u062e\u062a \u0648\u0631\u06a9\u0631 \u0644\u0627\u0632\u0645 \u0627\u0633\u062a.\n"
            "\u23f1 \u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 \u0632\u0645\u0627\u0646 \u062a\u062d\u0648\u06cc\u0644: \u06f2\u06f0 \u062a\u0627 \u06f4\u06f5 \u062b\u0627\u0646\u06cc\u0647 \u26a1"
        ),
        "en": (
            "\U0001f680 <b>Build a turbo panel</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\u0031\ufe0f\u20e3 No Cloudflare account yet? <b>Sign up</b> first.\n"
            "\u0032\ufe0f\u20e3 Tap <b>Get token</b> (permissions are pre-selected).\n"
            "\u0033\ufe0f\u20e3 In Cloudflare press <code>Continue to summary</code>, then <code>Create Token</code>.\n"
            "\u0034\ufe0f\u20e3 Copy the token and paste it right here.\n\n"
            "\U0001f512 The token only works on your own account and is only needed to create the Worker.\n"
            "\u23f1 Typical delivery time: 20 to 45 seconds \u26a1"
        ),
    },
    "token_bad_format": {
        "fa": "\u26a0\ufe0f \u0627\u06cc\u0646 \u0645\u062a\u0646 \u0634\u0628\u06cc\u0647 \u062a\u0648\u06a9\u0646 \u06a9\u0644\u0627\u062f\u0641\u0644\u0631 \u0646\u06cc\u0633\u062a. \u0641\u0642\u0637 \u062e\u0648\u062f \u062a\u0648\u06a9\u0646 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u060c \u0628\u062f\u0648\u0646 \u0644\u06cc\u0646\u06a9 \u06cc\u0627 \u062a\u0648\u0636\u06cc\u062d \u0627\u0636\u0627\u0641\u0647.",
        "en": "\u26a0\ufe0f That does not look like a Cloudflare token. Send only the token, without links or extra text.",
    },
    "token_checking": {
        "fa": "\U0001f50d \u062f\u0627\u0631\u0645 \u062a\u0648\u06a9\u0646 \u0631\u0627 \u0628\u0631\u0631\u0633\u06cc \u0645\u06cc\u200c\u06a9\u0646\u0645...",
        "en": "\U0001f50d Verifying your token...",
    },
    "token_rejected": {
        "fa": (
            "\u274c \u06a9\u0644\u0627\u062f\u0641\u0644\u0631 \u0627\u06cc\u0646 \u062a\u0648\u06a9\u0646 \u0631\u0627 \u0642\u0628\u0648\u0644 \u0646\u06a9\u0631\u062f.\n\n"
            "<b>\u062f\u0644\u06cc\u0644:</b> <code>{reason}</code>\n\n"
            "\u062f\u0648\u0628\u0627\u0631\u0647 \u0627\u0632 \u062f\u06a9\u0645\u0647 \u00ab\u062f\u0631\u06cc\u0627\u0641\u062a \u062a\u0648\u06a9\u0646\u00bb \u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u06a9\u0646 \u062a\u0627 \u062f\u0633\u062a\u0631\u0633\u06cc\u200c\u0647\u0627 \u062f\u0631\u0633\u062a \u062a\u0646\u0638\u06cc\u0645 \u0634\u0648\u0646\u062f."
        ),
        "en": (
            "\u274c Cloudflare rejected this token.\n\n"
            "<b>Reason:</b> <code>{reason}</code>\n\n"
            "Use the \u201cGet token\u201d button again so the permissions are set correctly."
        ),
    },
    "build_step": {
        "fa": "\u2699\ufe0f <b>\u062f\u0631 \u062d\u0627\u0644 \u0633\u0627\u062e\u062a</b>\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n{steps}",
        "en": "\u2699\ufe0f <b>Building</b>\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n{steps}",
    },
    "step_verify": {"fa": "\u0628\u0631\u0631\u0633\u06cc \u062a\u0648\u06a9\u0646 \u0648 \u0627\u06a9\u0627\u0646\u062a", "en": "Verifying token and account"},
    "step_subdomain": {"fa": "\u0622\u0645\u0627\u062f\u0647\u200c\u0633\u0627\u0632\u06cc \u062f\u0627\u0645\u0646\u0647 workers.dev", "en": "Preparing the workers.dev subdomain"},
    "step_scan": {"fa": "\u0627\u0646\u062a\u062e\u0627\u0628 \u0622\u06cc\u200c\u067e\u06cc \u062a\u0645\u06cc\u0632", "en": "Selecting clean IPs"},
    "step_deploy": {"fa": "\u0622\u067e\u0644\u0648\u062f \u0648\u0631\u06a9\u0631 \u0631\u0648\u06cc \u0627\u06a9\u0627\u0646\u062a \u062a\u0648", "en": "Uploading the Worker to your account"},
    "step_health": {"fa": "\u062a\u0633\u062a \u0633\u0644\u0627\u0645\u062a \u067e\u0646\u0644", "en": "Health checking the panel"},
    "panel_ready": {
        "fa": (
            "\U0001f389 <b>\u067e\u0646\u0644 \u062a\u0648 \u0622\u0645\u0627\u062f\u0647 \u0634\u062f!</b> \U0001f680\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\u23f1 \u0632\u0645\u0627\u0646 \u0633\u0627\u062e\u062a: <b>{seconds}</b> \u062b\u0627\u0646\u06cc\u0647\n"
            "\U0001f3c6 \u0628\u0647\u062a\u0631\u06cc\u0646 \u067e\u06cc\u0646\u06af: <b>{best}</b>\n"
            "\U0001f680 \u0632\u06cc\u0631 \u06f7\u06f0\u06f0ms: <b>{fast}</b> \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a\n"
            "\U0001f4e6 \u062a\u0639\u062f\u0627\u062f \u06a9\u0627\u0646\u0641\u06cc\u06af: <b>{count}</b>\n"
            "\U0001f9ea \u067e\u0631\u0648\u062a\u06a9\u0644: <b>VLESS / WS</b>\n"
            "\U0001f50c \u067e\u0648\u0631\u062a\u200c\u0647\u0627: <b>{ports}</b>\n"
            "\U0001f4f6 \u0627\u067e\u0631\u0627\u062a\u0648\u0631: <b>{operator}</b>\n"
            "\U0001f310 \u0645\u06cc\u0632\u0628\u0627\u0646: <code>{host}</code>\n\n"
            "\U0001f4a1 \u062f\u0631 \u06a9\u0644\u0627\u06cc\u0646\u062a <b>Real Delay</b> \u0628\u06af\u06cc\u0631 \u0648 \u0633\u0631\u06cc\u0639\u200c\u062a\u0631\u06cc\u0646 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646.\n"
            "\U0001f525 \u06af\u0632\u06cc\u0646\u0647 <b>Fragment</b> \u0631\u0627 \u0631\u0648\u0634\u0646 \u06a9\u0646 \u062a\u0627 \u067e\u0627\u06cc\u062f\u0627\u0631\u062a\u0631 \u0634\u0648\u062f."
        ),
        "en": (
            "\U0001f389 <b>Your panel is ready!</b> \U0001f680\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\u23f1 Build time: <b>{seconds}</b> s\n"
            "\U0001f3c6 Best ping: <b>{best}</b>\n"
            "\U0001f680 Under 700 ms: <b>{fast}</b> endpoints\n"
            "\U0001f4e6 Configs: <b>{count}</b>\n"
            "\U0001f9ea Protocol: <b>VLESS / WS</b>\n"
            "\U0001f50c Ports: <b>{ports}</b>\n"
            "\U0001f4f6 Operator: <b>{operator}</b>\n"
            "\U0001f310 Host: <code>{host}</code>\n\n"
            "\U0001f4a1 Run <b>Real Delay</b> in your client and pick the fastest entry.\n"
            "\U0001f525 Turn <b>Fragment</b> on for a steadier connection."
        ),
    },
    "panel_none": {
        "fa": "\U0001f4ed \u0647\u0646\u0648\u0632 \u067e\u0646\u0644\u06cc \u0646\u0633\u0627\u062e\u062a\u0647\u200c\u0627\u06cc. \u0627\u0632 \u062f\u06a9\u0645\u0647 \u00ab\u0633\u0627\u062e\u062a \u067e\u0646\u0644 \u062a\u0648\u0631\u0628\u0648\u00bb \u0634\u0631\u0648\u0639 \u06a9\u0646.",
        "en": "\U0001f4ed No panel yet. Start from \u201cBuild turbo panel\u201d.",
    },
    "panel_overview": {
        "fa": (
            "\U0001f39b <b>\u0645\u062f\u06cc\u0631\u06cc\u062a \u067e\u0646\u0644 \u0645\u0646</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\U0001f310 \u0645\u06cc\u0632\u0628\u0627\u0646: <code>{host}</code>\n"
            "\U0001f194 \u06cc\u0648\u0622\u06cc\u062f\u06cc: <code>{uuid}</code>\n"
            "\U0001f4e6 \u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627: <b>{count}</b>\n"
            "\U0001f3c6 \u0628\u0647\u062a\u0631\u06cc\u0646 \u067e\u06cc\u0646\u06af: <b>{best}</b>\n"
            "\U0001f504 \u0628\u0627\u0632\u0633\u0627\u0632\u06cc: <b>{rebuilds}</b>\n"
            "\U0001f552 \u0622\u062e\u0631\u06cc\u0646 \u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc: <b>{updated}</b>"
        ),
        "en": (
            "\U0001f39b <b>My panel</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\U0001f310 Host: <code>{host}</code>\n"
            "\U0001f194 UUID: <code>{uuid}</code>\n"
            "\U0001f4e6 Configs: <b>{count}</b>\n"
            "\U0001f3c6 Best ping: <b>{best}</b>\n"
            "\U0001f504 Rebuilds: <b>{rebuilds}</b>\n"
            "\U0001f552 Updated: <b>{updated}</b>"
        ),
    },
    "sub_links": {
        "fa": (
            "\U0001f517 <b>\u0644\u06cc\u0646\u06a9 \u0627\u0634\u062a\u0631\u0627\u06a9</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "<b>v2rayNG / Streisand / Nekobox</b>\n<code>{sub}</code>\n\n"
            "<b>Clash / Mihomo</b>\n<code>{clash}</code>\n\n"
            "<b>sing-box</b>\n<code>{singbox}</code>\n\n"
            "\u267b\ufe0f \u0644\u06cc\u0646\u06a9 \u062b\u0627\u0628\u062a \u0627\u0633\u062a\u061b \u0628\u0639\u062f \u0627\u0632 \u0647\u0631 \u0628\u0627\u0632\u0633\u0627\u0632\u06cc \u062e\u0648\u062f\u0628\u0647\u200c\u062e\u0648\u062f \u0628\u0647\u200c\u0631\u0648\u0632 \u0645\u06cc\u200c\u0634\u0648\u062f."
        ),
        "en": (
            "\U0001f517 <b>Subscription links</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "<b>v2rayNG / Streisand / Nekobox</b>\n<code>{sub}</code>\n\n"
            "<b>Clash / Mihomo</b>\n<code>{clash}</code>\n\n"
            "<b>sing-box</b>\n<code>{singbox}</code>\n\n"
            "\u267b\ufe0f The link is permanent and refreshes itself after every rebuild."
        ),
    },
    "ping_result": {
        "fa": "\U0001f4e1 <b>\u062a\u0633\u062a \u067e\u06cc\u0646\u06af \u0632\u0646\u062f\u0647</b>\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n{rows}\n\n\u2139\ufe0f \u0627\u06cc\u0646 \u0639\u062f\u062f\u0647\u0627 \u0627\u0632 \u0633\u0631\u0648\u0631 \u0631\u0628\u0627\u062a \u0627\u0646\u062f\u0627\u0632\u0647\u200c\u06af\u06cc\u0631\u06cc \u0634\u062f\u0647\u060c \u067e\u06cc\u0646\u06af \u062e\u0648\u062f\u062a \u0631\u0627 \u062f\u0631 \u06a9\u0644\u0627\u06cc\u0646\u062a \u0628\u06af\u06cc\u0631.",
        "en": "\U0001f4e1 <b>Live ping test</b>\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n{rows}\n\n\u2139\ufe0f Measured from the bot server. Check real delay in your own client too.",
    },
    "delete_confirm": {
        "fa": "\U0001f5d1 \u0645\u0637\u0645\u0626\u0646\u06cc\u061f \u0648\u0631\u06a9\u0631 <code>{script}</code> \u0627\u0632 \u0627\u06a9\u0627\u0646\u062a \u06a9\u0644\u0627\u062f\u0641\u0644\u0631 \u062a\u0648 \u067e\u0627\u06a9 \u0645\u06cc\u200c\u0634\u0648\u062f \u0648 \u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627 \u0627\u0632 \u06a9\u0627\u0631 \u0645\u06cc\u200c\u0627\u0641\u062a\u0646\u062f.",
        "en": "\U0001f5d1 Are you sure? The Worker <code>{script}</code> will be removed from your Cloudflare account and the configs will stop working.",
    },
    "deleted": {"fa": "\u2705 \u067e\u0646\u0644 \u062d\u0630\u0641 \u0634\u062f.", "en": "\u2705 Panel deleted."},
    "rebuilding": {"fa": "\u267b\ufe0f \u062f\u0627\u0631\u0645 \u0622\u06cc\u200c\u067e\u06cc\u200c\u0647\u0627\u06cc \u062a\u0627\u0632\u0647 \u0631\u0627 \u0633\u0648\u0627\u0631 \u0645\u06cc\u200c\u06a9\u0646\u0645...", "en": "\u267b\ufe0f Mounting fresh clean IPs..."},
    "token_missing": {
        "fa": "\U0001f511 \u0628\u0631\u0627\u06cc \u0627\u06cc\u0646 \u06a9\u0627\u0631 \u0628\u0627\u06cc\u062f \u062f\u0648\u0628\u0627\u0631\u0647 \u062a\u0648\u06a9\u0646 \u06a9\u0644\u0627\u062f\u0641\u0644\u0631\u062a \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc. \u0647\u0645\u06cc\u0646 \u0627\u0644\u0627\u0646 \u0628\u0641\u0631\u0633\u062a.",
        "en": "\U0001f511 I need your Cloudflare token again for this. Send it now.",
    },
    "scan_started": {"fa": "\u26a1 \u0627\u0633\u06a9\u0646 \u062a\u0627\u0632\u0647 \u0634\u0631\u0648\u0639 \u0634\u062f\u060c \u0686\u0646\u062f \u062b\u0627\u0646\u06cc\u0647 \u0635\u0628\u0631 \u06a9\u0646...", "en": "\u26a1 A fresh scan started, give it a few seconds..."},
    # ---------------------------------------------------------------- info
    "network_status": {
        "fa": (
            "\U0001f4ca <b>\u0648\u0636\u0639\u06cc\u062a \u0632\u0646\u062f\u0647 \u0634\u0628\u06a9\u0647</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\U0001f4e1 \u0627\u0633\u062a\u062e\u0631 \u0622\u06cc\u200c\u067e\u06cc: <b>{total}</b>\n"
            "\u2705 \u062a\u0627\u06cc\u06cc\u062f\u0634\u062f\u0647: <b>{verified}</b>\n"
            "\U0001f680 \u0632\u06cc\u0631 \u06f7\u06f0\u06f0ms: <b>{fast}</b>\n"
            "\U0001f3c6 \u0628\u0647\u062a\u0631\u06cc\u0646 \u067e\u06cc\u0646\u06af: <b>{best}</b>\n"
            "\U0001f50c \u067e\u0648\u0631\u062a\u200c\u0647\u0627\u06cc \u0641\u0639\u0627\u0644: <b>{ports}</b>\n"
            "\u23f3 \u0622\u062e\u0631\u06cc\u0646 \u0627\u0633\u06a9\u0646: <b>{updated}</b>\n"
            "\u2699\ufe0f \u0648\u0636\u0639\u06cc\u062a: <b>{state}</b>\n\n"
            "\U0001f4cd \u0645\u062d\u0628\u0648\u0628\u200c\u062a\u0631\u06cc\u0646 \u062f\u06cc\u062a\u0627\u0633\u0646\u062a\u0631\u0647\u0627: {colos}"
        ),
        "en": (
            "\U0001f4ca <b>Live network status</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\U0001f4e1 IP pool: <b>{total}</b>\n"
            "\u2705 Verified: <b>{verified}</b>\n"
            "\U0001f680 Under 700 ms: <b>{fast}</b>\n"
            "\U0001f3c6 Best ping: <b>{best}</b>\n"
            "\U0001f50c Active ports: <b>{ports}</b>\n"
            "\u23f3 Last scan: <b>{updated}</b>\n"
            "\u2699\ufe0f State: <b>{state}</b>\n\n"
            "\U0001f4cd Top datacenters: {colos}"
        ),
    },
    "apps": {
        "fa": (
            "\U0001f4f1 <b>\u0628\u0631\u0646\u0627\u0645\u0647\u200c\u0647\u0627 \u0648 \u0644\u06cc\u0646\u06a9 \u062f\u0627\u0646\u0644\u0648\u062f</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\u2022 <b>\u0627\u0646\u062f\u0631\u0648\u06cc\u062f:</b> v2rayNG \u060c NekoBox \u060c Hiddify\n"
            "\u2022 <b>\u0622\u06cc\u200c\u0627\u0648\u200c\u0627\u0633:</b> Streisand \u060c Shadowrocket \u060c FoXray\n"
            "\u2022 <b>\u0648\u06cc\u0646\u062f\u0648\u0632:</b> v2rayN \u060c Hiddify \u060c Nekoray\n"
            "\u2022 <b>\u0645\u06a9:</b> V2Box \u060c Streisand \u060c Hiddify\n\n"
            "\U0001f4a1 \u0644\u06cc\u0646\u06a9 \u0627\u0634\u062a\u0631\u0627\u06a9 \u0631\u0627 \u062f\u0631 \u0628\u062e\u0634 Subscription \u0628\u0631\u0646\u0627\u0645\u0647 \u0648\u0627\u0631\u062f \u06a9\u0646\u060c \u0646\u0647 \u062f\u0631 \u0628\u062e\u0634 \u06a9\u0627\u0646\u0641\u06cc\u06af \u062f\u0633\u062a\u06cc."
        ),
        "en": (
            "\U0001f4f1 <b>Apps and downloads</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\u2022 <b>Android:</b> v2rayNG, NekoBox, Hiddify\n"
            "\u2022 <b>iOS:</b> Streisand, Shadowrocket, FoXray\n"
            "\u2022 <b>Windows:</b> v2rayN, Hiddify, Nekoray\n"
            "\u2022 <b>macOS:</b> V2Box, Streisand, Hiddify\n\n"
            "\U0001f4a1 Paste the subscription link into the app's Subscription section, not the manual config field."
        ),
    },
    "guide": {
        "fa": (
            "\U0001f4d6 <b>\u0631\u0627\u0647\u0646\u0645\u0627\u06cc \u0627\u062a\u0635\u0627\u0644</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\u0031\ufe0f\u20e3 \u06cc\u06a9\u06cc \u0627\u0632 \u0628\u0631\u0646\u0627\u0645\u0647\u200c\u0647\u0627\u06cc \u0645\u0639\u0631\u0641\u06cc\u200c\u0634\u062f\u0647 \u0631\u0627 \u0646\u0635\u0628 \u06a9\u0646.\n"
            "\u0032\ufe0f\u20e3 \u0644\u06cc\u0646\u06a9 \u0627\u0634\u062a\u0631\u0627\u06a9 \u0631\u0627 \u062f\u0631 \u0628\u062e\u0634 Subscription \u0627\u0636\u0627\u0641\u0647 \u06a9\u0646 \u0648 Update \u0628\u0632\u0646.\n"
            "\u0033\ufe0f\u20e3 Real Delay \u06cc\u0627 \u062a\u0633\u062a \u062a\u0627\u062e\u06cc\u0631 \u0631\u0627 \u0628\u06af\u06cc\u0631 \u0648 \u0633\u0631\u06cc\u0639\u200c\u062a\u0631\u06cc\u0646 \u06a9\u0627\u0646\u0641\u06cc\u06af \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646.\n