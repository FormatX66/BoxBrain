#!/bin/sh
set -eu
umask 022

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo." >&2
    exit 1
fi
if [ "$#" -ne 1 ]; then
    echo "Usage: install-aurum-gui-on-pi.sh SOURCE_DIRECTORY" >&2
    exit 1
fi

source_directory=$1
case "$source_directory" in
    /tmp/aurum-gui-[A-Za-z0-9]*) ;;
    *)
        echo "Source must be a uniquely named /tmp/aurum-gui-* directory." >&2
        exit 1
        ;;
esac

console=/opt/boxbrain/codelation/seed/aurum_console.py
dialogue=/opt/boxbrain/codelation/seed/aurum_dialogue.py
module="$source_directory/aurum_gui.py"
launcher="$source_directory/aurum-gui.sh"
starter="$source_directory/start-aurum-gui-on-pi.sh"
stopper="$source_directory/stop-aurum-gui-on-pi.sh"

for required in "$console" "$dialogue" "$module" "$launcher" "$starter" "$stopper"; do
    test -f "$required"
done

/usr/bin/python3 -m py_compile "$module"
PYTHONPATH=/opt/boxbrain/codelation/seed /usr/bin/python3 "$module" \
    --root /opt/boxbrain/codelation \
    --host 127.0.0.1 \
    --port 8765 \
    --status >/dev/null

destination=/opt/boxbrain/codelation/seed/aurum_gui.py
rollback=/opt/boxbrain/codelation/rollback/gui
if [ -f "$destination" ]; then
    existing_sha=$(sha256sum "$destination" | awk '{print $1}')
    incoming_sha=$(sha256sum "$module" | awk '{print $1}')
    if [ "$existing_sha" != "$incoming_sha" ]; then
        install -d -o root -g root -m 0755 "$rollback"
        backup="$rollback/aurum_gui.py.$existing_sha"
        if [ ! -e "$backup" ]; then
            install -o root -g root -m 0644 "$destination" "$backup"
        fi
    fi
fi

install -o root -g root -m 0644 "$module" "$destination"
install -o root -g root -m 0755 "$launcher" /usr/local/bin/aurum-gui
install -o root -g root -m 0755 "$starter" /usr/local/bin/aurum-gui-start
install -o root -g root -m 0755 "$stopper" /usr/local/bin/aurum-gui-stop

printf 'AURUM_GUI_INSTALLED module_sha256=%s persistent_service=false\n' \
    "$(sha256sum "$destination" | awk '{print $1}')"
