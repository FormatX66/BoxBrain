#!/usr/bin/env bash
set -euo pipefail

fail=0
check() { if "$@"; then printf 'PASS %s\n' "$*"; else printf 'FAIL %s\n' "$*"; fail=1; fi; }

check test -x /usr/local/bin/aurum-web
check test -r /usr/local/lib/aurum/tr8-web-engine
check test -f /usr/share/applications/aurum-web.desktop

engine="$(head -n1 /usr/local/lib/aurum/tr8-web-engine 2>/dev/null || true)"
if [[ -n "$engine" ]]; then
  check command -v "$engine"
else
  echo 'FAIL browser engine binding missing'
  fail=1
fi

if command -v getent >/dev/null 2>&1; then
  check getent hosts example.com
fi

python3 - <<'PY' || fail=1
import ssl, urllib.request
ctx=ssl.create_default_context()
with urllib.request.urlopen('https://example.com/', timeout=10, context=ctx) as r:
    if r.status >= 400:
        raise SystemExit(1)
print('PASS HTTPS request')
PY

if grep -q '^Exec=/usr/local/bin/aurum-web' /usr/share/applications/aurum-web.desktop; then
  echo 'PASS graphical launcher'
else
  echo 'FAIL graphical launcher'
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  echo 'TR8:WEB acceptance FAILED' >&2
  exit 1
fi

echo 'TR8:WEB acceptance PASSED'
