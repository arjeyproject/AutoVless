#!/usr/bin/env python3
"""Register per-user credentials on the self-hosted sing-box node.

The free tier needs none of this: one shared server key means a new user costs
zero provisioning, which is what makes it automatic. Use this when you want
per-user credentials you can revoke one at a time.

Credentials are derived from the bot's own ``SECRET_KEY`` with the same HMAC as
``bot/selfhost.py``, so the node and the bot agree on every value without
sharing a database. Nothing is stored here that cannot be recomputed.

    sudo python3 scripts/selfhost-user.py list
    sudo python3 scripts/selfhost-user.py add 123456789
    sudo python3 scripts/selfhost-user.py remove 123456789

After the first ``add``, set ``SELFHOST_PER_USER=1`` in the bot's ``.env`` and
restart it, or the bot will keep handing out the shared credential.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import uuid as uuid_lib
from pathlib import Path

CONF = Path(os.getenv("SINGBOX_CONF", "/etc/sing-box/config.json"))
REPO = Path(__file__).resolve().parent.parent
KEY_BYTES = 16


def fail(message: str) -> "NoReturn":  # type: ignore[valid-type]
    print(f"!! {message}", file=sys.stderr)
    raise SystemExit(1)


def secret_key() -> str:
    """The same secret ``bot.config`` settles on, found the same way it does."""
    env = os.getenv("SECRET_KEY", "").strip()
    if env:
        return env
    dotenv = REPO / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("SECRET_KEY="):
                value = line.split("=", 1)[1].strip().strip("'\"")
                if value:
                    return value
    for candidate in (REPO / "data" / ".secret", Path("/opt/autovless/data/.secret")):
        if candidate.exists():
            value = candidate.read_text(encoding="utf-8").strip()
            if value:
                return value
    fail("could not find SECRET_KEY - export it, or run this from the bot's directory")


def digest(secret: str, label: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), label.encode("utf-8"), hashlib.sha256).digest()


def creds(secret: str, tg_id: int) -> tuple[str, str]:
    uid = str(uuid_lib.UUID(bytes=digest(secret, f"selfhost:vless:{tg_id}")[:16], version=4))
    psk = base64.b64encode(digest(secret, f"selfhost:ss:{tg_id}")[:KEY_BYTES]).decode("ascii")
    return uid, psk


def load_conf() -> dict:
    if not CONF.exists():
        fail(f"{CONF} not found - run scripts/install-selfhost.sh first")
    try:
        return json.loads(CONF.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"{CONF} is not valid json: {error}")


def inbound(conf: dict, kind: str) -> dict | None:
    for item in conf.get("inbounds") or []:
        if isinstance(item, dict) and item.get("type") == kind:
            return item
    return None


def save_conf(conf: dict) -> None:
    """Write, validate, restart. A config that fails ``check`` is rolled back."""
    backup = CONF.with_suffix(".json.bak")
    backup.write_text(CONF.read_text(encoding="utf-8"), encoding="utf-8")
    CONF.write_text(json.dumps(conf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    check = subprocess.run(
        ["sing-box", "check", "-c", str(CONF)], capture_output=True, text=True
    )
    if check.returncode != 0:
        CONF.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
        fail(f"sing-box rejected the new config, rolled back:\n{check.stderr.strip()}")
    restart = subprocess.run(
        ["systemctl", "restart", "sing-box"], capture_output=True, text=True
    )
    if restart.returncode != 0:
        fail(f"could not restart sing-box: {restart.stderr.strip()}")
    print("** config updated and sing-box restarted")


def cmd_list(_: argparse.Namespace) -> None:
    conf = load_conf()
    vless = inbound(conf, "vless") or {}
    shadow = inbound(conf, "shadowsocks") or {}
    print("vless users:")
    for user in vless.get("users") or []:
        print(f"  {user.get('name', '?'):<24} {user.get('uuid', '')}")
    print("shadowsocks users:")
    listed = shadow.get("users") or []
    if not listed:
        print("  (none - the shared server key is in use, which is the free tier)")
    for user in listed:
        print(f"  {user.get('name', '?')}")


def cmd_add(args: argparse.Namespace) -> None:
    tg_id = int(args.tg_id)
    name = str(tg_id)
    uid, psk = creds(secret_key(), tg_id)
    conf = load_conf()

    vless = inbound(conf, "vless")
    if vless is not None:
        users = [u for u in (vless.get("users") or []) if u.get("name") != name]
        users.append({"name": name, "uuid": uid, "flow": "xtls-rprx-vision"})
        vless["users"] = users

    shadow = inbound(conf, "shadowsocks")
    if shadow is not None:
        users = [u for u in (shadow.get("users") or []) if u.get("name") != name]
        users.append({"name": name, "password": psk})
        shadow["users"] = users

    save_conf(conf)
    print(f"** added {name}")
    print(f"   vless uuid : {uid}")
    print(f"   ss user key: {psk}")
    print("   the bot derives both from SECRET_KEY, so nothing to copy across")
    print("   set SELFHOST_PER_USER=1 in .env and restart the bot")


def cmd_remove(args: argparse.Namespace) -> None:
    name = str(int(args.tg_id))
    conf = load_conf()
    removed = False
    for kind in ("vless", "shadowsocks"):
        item = inbound(conf, kind)
        if item is None:
            continue
        users = item.get("users") or []
        kept = [u for u in users if u.get("name") != name]
        if len(kept) != len(users):
            removed = True
        # A vless inbound with no users at all will not start, so the shared
        # account is never the one that gets deleted here.
        if kind == "vless" and not kept:
            fail("refusing to leave the vless inbound with no users")
        item["users"] = kept
    if not removed:
        print(f"** {name} was not registered, nothing to do")
        return
    save_conf(conf)
    print(f"** removed {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show registered users").set_defaults(func=cmd_list)
    add = sub.add_parser("add", help="register a telegram id")
    add.add_argument("tg_id")
    add.set_defaults(func=cmd_add)
    remove = sub.add_parser("remove", help="revoke a telegram id")
    remove.add_argument("tg_id")
    remove.set_defaults(func=cmd_remove)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
