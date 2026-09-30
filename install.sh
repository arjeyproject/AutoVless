#!/usr/bin/env bash
# AutoVless installer. Installs Docker if needed, writes .env, starts the bot.
set -euo pipefail

REPO="https://github.com/arjeyproject/AutoVless.git"
TARGET="${AUTOVLESS_DIR:-/opt/autovless}"
# The container runs as this uid (see Dockerfile). The bind-mounted data
# directory must belong to it, or SQLite cannot create the database.
APP_UID=10001

green() { printf '\033[0;32m%s\033[0m\n' "$1"; }
red()   { printf '\033[0;31m%s\033[0m\n' "$1"; }
info()  { printf '\033[0;36m%s\033[0m\n' "$1"; }

if [[ $EUID -ne 0 ]]; then
  red "Run this as root: sudo bash install.sh"
  exit 1
fi

info "1/5 installing prerequisites"
if ! command -v curl >/dev/null 2>&1; then
  (apt-get update && apt-get install -y curl) || yum install -y curl
fi
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi
if ! command -v git >/dev/null 2>&1; then
  (apt-get update && apt-get install -y git) || yum install -y git
fi
if ! command -v openssl >/dev/null 2>&1; then
  (apt-get update && apt-get install -y openssl) || yum install -y openssl
fi
if ! docker compose version >/dev/null 2>&1; then
  red "docker compose plugin is missing. Install Docker 20.10+ and retry."
  exit 1
fi

info "2/5 fetching the project into ${TARGET}"
if [[ -d "${TARGET}/.git" ]]; then
  git -C "${TARGET}" pull --ff-only
else
  git clone --depth 1 "${REPO}" "${TARGET}"
fi
cd "${TARGET}"

info "3/5 configuration"
if [[ -f .env ]]; then
  green ".env already exists, keeping it"
else
  read -rp "Bot token from @BotFather: " BOT_TOKEN
  read -rp "Your numeric Telegram id (comma separated for several admins): " ADMIN_IDS
  read -rp "Support link [https://t.me/AutoVless]: " SUPPORT_URL
  SUPPORT_URL="${SUPPORT_URL:-https://t.me/AutoVless}"
  read -rp "Your domain for the mini app / payments, e.g. bot.example.com (empty to skip): " DOMAIN

  if [[ -z "${BOT_TOKEN}" || -z "${ADMIN_IDS}" ]]; then
    red "Both the bot token and the admin id are required."
    exit 1
  fi

  cp .env.example .env
  sed -i "s|^BOT_TOKEN=.*|BOT_TOKEN=${BOT_TOKEN}|" .env
  sed -i "s|^ADMIN_IDS=.*|ADMIN_IDS=${ADMIN_IDS}|" .env
  sed -i "s|^SUPPORT_URL=.*|SUPPORT_URL=${SUPPORT_URL}|" .env
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(openssl rand -hex 32)|" .env
  if [[ -n "${DOMAIN}" ]]; then
    DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN%/}"
    for KEY in WEBAPP_URL PUBLIC_URL; do
      if grep -q "^${KEY}=" .env; then
        sed -i "s|^${KEY}=.*|${KEY}=https://${DOMAIN}|" .env
      else
        echo "${KEY}=https://${DOMAIN}" >> .env
      fi
    done
  fi
  chmod 600 .env
  green ".env written"
fi

mkdir -p data
chown -R "${APP_UID}:${APP_UID}" data

info "4/5 building the image"
docker compose build --pull

info "5/5 starting"
docker compose up -d

green ""
green "AutoVless is running."
green "Logs:    docker compose -f ${TARGET}/docker-compose.yml logs -f"
green "Restart: docker compose -f ${TARGET}/docker-compose.yml restart"
green "Update:  cd ${TARGET} && git pull && docker compose up -d --build"
green ""
green "Open Telegram and send /start to your bot."
