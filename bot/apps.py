"""Client app catalogue.

Every entry is a real, tappable destination: a Google Play page, an App Store
page, or the project's release page on GitHub. Nothing here is a search result
or a mirror, because a download link that lands somewhere unexpected is worse
than no link at all.

``tag`` says what the app is actually good for, so the WARP screen can offer the
subset that understands AmneziaWG instead of the whole list.
"""

from __future__ import annotations

from typing import Iterable

PLATFORMS: tuple[str, ...] = ("android", "ios", "windows", "macos", "linux")

STORE_MARKS: dict[str, str] = {
    "play": "\u25b6\ufe0f",
    "appstore": "\uf8ff",
    "github": "\U0001f419",
    "web": "\U0001f310",
}

# tag: "vless" for panel configs, "warp" for WireGuard/AmneziaWG, "both" for both
CATALOGUE: dict[str, tuple[dict, ...]] = {
    "android": (
        {
            "name": "v2rayNG",
            "store": "play",
            "url": "https://play.google.com/store/apps/details?id=com.v2ray.ang",
            "tag": "vless",
            "best": True,
        },
        {
            "name": "Hiddify",
            "store": "play",
            "url": "https://play.google.com/store/apps/details?id=app.hiddify.com",
            "tag": "both",
            "best": True,
        },
        {
            "name": "NekoBox",
            "store": "play",
            "url": "https://play.google.com/store/apps/details?id=io.nekohasekai.sagernet",
            "tag": "vless",
        },
        {
            "name": "v2rayNG (APK)",
            "store": "github",
            "url": "https://github.com/2dust/v2rayNG/releases/latest",
            "tag": "vless",
        },
        {
            "name": "AmneziaVPN",
            "store": "play",
            "url": "https://play.google.com/store/apps/details?id=org.amnezia.vpn",
            "tag": "warp",
            "best": True,
        },
        {
            "name": "WG Tunnel",
            "store": "play",
            "url": (
                "https://play.google.com/store/apps/details"
                "?id=com.zaneschepke.wireguardautotunnel"
            ),
            "tag": "warp",
        },
    ),
    "ios": (
        {
            "name": "Streisand",
            "store": "appstore",
            "url": "https://apps.apple.com/app/streisand/id6450534064",
            "tag": "both",
            "best": True,
        },
        {
            "name": "Hiddify",
            "store": "appstore",
            "url": "https://apps.apple.com/app/hiddify-proxy-vpn/id6596777532",
            "tag": "both",
            "best": True,
        },
        {
            "name": "Shadowrocket",
            "store": "appstore",
            "url": "https://apps.apple.com/app/shadowrocket/id932747118",
            "tag": "vless",
        },
        {
            "name": "V2Box",
            "store": "appstore",
            "url": "https://apps.apple.com/us/search?term=v2box",
            "tag": "vless",
        },
        {
            "name": "FoXray",
            "store": "appstore",
            "url": "https://apps.apple.com/us/search?term=foxray",
            "tag": "vless",
        },
        {
            "name": "AmneziaVPN",
            "store": "appstore",
            "url": "https://apps.apple.com/us/search?term=amneziavpn",
            "tag": "warp",
        },
    ),
    "windows": (
        {
            "name": "v2rayN",
            "store": "github",
            "url": "https://github.com/2dust/v2rayN/releases/latest",
            "tag": "vless",
            "best": True,
        },
        {
            "name": "Hiddify",
            "store": "github",
            "url": "https://github.com/hiddify/hiddify-app/releases/latest",
            "tag": "both",
            "best": True,
        },
        {
            "name": "NekoRay",
            "store": "github",
            "url": "https://github.com/MatsuriDayo/nekoray/releases/latest",
            "tag": "vless",
        },
        {
            "name": "AmneziaVPN",
            "store": "github",
            "url": "https://github.com/amnezia-vpn/amnezia-client/releases/latest",
            "tag": "warp",
            "best": True,
        },
        {
            "name": "WireGuard",
            "store": "web",
            "url": "https://www.wireguard.com/install/",
            "tag": "warp",
        },
    ),
    "macos": (
        {
            "name": "Hiddify",
            "store": "github",
            "url": "https://github.com/hiddify/hiddify-app/releases/latest",
            "tag": "both",
            "best": True,
        },
        {
            "name": "Streisand",
            "store": "appstore",
            "url": "https://apps.apple.com/app/streisand/id6450534064",
            "tag": "both",
            "best": True,
        },
        {
            "name": "V2Box",
            "store": "appstore",
            "url": "https://apps.apple.com/us/search?term=v2box",
            "tag": "vless",
        },
        {
            "name": "sing-box",
            "store": "github",
            "url": "https://github.com/SagerNet/sing-box/releases/latest",
            "tag": "vless",
        },
        {
            "name": "AmneziaVPN",
            "store": "github",
            "url": "https://github.com/amnezia-vpn/amnezia-client/releases/latest",
            "tag": "warp",
        },
    ),
    "linux": (
        {
            "name": "Hiddify",
            "store": "github",
            "url": "https://github.com/hiddify/hiddify-app/releases/latest",
            "tag": "both",
            "best": True,
        },
        {
            "name": "NekoRay",
            "store": "github",
            "url": "https://github.com/MatsuriDayo/nekoray/releases/latest",
            "tag": "vless",
        },
        {
            "name": "sing-box",
            "store": "github",
            "url": "https://github.com/SagerNet/sing-box/releases/latest",
            "tag": "vless",
            "best": True,
        },
        {
            "name": "Mihomo (Clash)",
            "store": "github",
            "url": "https://github.com/MetaCubeX/mihomo/releases/latest",
            "tag": "vless",
        },
        {
            "name": "AmneziaVPN",
            "store": "github",
            "url": "https://github.com/amnezia-vpn/amnezia-client/releases/latest",
            "tag": "warp",
        },
    ),
}


def mark(store: str) -> str:
    return STORE_MARKS.get(store, "\U0001f4e5")


def listing(platform: str, tag: str = "") -> tuple[dict, ...]:
    """Apps for a platform, recommended ones first.

    ``tag`` narrows the list: "vless" for panel configs, "warp" for WireGuard.
    Entries marked for both always survive the filter.
    """
    items: Iterable[dict] = CATALOGUE.get(platform, ())
    if tag:
        items = [item for item in items if item["tag"] in {tag, "both"}]
    return tuple(sorted(items, key=lambda item: (not item.get("best"), item["name"].lower())))


def label(item: dict) -> str:
    """Button text: the app name is the thing people look for, so it leads."""
    star = " \u2b50" if item.get("best") else ""
    return f"{mark(item['store'])} {item['name']}{star}"


def count(platform: str, tag: str = "") -> int:
    return len(listing(platform, tag))
