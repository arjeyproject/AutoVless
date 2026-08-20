"""Translation lookup. Persian is the default, English is a full peer."""

from __future__ import annotations

from typing import Any

from .locales.admin import ADMIN
from .locales.en import EN
from .locales.fa import FA

LANGS: tuple[str, ...] = ("fa", "en")
RULE = "\u2501" * 14

CATALOG: dict[str, dict[str, str]] = {
    "fa": {**FA, **ADMIN["fa"]},
    "en": {**EN, **ADMIN["en"]},
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
