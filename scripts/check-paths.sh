#!/usr/bin/env bash
set -Eeuo pipefail

# Usage: ENDPOINTS='https://edge-a.example/health https://edge-b.example/health' bash scripts/check-paths.sh
# Exit 0 when at least one endpoint responds with 2xx/3xx; prints a machine-readable report.

: "${ENDPOINTS:?Set ENDPOINTS to a space-separated list of HTTPS health URLs}"

ok=0
for url in $ENDPOINTS; do
  code=$(curl --silent --show-error --location --head --connect-timeout 5 --max-time 12 \
    --output /dev/null --write-out '%{http_code}' "$url" || true)
  if [[ "$code" =~ ^[23][0-9][0-9]$ ]]; then
    printf 'UP   %s %s\n' "$code" "$url"
    ok=1
  else
    printf 'DOWN %s %s\n' "${code:-000}" "$url"
  fi
done

(( ok == 1 ))
