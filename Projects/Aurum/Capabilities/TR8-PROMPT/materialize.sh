#!/usr/bin/env bash
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
lib=/usr/local/lib/aurum/prompt
bin=/usr/local/bin/aurum-prompt
install -d -m 0755 "$lib"
install -m 0755 "$here/server.py" "$lib/server.py"
install -m 0644 "$here/index.html" "$lib/index.html"
cat > "$bin" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
health=http://127.0.0.1:8765/healthz
if ! curl -fsS --max-time 1 "$health" >/dev/null 2>&1; then
  nohup /usr/bin/env python3 /usr/local/lib/aurum/prompt/server.py >"${XDG_RUNTIME_DIR:-/tmp}/aurum-prompt.log" 2>&1 &
  for _ in $(seq 1 30); do
    curl -fsS --max-time 1 "$health" >/dev/null 2>&1 && break
    sleep .1
  done
fi
exec /usr/local/bin/aurum-web http://127.0.0.1:8765/
EOF
chmod 0755 "$bin"

appdir=/usr/local/share/applications
install -d -m 0755 "$appdir"
cat > "$appdir/aurum-prompt.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Aurum
Comment=Web and Aurum/GPT prompt surface
Exec=/usr/local/bin/aurum-prompt
Terminal=false
Categories=Network;Utility;
StartupNotify=true
EOF
chmod 0644 "$appdir/aurum-prompt.desktop"

echo "TR8:PROMPT materialized"
