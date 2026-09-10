"""Translation lookup. Persian is the default, English is a full peer."""

from __future__ import annotations

from typing import Any

from .locales.admin import ADMIN
from .locales.ai import AI
from .locales.apps import APPS
from .locales.curator import CURATOR
from .locales.device import DEVICE
from .locales.en import EN
from .locales.fa import FA
from .locales.proton import PROTON_STRINGS
from .locales.support import SUPPORT
from .locales.warp import WARP
from .locales.warpmanual import WARPMANUAL
from .locales.warppool import WARPPOOL

LANGS: tuple[str, ...] = ("fa", "en")
RULE = "\u2501" * 14

# WARPPOOL is merged after WARP so the pool screens can override an older WARP
# string without editing that catalogue, and WARPMANUAL comes after it for the
# same reason: the hand entry screens own their wording. DEVICE is merged last of
# the WARP family because the device picker owns anything it names - including
# ``warp.select_platform``, which had no entry anywhere and was rendering its own
# key as the screen body. AI and Proton come at the end.
CATALOG: dict[str, dict[str, str]] = {
    "fa": {
        **FA,
        **ADMIN["fa"],
        **CURATOR["fa"],
        **SUPPORT["fa"],
        **WARP["fa"],
        **APPS["fa"],
        **WARPPOOL["fa"],
        **WARPMANUAL["fa"],
        **DEVICE["fa"],
        **AI["fa"],
        **PROTON_STRINGS.get("fa", {}),
    },
    "en": {
        **EN,
        **ADMIN["en"],
        **CURATOR["en"],
        **SUPPORT["en"],
        **WARP["en"],
        **APPS["en"],
        **WARPPOOL["en"],
        **WARPMANUAL["en"],
        **DEVICE["en"],
        **AI["en"],
        **PROTON_STRINGS.get("en", {}),
    },
}

_PERSIAN_DIGITS = str.maketrans(
    "0123456789", "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9"
)


def normalise(lang: str | None) -> str:
    lang = (lang or "fa").lower()
    return lang if lang in LANGS else "fa"


def num(value: Any, lang: str) -> str:
    """Render digits in the reader's own numerals."""
    text = str(value)
    return text.translate(_PERSIAN_DIGITS) if normalise(lang) == "fa" else text


def t(lang: str, key: str, **kwargs: Any) -> str:
    """Look up a key, falling back to Persian and then to the key itself."""
    lang = normalise(lang)
    template = CATALOG[lang].get(key) or CATALOG["fa"].get(key) or key
    if not kwargs and "{rule}" not in template:
        return template
    try:
        return template.format(rule=RULE, **kwargs)
    except (KeyError, IndexError, ValueError):
        return template


def other_lang(lang: str) -> str:
    return "en" if normalise(lang) == "fa" else "fa"


def device_label(platform: str, lang: str) -> str:
    """The picker button's text, reused as a plain device name in messages."""
    from .platforms import label_key, normalise_platform

    return t(lang, label_key(normalise_platform(platform)))
