"""Iranian operator profiles: display names and connection advice.

Each profile also carries a WireGuard layer (``wg_ports``, ``wg_mtu``,
``wg_family``) used by ``warpops`` when it ranks the endpoint pool for one
operator's users, and by the config renderer when the pro settings leave the
MTU on auto. The ports are the Cloudflare ranges those carriers are widely
reported to pass without throttling; learned wins from real benchmarks always
take precedence over these priors once evidence accumulates.
"""

from __future__ import annotations

# Cloudflare HTTPS-range ports vs HTTP-range ports, used to build per-operator
# port sets without repeating them in every profile.
TLS_PORTS = (443, 2053, 2083, 2087, 2096, 8443)
HTTP_PORTS = (80, 8080, 8880, 2052, 2082, 2086, 2095)

OPERATORS: dict[str, dict[str, object]] = {
    "mci": {
        "fa": "\u0647\u0645\u0631\u0627\u0647 \u0627\u0648\u0644",
        "en": "MCI",
        "tip_fa": "\u067e\u0648\u0631\u062a \u06f4\u06f4\u06f3 \u0631\u0627 \u0627\u0648\u0644 \u0627\u0645\u062a\u062d\u0627\u0646 \u06a9\u0646 \u0648 Fragment \u0631\u0627 \u0631\u0648\u06cc \u062d\u0627\u0644\u062a tlshello \u0628\u06af\u0630\u0627\u0631.",
        "tip_en": "Start with port 443 and set Fragment to tlshello.",
        "wg_ports": (443, 2053, 2087, 80, 2052),
        "wg_mtu": 1420,
        "wg_family": "v4",
    },
    "mtn": {
        "fa": "\u0627\u06cc\u0631\u0627\u0646\u0633\u0644",
        "en": "Irancell",
        "tip_fa": "\u067e\u0648\u0631\u062a \u06f8\u06f0 \u0627\u063a\u0644\u0628 \u067e\u0627\u06cc\u062f\u0627\u0631\u062a\u0631 \u0627\u0633\u062a\u061b \u0627\u06af\u0631 \u0642\u0637\u0639 \u0634\u062f \u0628\u0647 \u067e\u0648\u0631\u062a \u06f4\u06f4\u06f3 \u0628\u0631\u06af\u0631\u062f.",
        "tip_en": "Port 80 is usually steadier here; fall back to 443 if it drops.",
        "wg_ports": (80, 8880, 2052, 443, 2053),
        "wg_mtu": 1380,
        "wg_family": "v6",
    },
    "rightel": {
        "fa": "\u0631\u0627\u06cc\u062a\u0644",
        "en": "Rightel",
        "tip_fa": "MTU \u0631\u0627 \u0631\u0648\u06cc \u06f1\u06f2\u06f8\u06f0 \u0628\u06af\u0630\u0627\u0631 \u0648 \u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627\u06cc \u067e\u0648\u0631\u062a \u06f8\u06f0 \u0631\u0627 \u062a\u0631\u062c\u06cc\u062d \u0628\u062f\u0647.",
        "tip_en": "Set MTU to 1280 and prefer the port 80 configs.",
        "wg_ports": (80, 2052, 8080, 443),
        "wg_mtu": 1280,
        "wg_family": "v4",
    },
    "shatel": {
        "fa": "\u0634\u0627\u062a\u0644 \u0645\u0648\u0628\u0627\u06cc\u0644",
        "en": "Shatel Mobile",
        "tip_fa": "\u067e\u0648\u0631\u062a \u06f4\u06f4\u06f3 \u0628\u0627 Fragment \u0631\u0648\u0634\u0646 \u0628\u0647\u062a\u0631\u06cc\u0646 \u0646\u062a\u06cc\u062c\u0647 \u0631\u0627 \u0645\u06cc\u200c\u062f\u0647\u062f.",
        "tip_en": "Port 443 with Fragment enabled works best.",
        "wg_ports": (443, 2053, 2083, 80),
        "wg_mtu": 1420,
        "wg_family": "v4",
    },
    "adsl": {
        "fa": "\u0645\u062e\u0627\u0628\u0631\u0627\u062a / ADSL",
        "en": "Fixed line / ADSL",
        "tip_fa": "\u067e\u0648\u0631\u062a \u06f4\u06f4\u06f3 \u0648 DNS \u0631\u0627 \u0631\u0648\u06cc \u06f1.\u06f1.\u06f1.\u06f1 \u0628\u06af\u0630\u0627\u0631.",
        "tip_en": "Use port 443 and point DNS at 1.1.1.1.",
        "wg_ports": (443, 2053, 2096, 8443),
        "wg_mtu": 1420,
        "wg_family": "v4",
    },
    "other": {
        "fa": "\u0633\u0627\u06cc\u0631",
        "en": "Other",
        "tip_fa": "\u0647\u0631 \u0634\u0634 \u06a9\u0627\u0646\u0641\u06cc\u06af \u0631\u0627 \u062a\u0633\u062a \u06a9\u0646 \u0648 \u0633\u0631\u06cc\u0639\u200c\u062a\u0631\u06cc\u0646 \u0631\u0627 \u0646\u06af\u0647 \u062f\u0627\u0631.",
        "tip_en": "Test all six configs and keep the fastest one.",
        "wg_ports": TLS_PORTS + HTTP_PORTS,
        "wg_mtu": 1420,
        "wg_family": "v4",
    },
}


def label(code: str | None, lang: str) -> str:
    profile = OPERATORS.get(code or "")
    if not profile:
        return ""
    return str(profile["en" if lang == "en" else "fa"])


def tip(code: str | None, lang: str) -> str:
    profile = OPERATORS.get(code or "other", OPERATORS["other"])
    return str(profile["tip_en" if lang == "en" else "tip_fa"])


def wg_profile(code: str | None) -> dict[str, object]:
    """The WireGuard layer of one operator, with safe defaults for unknowns."""
    profile = OPERATORS.get(code or "other", OPERATORS["other"])
    ports = profile.get("wg_ports") or (TLS_PORTS + HTTP_PORTS)
    return {
        "ports": tuple(int(p) for p in ports),
        "mtu": int(profile.get("wg_mtu") or 1420),
        "family": str(profile.get("wg_family") or "v4"),
        "ipv6_ok": str(profile.get("wg_family") or "v4") == "v6",
    }
