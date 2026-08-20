"""Iranian operator profiles: display names and connection advice."""

from __future__ import annotations

OPERATORS: dict[str, dict[str, str]] = {
    "mci": {
        "fa": "\u0647\u0645\u0631\u0627\u0647 \u0627\u0648\u0644",
        "en": "MCI",
        "tip_fa": "\u067e\u0648\u0631\u062a \u06f4\u06f4\u06f3 \u0631\u0627 \u0627\u0648\u0644 \u0627\u0645\u062a\u062d\u0627\u0646 \u06a9\u0646 \u0648 Fragment \u0631\u0627 \u0631\u0648\u06cc \u062d\u0627\u0644\u062a tlshello \u0628\u06af\u0630\u0627\u0631.",
        "tip_en": "Start with port 443 and set Fragment to tlshello.",
    },
    "mtn": {
        "fa": "\u0627\u06cc\u0631\u0627\u0646\u0633\u0644",
        "en": "Irancell",
        "tip_fa": "\u067e\u0648\u0631\u062a \u06f8\u06f0 \u0627\u063a\u0644\u0628 \u067e\u0627\u06cc\u062f\u0627\u0631\u062a\u0631 \u0627\u0633\u062a\u061b \u0627\u06af\u0631 \u0642\u0637\u0639 \u0634\u062f \u0628\u0647 \u067e\u0648\u0631\u062a \u06f4\u06f4\u06f3 \u0628\u0631\u06af\u0631\u062f.",
        "tip_en": "Port 80 is usually steadier here; fall back to 443 if it drops.",
    },
    "rightel": {
        "fa": "\u0631\u0627\u06cc\u062a\u0644",
        "en": "Rightel",
        "tip_fa": "MTU \u0631\u0627 \u0631\u0648\u06cc \u06f1\u06f2\u06f8\u06f0 \u0628\u06af\u0630\u0627\u0631 \u0648 \u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627\u06cc \u067e\u0648\u0631\u062a \u06f8\u06f0 \u0631\u0627 \u062a\u0631\u062c\u06cc\u062d \u0628\u062f\u0647.",
        "tip_en": "Set MTU to 1280 and prefer the port 80 configs.",
    },
    "shatel": {
        "fa": "\u0634\u0627\u062a\u0644 \u0645\u0648\u0628\u0627\u06cc\u0644",
        "en": "Shatel Mobile",
        "tip_fa": "\u067e\u0648\u0631\u062a \u06f4\u06f4\u06f3 \u0628\u0627 Fragment \u0631\u0648\u0634\u0646 \u0628\u0647\u062a\u0631\u06cc\u0646 \u0646\u062a\u06cc\u062c\u0647 \u0631\u0627 \u0645\u06cc\u200c\u062f\u0647\u062f.",
        "tip_en": "Port 443 with Fragment enabled works best.",
    },
    "adsl": {
        "fa": "\u0645\u062e\u0627\u0628\u0631\u0627\u062a / ADSL",
        "en": "Fixed line / ADSL",
        "tip_fa": "\u067e\u0648\u0631\u062a \u06f4\u06f4\u06f3 \u0648 DNS \u0631\u0627 \u0631\u0648\u06cc \u06f1.\u06f1.\u06f1.\u06f1 \u0628\u06af\u0630\u0627\u0631.",
        "tip_en": "Use port 443 and point DNS at 1.1.1.1.",
    },
    "other": {
        "fa": "\u0633\u0627\u06cc\u0631",
        "en": "Other",
        "tip_fa": "\u0647\u0631 \u0634\u0634 \u06a9\u0627\u0646\u0641\u06cc\u06af \u0631\u0627 \u062a\u0633\u062a \u06a9\u0646 \u0648 \u0633\u0631\u06cc\u0639\u200c\u062a\u0631\u06cc\u0646 \u0631\u0627 \u0646\u06af\u0647 \u062f\u0627\u0631.",
        "tip_en": "Test all six configs and keep the fastest one.",
    },
}


def label(code: str | None, lang: str) -> str:
    profile = OPERATORS.get(code or "")
    if not profile:
        return ""
    return profile["en" if lang == "en" else "fa"]


def tip(code: str | None, lang: str) -> str:
    profile = OPERATORS.get(code or "other", OPERATORS["other"])
    return profile["tip_en" if lang == "en" else "tip_fa"]
