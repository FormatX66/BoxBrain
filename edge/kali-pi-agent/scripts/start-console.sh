#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this command with sudo." >&2
    exit 1
fi

console_user=kali
console_root=/opt/boxbrain/pi-console
console_bind=10.12.194.1
viewer_port=8790
display_unit=boxbrain-console-display.service
desktop_unit=boxbrain-console-desktop.service
websocket_unit=boxbrain-console-websocket.service
viewer_unit=boxbrain-console-viewer.service

if [ -r /etc/boxbrain/console.env ]; then
    # This file is installed root-owned and may contain only console settings.
    # shellcheck disable=SC1091
    . /etc/boxbrain/console.env
    console_bind=${BOXBRAIN_CONSOLE_BIND:-$console_bind}
    viewer_port=${BOXBRAIN_CONSOLE_VIEWER_PORT:-$viewer_port}
fi

python3 - "$console_bind" "$viewer_port" <<'PY'
import ipaddress
import sys

address = ipaddress.ip_address(sys.argv[1])
port = int(sys.argv[2])
if not (address.is_private or address.is_link_local):
    raise SystemExit("Console bind address must be private or link-local.")
if not 1024 <= port <= 65535:
    raise SystemExit("Console viewer port must be between 1024 and 65535.")
PY

if ! ip -4 -o address show | grep -Fq " $console_bind/"; then
    echo "Console bind address $console_bind is not assigned to this Pi." >&2
    exit 1
fi
if ! id "$console_user" >/dev/null 2>&1; then
    echo "The required local account '$console_user' does not exist." >&2
    exit 1
fi
test -f "$console_root/current/vnc.html"
test -f "$console_root/current/LICENSE.txt"

console_uid=$(id -u "$console_user")
console_gid=$(id -g "$console_user")
console_home=$(getent passwd "$console_user" | cut -d: -f6)
runtime_directory="/run/user/$console_uid"
install -d -o "$console_user" -g "$console_gid" -m 0700 "$runtime_directory"

port_is_listening() {
    ss -ltn | grep -Fq "$1:$2"
}

wait_for_port() {
    address=$1
    port=$2
    count=0
    while [ "$count" -lt 40 ]; do
        if port_is_listening "$address" "$port"; then
            return 0
        fi
        count=$((count + 1))
        sleep 0.25
    done
    return 1
}

prepare_unit() {
    unit=$1
    systemctl stop "$unit" >/dev/null 2>&1 || true
    systemctl reset-failed "$unit" >/dev/null 2>&1 || true
}

if ! systemctl is-active --quiet "$display_unit"; then
    if port_is_listening 127.0.0.1 5901; then
        echo "Port 127.0.0.1:5901 is already used by another process." >&2
        exit 1
    fi
    prepare_unit "$display_unit"
    systemd-run \
        --unit="$display_unit" \
        --collect \
        --uid="$console_user" \
        --gid="$console_gid" \
        --property=Restart=no \
        -- \
        /usr/bin/Xtightvnc :1 \
        -desktop BoxBrain-Pi \
        -geometry 1280x800 \
        -depth 24 \
        -localhost \
        -rfbport 5901 \
        -alwaysshared \
        -dontdisconnect
fi
wait_for_port 127.0.0.1 5901

if ! systemctl is-active --quiet "$desktop_unit"; then
    prepare_unit "$desktop_unit"
    systemd-run \
        --unit="$desktop_unit" \
        --collect \
        --uid="$console_user" \
        --gid="$console_gid" \
        --property=Restart=no \
        --setenv="HOME=$console_home" \
        --setenv="USER=$console_user" \
        --setenv=DISPLAY=:1 \
        --setenv="XDG_RUNTIME_DIR=$runtime_directory" \
        -- \
        /usr/bin/dbus-run-session /usr/bin/startxfce4
fi

if ! systemctl is-active --quiet "$websocket_unit"; then
    if port_is_listening 127.0.0.1 6080; then
        echo "Port 127.0.0.1:6080 is already used by another process." >&2
        exit 1
    fi
    prepare_unit "$websocket_unit"
    systemd-run \
        --unit="$websocket_unit" \
        --collect \
        --uid="$console_user" \
        --gid="$console_gid" \
        --property=Restart=no \
        -- \
        /usr/bin/websockify 127.0.0.1:6080 127.0.0.1:5901
fi
wait_for_port 127.0.0.1 6080

if ! systemctl is-active --quiet "$viewer_unit"; then
    if port_is_listening "$console_bind" "$viewer_port"; then
        echo "Port $console_bind:$viewer_port is already used by another process." >&2
        exit 1
    fi
    prepare_unit "$viewer_unit"
    systemd-run \
        --unit="$viewer_unit" \
        --collect \
        --uid="$console_user" \
        --gid="$console_gid" \
        --property=Restart=no \
        --working-directory="$console_root" \
        -- \
        /usr/bin/python3 -m http.server "$viewer_port" --bind "$console_bind"
fi
wait_for_port "$console_bind" "$viewer_port"

curl \
    --fail \
    --silent \
    --show-error \
    "http://$console_bind:$viewer_port/current/vnc.html" \
    >/dev/null

printf 'BOXBRAIN_CONSOLE_READY address=%s port=%s\n' \
    "$console_bind" \
    "$viewer_port"
