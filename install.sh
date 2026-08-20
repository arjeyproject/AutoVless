#!/usr/bin/env bash
# AutoVless installer. Installs Docker if needed, writes .env, starts the bot.
set -euo pipefail

REPO="https://github.com/arjeyproject/AutoVless.git"
TARGET="${AUTOVLESS_DIR:-/opt/autovless}"

green() { printf '\033[0;32m%s\033[0m\n' "$1"; }
red()   { printf '\033[0;31m%s\033[0m\n' "$1"; }
info()  { printf '\033[0;36m%s\033[0m\n' "$1"; }

if [[ $EUID -ne 0 ]]; then
  red "Run this as root: sudo bash install.sh"
  exit 1
fi

info "1/5 installing prerequisites"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi
if ! command -v git >/dev/null 2>&1; then
  (apt-get update && apt-get install -y git) || yum install -y git
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

  if [[ -z "${BOT_TOKEN}" || -z "${ADMIN_IDS}" ]]; then
    red "Both the bot token and the admin id are required."
    exit 1
  fi

  cp .env.example .env
  sed -i "s|^BOT_TOKEN=.*|BOT_TOKEN=${BOT_TOKEN}|" .env
  sed -i "s|^ADMIN_IDS=.*|ADMIN_IDS=${ADMIN_IDS}|" .env
  sed -i "s|^SUPPORT_URL=.*|SUPPORT_URL=${SUPPORT_URL}|" .env
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(openssl rand -hex 32)|" .env
  chmod 600 .env
  green ".env written"
fi

mkdir -p data

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
