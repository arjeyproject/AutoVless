#!/usr/bin/env bash
# AutoVless: put the mini app + API behind HTTPS on your own domain with Caddy.
# Usage: sudo bash scripts/setup-miniapp.sh prostoreshop.site
set -euo pipefail

DOMAIN="${1:-prostoreshop.site}"
DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN%/}"
PORT="${API_PORT:-8088}"
TARGET="${AUTOVLESS_DIR:-/opt/autovless}"
ENV_FILE="${TARGET}/.env"

green() { printf '\033[0;32m%s\033[0m\n' "$1"; }
red()   { printf '\033[0;31m%s\033[0m\n' "$1"; }
info()  { printf '\033[0;36m%s\033[0m\n' "$1"; }

[[ $EUID -eq 0 ]] || { red "Run as root: sudo bash $0 ${DOMAIN}"; exit 1; }

set_kv() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "${ENV_FILE}"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
  else
    echo "${key}=${value}" >> "${ENV_FILE}"
  fi
}

info "1/4 checking DNS for ${DOMAIN}"
MY_IP="$(curl -4 -fsS https://api.ipify.org || true)"
DNS_IP="$(getent ahostsv4 "${DOMAIN}" | awk 'NR==1{print $1}' || true)"
echo "server ip: ${MY_IP:-unknown}   dns says: ${DNS_IP:-nothing}"
if [[ -n "${MY_IP}" && "${DNS_IP}" != "${MY_IP}" ]]; then
  red "Warning: ${DOMAIN} does not point at this server yet (or the Cloudflare cloud is orange)."
  red "Caddy may fail to get a certificate. Fix the A record, wait a minute, rerun."
fi

info "2/4 installing Caddy"
apt-get update -y
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
apt-get update -y
apt-get install -y caddy

info "3/4 writing /etc/caddy/Caddyfile"
cat > /etc/caddy/Caddyfile <<EOF
${DOMAIN} {
    encode gzip
    reverse_proxy 127.0.0.1:${PORT}
}
EOF
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl enable caddy
systemctl restart caddy

info "4/4 updating ${ENV_FILE}"
if [[ -f "${ENV_FILE}" ]]; then
  set_kv WEBAPP_URL "https://${DOMAIN}"
  set_kv PUBLIC_URL "https://${DOMAIN}"
  # The API must only be reachable through Caddy, never straight from the internet.
  set_kv API_HOST "127.0.0.1"
  set_kv API_PORT "${PORT}"
  green ".env updated"
else
  red "${ENV_FILE} not found. Run install.sh first, then rerun this script."
fi

green ""
green "Done. Restart the bot:  cd ${TARGET} && docker compose up -d --build"
green "Then check:            curl https://${DOMAIN}/api/health"
