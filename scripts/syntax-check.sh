#!/usr/bin/env bash
# Refuse to restart something that cannot even parse.
#
# Two failure modes make this worth the ten seconds. A syntax error in any bot
# module takes the whole bot down on the next restart. A syntax error in the
# worker bundle is worse: the upload to Cloudflare succeeds, the script is
# rejected at the edge, and every user's configs stop working at the same moment.
#
# Run it after every pull, before systemctl start.

set -euo pipefail
cd "$(dirname "$0")/.."

fail=0

echo "==> python modules"
if python3 -m compileall -q bot; then
  echo "    ok"
else
  echo "    FAILED"
  fail=1
fi

echo "==> worker bundles"
if command -v node >/dev/null 2>&1; then
  for bundle in worker/*.js; do
    # Checked as an es module, which is what a Worker actually is: as CommonJS
    # the import on line one would be reported as the error every time.
    tmp="$(mktemp /tmp/worker-XXXXXX.mjs)"
    cp "$bundle" "$tmp"
    if node --check "$tmp"; then
      echo "    ok   $bundle"
    else
      echo "    FAIL $bundle"
      fail=1
    fi
    rm -f "$tmp"
  done
else
  echo "    skipped, node is not installed on this box"
fi

echo "==> locale catalogues"
python3 - <<'PY' || fail=1
import ast
import pathlib

for path in sorted(pathlib.Path("bot/locales").glob("*.py")):
    ast.parse(path.read_text(encoding="utf-8"))
print("    ok")
PY

if [ "$fail" -ne 0 ]; then
  echo
  echo "something does not parse. Do not restart the bot yet."
  exit 1
fi

echo
echo "all clear."
