#!/usr/bin/env bash
#
# Export the measured WARP endpoint pool and push it to GitHub.
#
# Meant for cron on the box that runs the bot:
#
#   */30 * * * * /opt/AutoVless/scripts/publish_endpoints.sh >> /var/log/autovless-endpoints.log 2>&1
#
# Safe to run as often as you like. It takes a lock, only commits when the list
# actually changed, rebases before pushing, retries a rejected push, and never
# prints the token.
#
# Environment:
#   REPO_DIR      repository root (default: the parent of this script)
#   BRANCH        branch to push (default: current branch, else main)
#   OUT           output basename (default: endpoints/warp-endpoints)
#   LIMIT         how many endpoints to publish (default: 40)
#   PYTHON        interpreter (default: .venv/bin/python when present, else python3)
#   GITHUB_TOKEN  optional PAT with contents:write; without it the existing
#                 remote credentials are used
#   GIT_NAME / GIT_EMAIL   commit identity when the repo has none configured
#
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
OUT="${OUT:-endpoints/warp-endpoints}"
LIMIT="${LIMIT:-40}"
LOCK_FILE="${LOCK_FILE:-/tmp/autovless-endpoints.lock}"

log() { printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }
die() { log "ERROR: $*"; exit 1; }

# One publisher at a time. Cron overlapping itself is how a repository ends up
# with a half written file and a rebase left in progress.
if command -v flock >/dev/null 2>&1 && [[ -z "${_ENDPOINTS_LOCKED:-}" ]]; then
  export _ENDPOINTS_LOCKED=1
  exec flock -n "${LOCK_FILE}" "$0" "$@"
fi

cd "${REPO_DIR}" || die "cannot enter ${REPO_DIR}"
git rev-parse --git-dir >/dev/null 2>&1 || die "${REPO_DIR} is not a git repository"

if [[ -n "${PYTHON:-}" ]]; then
  :
elif [[ -x "${REPO_DIR}/.venv/bin/python" ]]; then
  PYTHON="${REPO_DIR}/.venv/bin/python"
else
  PYTHON="$(command -v python3 || true)"
fi
[[ -n "${PYTHON}" ]] || die "no python interpreter found"

BRANCH="${BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)}"
[[ "${BRANCH}" != "HEAD" ]] || BRANCH="main"

log "exporting the endpoint pool with ${PYTHON}"
"${PYTHON}" "${SCRIPT_DIR}/publish_warp.py" --mode db --out "${OUT}" --limit "${LIMIT}" \
  || die "export failed (is the bot database reachable and the pool non-empty?)"

git add -- "${OUT}.json" "${OUT}.txt"
if git diff --cached --quiet -- "${OUT}.json" "${OUT}.txt"; then
  log "endpoint list unchanged, nothing to push"
  exit 0
fi

count="$(sed -n 's/.*"count": *\([0-9]*\).*/\1/p' "${OUT}.json" | head -1)"
git config user.name >/dev/null 2>&1 || git config user.name "${GIT_NAME:-AutoVless bot}"
git config user.email >/dev/null 2>&1 || git config user.email "${GIT_EMAIL:-bot@autovless.local}"

git commit -q \
  -m "chore(warp): refresh endpoint pool (${count:-0} endpoints)" \
  -m "Published by scripts/publish_endpoints.sh at $(date -u '+%Y-%m-%d %H:%M:%SZ')."

remote_url="$(git remote get-url origin 2>/dev/null || true)"
[[ -n "${remote_url}" ]] || die "no origin remote configured"

# The token lives in this process only: never written to .git/config, and the
# push output is swallowed so a failure cannot echo the URL back into a log.
push_url="${remote_url}"
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  case "${remote_url}" in
    https://*)
      push_url="https://x-access-token:${GITHUB_TOKEN}@${remote_url#https://}"
      ;;
    git@github.com:*)
      push_url="https://x-access-token:${GITHUB_TOKEN}@github.com/${remote_url#git@github.com:}"
      ;;
  esac
fi

for attempt in 1 2 3; do
  git fetch --quiet origin "${BRANCH}" || log "fetch failed (attempt ${attempt})"
  git pull --quiet --rebase --autostash origin "${BRANCH}" || log "rebase failed (attempt ${attempt})"
  if git push --quiet "${push_url}" "HEAD:refs/heads/${BRANCH}" 2>/dev/null; then
    log "pushed ${count:-0} endpoints to ${BRANCH}"
    exit 0
  fi
  log "push rejected, retrying in $((attempt * 5))s"
  sleep "$((attempt * 5))"
done

die "could not push after 3 attempts"
