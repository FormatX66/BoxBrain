#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run the BoxBrain desktop shortcut installer with sudo." >&2
    exit 1
fi

desktop_user=${1:-kali}
case "$desktop_user" in
    ''|*[!a-zA-Z0-9_-]*)
        echo "The desktop user name is invalid." >&2
        exit 1
        ;;
esac

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
helper_source=$project_dir/scripts/open-headless-windows.sh
shortcut_source=$project_dir/desktop/boxbrain-headless-windows.desktop
home_directory=$(getent passwd "$desktop_user" | cut -d: -f6)
primary_group=$(id -gn "$desktop_user")

[ -n "$home_directory" ] || {
    echo "The requested desktop user does not exist." >&2
    exit 1
}
desktop_directory=$home_directory/Desktop
[ -d "$desktop_directory" ] || {
    echo "The requested user's Desktop directory does not exist." >&2
    exit 1
}
[ -f "$helper_source" ]
[ -f "$shortcut_source" ]
command -v dbus-run-session >/dev/null 2>&1
command -v gio >/dev/null 2>&1

shortcut_target=$desktop_directory/BoxBrain\ Headless\ Windows.desktop

install -o root -g root -m 0755 \
    "$helper_source" \
    /usr/local/bin/boxbrain-headless-windows
install -o "$desktop_user" -g "$primary_group" -m 0755 \
    "$shortcut_source" \
    "$shortcut_target"
sudo -n -u "$desktop_user" dbus-run-session -- \
    gio set "$shortcut_target" metadata::trusted true

printf 'Installed BoxBrain headless shortcut for %s.\n' "$desktop_user"
