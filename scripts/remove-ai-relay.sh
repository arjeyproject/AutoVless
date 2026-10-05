#!/usr/bin/env bash
# AutoVless: stop using this VPS as the AI exit, so AI traffic costs this server
# nothing. AI sites are then pinned (one steady relay per panel, US/EU first,
# never IR/RU/CN) from the public proxyIP pool by bot/aipin.py.
# Usage: sudo bash scripts/remove-ai-relay.sh
set -euo pipefail
TARGET="${AUTOVLESS_DIR:-/opt/autovless}"
ENV_FILE="${TARGET}/.env"
[[ $EUID -eq 0 ]] || { echo "Run as root"; exit 1; }

if [[ -f "${ENV_FILE}" ]]; then
  sed -i 's|^AI_PROXY_IP=.*|AI_PROXY_IP=|' "${ENV_FILE}"
  grep -q '^AI_ROUTE=' "${ENV_FILE}" && sed -i 's|^AI_ROUTE=.*|AI_ROUTE=true|' "${ENV_FILE}" || echo 'AI_ROUTE=true' >> "${ENV_FILE}"
  # One relay per panel keeps Google login and Gemini on the same exit.
  grep -q '^AI_RELAYS=' "${ENV_FILE}" && sed -i 's|^AI_RELAYS=.*|AI_RELAYS=1|' "${ENV_FILE}" || echo 'AI_RELAYS=1' >> "${ENV_FILE}"
fi

rm -f /etc/nginx/stream.d/autovless-ai.conf
if command -v nginx >/dev/null 2>&1; then
  systemctl stop nginx || true
  systemctl disable nginx || true
fi
command -v ufw >/dev/null 2>&1 && ufw delete allow 8443/tcp >/dev/null 2>&1 || true

cd "${TARGET}" && docker compose up -d --build
echo "Done. AI traffic no longer touches this server."
echo "In the bot: admin > AI > re-pin / refresh geo, then press 'apply fresh IPs' on each panel."
