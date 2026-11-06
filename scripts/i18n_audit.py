#!/usr/bin/env python3
"""i18n audit: every t(lang, "key") call must resolve to a real string.

A missing key renders as the raw key on screen, which reads exactly like a
broken bot. This walks every ``t(lang, "...")`` and ``T("...")`` literal in the
bot and the mini app, plus the dynamic ``f"prefix_{x}"`` families, and checks
each against the merged catalogues.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.i18n import CATALOG  # noqa: E402


def collect_calls(path: Path, func_names: set[str]) -> list[tuple[int, str, bool]]:
    """(line, key, is_dynamic) tuples from every literal call."""
    out: list[tuple[int, str, bool]] = []
    tree = ast.parse(path.read_text(), str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", getattr(func, "attr", ""))
        if name not in func_names or not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            out.append((node.lineno, arg.value, False))
        elif isinstance(arg, ast.JoinedStr):
            # f"pro.mtu_{mtu}" -> dynamic prefix "pro.mtu_"
            parts = []
            for v in arg.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    parts.append(v.value)
                else:
                    parts.append("\0")
            out.append((node.lineno, "".join(parts), True))
    return out


def known_prefix(key: str) -> bool:
    """A dynamic key counts as known when at least one real key starts with it."""
    return any(real.startswith(key) for real in catalog_all)


catalog_all: set[str] = set()


def main() -> int:
    global catalog_all
    catalog_all = set(CATALOG["fa"]) | set(CATALOG["en"])
    missing: list[str] = []

    for path in sorted((ROOT / "bot" / "bot").glob("*.py")) if False else sorted((ROOT / "bot").rglob("*.py")):
        if path.name.startswith("locales"):
            continue
        for line, key, dynamic in collect_calls(path, {"t"}):
            if "\0" in key:
                if not known_prefix(key):
                    missing.append(f"{path.name}:{line} DYNAMIC {key!r}")
            elif key not in catalog_all:
                missing.append(f"{path.name}:{line} {key!r}")

    # The mini app: T("key") literals against the keys the file's own STR
    # catalogue defines. app.js is JavaScript, so a regex does this instead of
    # the AST; the fa object is line "STR.fa = {" and en merges after it.
    import re

    js = (ROOT / "webapp" / "app.js").read_text()
    js_keys: set[str] = set()
    for line in js.splitlines():
        if "STR." not in line and '"warp.op_mci"' not in line:
            continue
        for match in re.finditer(r'[,{]\s*(?:"([^"]+)"|([A-Za-z_.][\w.]*))\s*:', line):
            js_keys.add(match.group(1) or match.group(2))
    for match in re.finditer(r'\bT\(\s*"([^"]+)"\s*\)', js):
        key = match.group(1)
        if key not in js_keys:
            missing.append(f"app.js:{match.start()} {key!r}")

    if missing:
        print("MISSING KEYS:")
        for item in missing:
            print(f"  - {item}")
        return 1
    print("i18n audit: all keys resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
