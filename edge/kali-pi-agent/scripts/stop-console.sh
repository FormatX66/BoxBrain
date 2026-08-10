#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this command with sudo." >&2
    exit 1
fi

for unit in \
    boxbrain-console-viewer.service \
    boxbrain-console-target-websocket.service \
    boxbrain-console-websocket.service \
    boxbrain-console-desktop.service \
    boxbrain-console-display.service
do
    systemctl stop "$unit" >/dev/null 2>&1 || true
    systemctl reset-failed "$unit" >/dev/null 2>&1 || true
done

printf 'BoxBrain Pi console stopped.\n'
