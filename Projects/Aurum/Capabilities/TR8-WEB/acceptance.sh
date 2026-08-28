#!/usr/bin/env bash
set -euo pipefail

fail=0
say(){ printf 'TR8:WEB %-34s %s\n' "$1" "$2"; }

if [[ -x /usr/local/bin/aurum-web ]]; then say launcher PASS; else say launcher FAIL; fail=1; fi

engine_file=/usr/local/lib/aurum/tr8-web-engine
if [[ -r "$engine_file" ]]; then
  engine="$(head -n1 "$engine_file")"
  if command -v "$engine" >/dev/null 2>&1; then say engine PASS; else say engine FAIL; fail=1; fi
else
  say engine-binding FAIL
  fail=1
fi

if command -v getent >/dev/null 2>&1 && getent hosts example.com >/dev/null 2>&1; then
  say dns PASS
else
  say dns FAIL
  fail=1
fi

if command -v curl >/dev/null 2>&1; then
  if curl -fsSIL --max-time 15 https://example.com >/dev/null; then say https PASS; else say https FAIL; fail=1; fi
elif command -v wget >/dev/null 2>&1; then
  if wget -q --spider --timeout=15 https://example.com; then say https PASS; else say https FAIL; fail=1; fi
else
  say https SKIP-no-probe-tool
fi

if [[ -f /usr/share/applications/aurum-web.desktop ]]; then say shell-entry PASS; else say shell-entry FAIL; fail=1; fi

if grep -q '^Exec=/usr/local/bin/aurum-web' /usr/share/applications/aurum-web.desktop 2>/dev/null; then
  say stable-interface PASS
else
  say stable-interface FAIL
  fail=1
fi

if [[ $fail -eq 0 ]]; then
  echo 'TR8:WEB ACCEPTANCE=PASS'
else
  echo 'TR8:WEB ACCEPTANCE=FAIL'
fi
exit "$fail"
