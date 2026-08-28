#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "TR8:WEB materializer must be run as root during seed build/install." >&2
  exit 2
fi

pick_existing() {
  for b in chromium chromium-browser firefox-esr firefox; do
    if command -v "$b" >/dev/null 2>&1; then
      printf '%s\n' "$b"
      return 0
    fi
  done
  return 1
}

install_engine() {
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    if apt-cache show chromium >/dev/null 2>&1; then
      apt-get install -y --no-install-recommends chromium ca-certificates xdg-utils
    elif apt-cache show firefox-esr >/dev/null 2>&1; then
      apt-get install -y --no-install-recommends firefox-esr ca-certificates xdg-utils
    else
      echo "No supported TR8:WEB browser package found in configured repositories." >&2
      return 1
    fi
    return 0
  fi
  echo "Unsupported package manager for automatic TR8:WEB materialization." >&2
  return 1
}

engine="$(pick_existing || true)"
if [[ -z "$engine" ]]; then
  install_engine
  engine="$(pick_existing)"
fi

install -d -m 0755 /usr/local/lib/aurum /usr/local/bin /usr/share/applications
cat >/usr/local/lib/aurum/tr8-web-engine <<EOF
$engine
EOF
chmod 0644 /usr/local/lib/aurum/tr8-web-engine

cat >/usr/local/bin/aurum-web <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
  echo "TR8:WEB refuses to run a web browser as root." >&2
  exit 3
fi

engine_file=/usr/local/lib/aurum/tr8-web-engine
[[ -r "$engine_file" ]] || { echo "TR8:WEB engine binding is missing." >&2; exit 4; }
engine="$(head -n1 "$engine_file")"
command -v "$engine" >/dev/null 2>&1 || { echo "TR8:WEB engine '$engine' is unavailable." >&2; exit 5; }

url="${1:-}"
profile="${XDG_STATE_HOME:-$HOME/.local/state}/aurum/tr8-web"
mkdir -p "$profile"

case "$engine" in
  chromium|chromium-browser)
    args=(--user-data-dir="$profile/chromium" --no-first-run --no-default-browser-check)
    [[ -n "$url" ]] && args+=("$url")
    exec "$engine" "${args[@]}"
    ;;
  firefox-esr|firefox)
    profile_dir="$profile/firefox-profile"
    mkdir -p "$profile_dir"
    if [[ -n "$url" ]]; then
      exec "$engine" --profile "$profile_dir" --new-window "$url"
    else
      exec "$engine" --profile "$profile_dir"
    fi
    ;;
  *)
    echo "Unsupported TR8:WEB engine binding: $engine" >&2
    exit 6
    ;;
esac
EOF
chmod 0755 /usr/local/bin/aurum-web

cat >/usr/share/applications/aurum-web.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Web
Comment=Aurum TR8:WEB
Exec=/usr/local/bin/aurum-web %u
Terminal=false
Categories=Network;WebBrowser;
MimeType=x-scheme-handler/http;x-scheme-handler/https;text/html;
StartupNotify=true
EOF
chmod 0644 /usr/share/applications/aurum-web.desktop

echo "TR8:WEB materialized with engine: $engine"
