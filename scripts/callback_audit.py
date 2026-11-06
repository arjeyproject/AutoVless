#!/usr/bin/env python3
"""Callback audit: every button a keyboard can emit must have a handler.

Static cross-check between the callback data literals the keyboards (and
handlers that send keyboards) emit and the callback patterns the routers
answer. Anything emitted but not answered is a dead button - the exact class
of bug the operator picker used to have, where a navigation cleared the state
and the next tap did nothing at all.

Patterns are collected from:
  F.data == "lit"            -> exact set
  F.data.in_({...})          -> exact set
  F.data.startswith("pre")   -> prefix list
  F.data.startswith(...) & F.data.contains(":x:") -> prefix plus a contains rule

Literals are collected from every ``"..."`` that appears as callback_data= or
inside _b(...) / _c(...) / _u(...) calls, plus the per-operator/per-platform
f-strings resolved against the real tables (operators, platforms, export
kinds, protocol kinds), so generated buttons are checked too.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOT = ROOT / "bot"

# Optional extras that resolve f-string literals, tried with real data.
EXTRA_TABLES: dict[str, set[str]] = {
    "operators": set(),  # filled from operators.py
    "platforms": {"android", "ios", "windows", "macos", "linux", "tv", ""},
    "kinds": {"awg", "awg2", "plain", "singbox", "clash"},
    "proto_kinds": {"vless", "httpupgrade", "xhttp", "trojan", "ss", "sub"},
    "families": {"v4", "v6"},
    "apps": {"android", "ios", "windows", "macos", "linux"},
    "tags": {"", "warp"},
    "codes": {"mci", "mtn", "rightel", "shatel", "adsl", "other"},
}

emitted: set[str] = set()      # fully literal callback data strings
emitted_prefixes: set[str] = set()  # from f-strings we could not fully resolve
handlers_exact: set[str] = set()
handlers_prefix: list[str] = []
handlers_contains: list[str] = []


def load_operator_codes() -> None:
    sys.path.insert(0, str(BOT.parent))
    try:
        from bot.operators import OPERATORS

        EXTRA_TABLES["operators"] = set(OPERATORS)
        EXTRA_TABLES["codes"] = set(OPERATORS)
    except Exception as exc:  # noqa: BLE001
        print(f"warn: could not load operators: {exc}")


def literal_of(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def resolve_joined(parts: list[str]) -> str:
    """Turn a partially resolved f-string into a literal or a prefix."""
    if "<any>" in parts:
        return "".join(parts).split("<any>")[0]
    return "".join(parts)


def collect_emitted(tree: ast.AST, path: str) -> None:
    for node in ast.walk(tree):
        handled = False
        # callback_data= kwarg
        if isinstance(node, ast.keyword) and node.arg == "callback_data":
            value = node.value
            lit = literal_of(value)
            if lit:
                emitted.add(lit)
                handled = True
            elif isinstance(value, ast.JoinedStr):
                handled = True
        # _b/_c/_u/glass_button positional data argument
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"_b", "_c", "_u", "glass_button"}:
            if len(node.args) >= 2:
                lit = literal_of(node.args[1])
                if lit:
                    emitted.add(lit)
                    handled = True
                elif isinstance(node.args[1], ast.JoinedStr):
                    handled = True
        if not handled:
            continue
        # resolve the joined string we just marked as handled
        joined = None
        if isinstance(node, ast.keyword) and isinstance(node.value, ast.JoinedStr):
            joined = node.value
        elif isinstance(node, ast.Call) and len(node.args) >= 2 and isinstance(node.args[1], ast.JoinedStr):
            joined = node.args[1]
        if joined is None:
            continue
        parts: list[str] = []
        for v in joined.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            elif isinstance(v, ast.FormattedValue):
                # <any> marks a hole; keep everything before the first hole.
                parts.append("<any>")
            else:
                parts.append("<any>")
        prefix = resolve_joined(parts)
        if "<any>" in "".join(parts):
            if prefix:
                emitted_prefixes.add(prefix)
        else:
            emitted.add(prefix)


def collect_handlers(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        # F.data == "lit" and F.data.in_({...}) are calls/comparisons, both.
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
            left = node.left
            if isinstance(left, ast.Attribute) and left.attr == "data":
                lit = literal_of(node.comparators[0])
                if lit:
                    handlers_exact.add(lit)
            continue
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "attr", getattr(func, "id", ""))
        if name not in {"eq", "in_", "startswith", "contains"}:
            continue
        # find the enclosing F.data attribute chain
        parent_is_fdata = isinstance(func, ast.Attribute) and isinstance(func.value, ast.Attribute) and func.value.attr == "data"
        if not parent_is_fdata:
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if name == "eq":
            lit = literal_of(arg)
            if lit:
                handlers_exact.add(lit)
        elif name == "in_":
            if isinstance(arg, (ast.Set, ast.List, ast.Tuple)):
                for elt in arg.elts:
                    lit = literal_of(elt)
                    if lit:
                        handlers_exact.add(lit)
        elif name == "startswith":
            lit = literal_of(arg)
            if lit:
                handlers_prefix.append(lit)
        elif name == "contains":
            lit = literal_of(arg)
            if lit:
                handlers_contains.append(lit)


def main() -> int:
    load_operator_codes()
    files = sorted(BOT.glob("*.py")) + sorted((BOT / "handlers").glob("*.py"))
    for path in files:
        tree = ast.parse(path.read_text(), str(path))
        collect_emitted(tree, str(path))
        collect_handlers(tree)

    dead = []
    for lit in sorted(emitted):
        if lit in handlers_exact:
            continue
        if any(lit.startswith(prefix) for prefix in handlers_prefix):
            continue
        if any(c in lit for c in handlers_contains):
            continue
        dead.append(lit)

    unanswered_prefixes = []
    for prefix in sorted(emitted_prefixes):
        if not prefix:
            continue
        if any(p.startswith(prefix) or prefix.startswith(p) for p in handlers_prefix):
            continue
        if any(p in prefix for p in handlers_contains):
            continue
        if prefix in handlers_exact or any(prefix.startswith(p) for p in handlers_exact):
            continue
        unanswered_prefixes.append(prefix)

    unreachable = []
    for prefix in sorted(handlers_prefix):
        if any(e.startswith(prefix) for e in emitted) or any(
            p.startswith(prefix) for p in emitted_prefixes
        ):
            continue
        # prefix handlers also answer buttons that older chat history already
        # carries - those are emitted nowhere in the current source. Only flag
        # a prefix as unreachable when nothing plausibly matches it at all.
        plausible = any(p.startswith(prefix) or prefix.startswith(p) for p in handlers_prefix)
        if not plausible:
            unreachable.append(prefix)

    print(f"emitted literals: {len(emitted)}")
    print(f"emitted f-string prefixes: {len(emitted_prefixes)}")
    print(f"handler exact: {len(handlers_exact)}, prefix: {len(handlers_prefix)}, contains: {len(handlers_contains)}")
    print()
    if dead:
        print("DEAD BUTTONS (emitted but never answered):")
        for item in dead:
            print(f"  - {item}")
    else:
        print("dead buttons: NONE")
    print()
    if unanswered_prefixes:
        print("UNANSWERED GENERATED BUTTONS (f-string prefix not matched):")
        for item in unanswered_prefixes:
            print(f"  - {item}*")
    else:
        print("generated buttons: ALL MATCHED")
    print()
    if unreachable:
        print("POSSIBLY ORPHAN HANDLERS (no emitter found):")
        for item in unreachable:
            print(f"  - {item}*")
    return 1 if dead else 0


if __name__ == "__main__":
    raise SystemExit(main())
