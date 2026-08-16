#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this command with sudo." >&2
    exit 1
fi

gui_user=kali
gui_address=127.0.0.1
gui_port=8765
gui_unit=aurum-gui.service
gui_root=/opt/boxbrain/codelation

id "$gui_user" >/dev/null 2>&1
test -x /usr/local/bin/aurum-gui
test -f "$gui_root/seed/aurum_gui.py"
test -f "$gui_root/seed/aurum_console.py"
test -f "$gui_root/seed/aurum_dialogue.py"

health_check() {
    curl \
        --fail \
        --silent \
        --show-error \
        --max-time 2 \
        -H "Host: 127.0.0.1:$gui_port" \
        "http://$gui_address:$gui_port/api/status"
}

if systemctl is-active --quiet "$gui_unit"; then
    health_check >/dev/null
    printf 'AURUM_GUI_READY address=%s port=%s transient=true\n' "$gui_address" "$gui_port"
    exit 0
fi

if ss -ltnH "sport = :$gui_port" | grep -q .; then
    echo "Aurum GUI port $gui_port is already in use." >&2
    exit 1
fi

systemctl stop "$gui_unit" >/dev/null 2>&1 || true
systemctl reset-failed "$gui_unit" >/dev/null 2>&1 || true

gui_uid=$(id -u "$gui_user")
gui_gid=$(id -g "$gui_user")
gui_home=$(getent passwd "$gui_user" | cut -d: -f6)
runtime_directory="/run/user/$gui_uid"
install -d -o "$gui_user" -g "$gui_gid" -m 0700 "$runtime_directory"

# A recently stopped server can leave the loopback socket unavailable briefly
# even after its listener disappears. Probe the exact fail-closed bind before
# creating the transient unit so a restart cannot race the kernel socket hold.
python3 - "$gui_address" "$gui_port" <<'PY'
import errno
import socket
import sys
import time

host, port = sys.argv[1], int(sys.argv[2])
deadline = time.monotonic() + 45
while True:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
        break
    except OSError as error:
        if error.errno != errno.EADDRINUSE or time.monotonic() >= deadline:
            raise
        time.sleep(0.25)
    finally:
        probe.close()
PY

systemd-run \
    --unit="$gui_unit" \
    --collect \
    --uid="$gui_user" \
    --gid="$gui_gid" \
    --property=Restart=no \
    --setenv="HOME=$gui_home" \
    --setenv="USER=$gui_user" \
    --setenv="XDG_RUNTIME_DIR=$runtime_directory" \
    --working-directory="$gui_root" \
    -- \
    /usr/local/bin/aurum-gui \
    --host "$gui_address" \
    --port "$gui_port"

attempt=0
while [ "$attempt" -lt 40 ]; do
    if health_check >/dev/null 2>&1; then
        printf 'AURUM_GUI_READY address=%s port=%s transient=true\n' "$gui_address" "$gui_port"
        exit 0
    fi
    if ! systemctl is-active --quiet "$gui_unit"; then
        break
    fi
    attempt=$((attempt + 1))
    sleep 0.25
done

systemctl status "$gui_unit" --no-pager >&2 || true
exit 1
