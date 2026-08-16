#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this command with sudo." >&2
    exit 1
fi

systemctl stop aurum-gui.service >/dev/null 2>&1 || true
systemctl reset-failed aurum-gui.service >/dev/null 2>&1 || true
printf 'Aurum GUI stopped. Installed files and Aurum mind were preserved.\n'
