#!/usr/bin/env bash
#
# AutoVless: install the self-hosted inbounds on this machine.
#
#   * VLESS + REALITY on 443. No domain, no certificate, no CDN. The TLS
#     handshake clients see is a genuine one borrowed from a real site, so there
#     is nothing self-signed to fingerprint and no SNI of yours on the wire.
#   * Shadowsocks-2022 (2022-blake3-aes-128-gcm) on 8443. No plugin, no TLS
#     wrapper, nothing per-user to deploy, which is what makes it free and
#     automatic.
#
# Both are served by one sing-box process on your own IP. There is no
# third-party account anywhere in the path, which is the entire point: an account
# that does not exist cannot be suspended.
#
# Usage:
#   sudo -E bash scripts/install-selfhost.sh
#
# Environment overrides, all optional:
#   SELFHOST_HOST=1.2.3.4        skip public-address detection
#   SNI=www.datadoghq.com        the site REALITY borrows its handshake from
#   REALITY_PORT=443  SS_PORT=8443
#   FORCE=1                      rotate the keys instead of re-printing them
#
set -euo pipefail

SNI="${SNI:-www.datadoghq.com}"
REALITY_PORT="${REALITY_PORT:-443}"
SS_PORT="${SS_PORT:-8443}"
SS_METHOD="${SS_METHOD:-2022-blake3-aes-128-gcm}"
FORCE="${FORCE:-0}"
CONF="/etc/sing-box/config.json"
STATE="/etc/autovless/selfhost.env"

say() { printf '\033[36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[31m!!\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run this as root: sudo -E bash $0"
command -v apt-get >/dev/null 2>&1 || die "this installer expects Debian or Ubuntu"

# Re-running must be safe. Rotating the keys would invalidate every config your
# users already saved, so an existing install only re-prints what it has.
if [ -f "$STATE" ] && [ "$FORCE" != "1" ]; then
  say "already installed - re-printing the .env block (FORCE=1 to rotate keys)"
  echo
  cat "$STATE"
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive
say "installing prerequisites"
apt-get update -qq
apt-get install -y -qq curl ca-certificates gnupg jq openssl >/dev/null

if ! command -v sing-box >/dev/null 2>&1; then
  say "adding the official sing-box repository"
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://sing-box.app/gpg.key -o /etc/apt/keyrings/sagernet.asc
  chmod a+r /etc/apt/keyrings/sagernet.asc
  echo 'deb [signed-by=/etc/apt/keyrings/sagernet.asc] https://deb.sagernet.org/ * *' \
    > /etc/apt/sources.list.d/sagernet.list
  apt-get update -qq
  say "installing sing-box"
  apt-get install -y -qq sing-box >/dev/null
fi
command -v sing-box >/dev/null 2>&1 || die "sing-box is still not on PATH"

HOST="${SELFHOST_HOST:-}"
if [ -z "$HOST" ]; then
  say "detecting the public address"
  HOST="$(curl -fsS4 --max-time 8 https://api.ipify.org 2>/dev/null || true)"
fi
if [ -z "$HOST" ]; then
  HOST="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}' || true)"
fi
[ -n "$HOST" ] || die "could not detect the public address - re-run with SELFHOST_HOST=your.ip"

say "generating keys"
KEYS="$(sing-box generate reality-keypair)"
PRIV="$(printf '%s\n' "$KEYS" | awk -F': *' '/PrivateKey/ {print $2}' | tr -d '\r')"
PUB="$(printf '%s\n' "$KEYS" | awk -F': *' '/PublicKey/ {print $2}' | tr -d '\r')"
[ -n "$PRIV" ] && [ -n "$PUB" ] || die "could not read the reality keypair"
UUID="$(sing-box generate uuid 2>/dev/null || cat /proc/sys/kernel/random/uuid)"
SID="$(openssl rand -hex 8)"
PSK="$(openssl rand -base64 16)"

say "writing $CONF"
install -d -m 0750 /etc/sing-box
install -d -m 0750 /etc/autovless
cat > "$CONF" <<JSON
{
  "log": { "level": "warn", "timestamp": true },
  "dns": {
    "servers": [ { "tag": "doh", "address": "https://1.1.1.1/dns-query" } ],
    "strategy": "prefer_ipv4"
  },
  "inbounds": [
    {
      "type": "vless",
      "tag": "vless-reality",
      "listen": "::",
      "listen_port": ${REALITY_PORT},
      "users": [ { "name": "free", "uuid": "${UUID}", "flow": "xtls-rprx-vision" } ],
      "tls": {
        "enabled": true,
        "server_name": "${SNI}",
        "reality": {
          "enabled": true,
          "handshake": { "server": "${SNI}", "server_port": 443 },
          "private_key": "${PRIV}",
          "short_id": [ "${SID}" ]
        }
      }
    },
    {
      "type": "shadowsocks",
      "tag": "ss2022",
      "listen": "::",
      "listen_port": ${SS_PORT},
      "method": "${SS_METHOD}",
      "password": "${PSK}"
    }
  ],
  "outbounds": [
    { "type": "direct", "tag": "direct" },
    { "type": "block", "tag": "block" }
  ],
  "route": {
    "rules": [
      { "ip_is_private": true, "outbound": "block" },
      { "protocol": "bittorrent", "outbound": "block" }
    ],
    "final": "direct"
  }
}
JSON
chmod 0640 "$CONF"
sing-box check -c "$CONF" || die "the generated config did not pass sing-box check"

say "tuning the kernel and the unit"
cat > /etc/sysctl.d/99-autovless.conf <<'SYSCTL'
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr
net.ipv4.tcp_fastopen = 3
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_mtu_probing = 1
SYSCTL
sysctl --system >/dev/null 2>&1 || true

install -d -m 0755 /etc/systemd/system/sing-box.service.d
cat > /etc/systemd/system/sing-box.service.d/override.conf <<'UNIT'
[Service]
LimitNOFILE=1048576
Restart=always
RestartSec=3
UNIT

systemctl daemon-reload
systemctl enable --now sing-box >/dev/null 2>&1 || systemctl restart sing-box
sleep 2
if ! systemctl is-active --quiet sing-box; then
  journalctl -u sing-box -n 40 --no-pager || true
  die "sing-box did not stay up - the log above says why"
fi

if command -v ufw >/dev/null 2>&1; then
  say "opening the ports in ufw"
  ufw allow "${REALITY_PORT}"/tcp >/dev/null 2>&1 || true
  ufw allow "${SS_PORT}"/tcp >/dev/null 2>&1 || true
  ufw allow "${SS_PORT}"/udp >/dev/null 2>&1 || true
fi

cat > "$STATE" <<ENV
SELFHOST=1
SELFHOST_HOST=${HOST}
REALITY_PORT=${REALITY_PORT}
REALITY_SNI=${SNI}
REALITY_PBK=${PUB}
REALITY_SID=${SID}
REALITY_UUID=${UUID}
SS2022_PORT=${SS_PORT}
SS2022_METHOD=${SS_METHOD}
SS2022_PSK=${PSK}
SELFHOST_PER_USER=0
ENV
chmod 0600 "$STATE"

say "sing-box is up on ${HOST}:${REALITY_PORT} (REALITY) and ${HOST}:${SS_PORT} (SS-2022)"
say "append this block to the bot's .env, then restart the bot:"
echo
cat "$STATE"
echo
say "a copy lives at ${STATE} - keep it, it is the only copy of the keys"
