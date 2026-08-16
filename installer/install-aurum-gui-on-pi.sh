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
context_module="$source_directory/aurum_gui_context.py"
aurum_context_module="$source_directory/aurum_context.py"
context_exchange_module="$source_directory/context_exchange.py"
launcher="$source_directory/aurum-gui.sh"
starter="$source_directory/start-aurum-gui-on-pi.sh"
stopper="$source_directory/stop-aurum-gui-on-pi.sh"

for required in \
    "$console" "$dialogue" "$module" "$context_module" \
    "$aurum_context_module" "$context_exchange_module" \
    "$launcher" "$starter" "$stopper"; do
    test -f "$required"
done

/usr/bin/python3 -m py_compile \
    "$module" "$context_module" "$aurum_context_module" "$context_exchange_module"
PYTHONPATH="$source_directory:/opt/boxbrain/codelation/seed" \
  /usr/bin/python3 "$context_module" \
    --root /opt/boxbrain/codelation \
    --host 127.0.0.1 \
    --port 8765 \
    --status >/dev/null

# A running transient process retains the old module in memory. Stop only this
# exact transient GUI unit before atomically replacing the reviewed files.
systemctl stop aurum-gui.service >/dev/null 2>&1 || true
systemctl reset-failed aurum-gui.service >/dev/null 2>&1 || true

rollback=/opt/boxbrain/codelation/rollback/gui
for source_path in \
    "$module" "$context_module" "$aurum_context_module" "$context_exchange_module"; do
    module_name=$(basename "$source_path")
    destination="/opt/boxbrain/codelation/seed/$module_name"
    if [ -f "$destination" ]; then
        existing_sha=$(sha256sum "$destination" | awk '{print $1}')
        incoming_sha=$(sha256sum "$source_path" | awk '{print $1}')
        if [ "$existing_sha" != "$incoming_sha" ]; then
            install -d -o root -g root -m 0755 "$rollback"
            backup="$rollback/$module_name.$existing_sha"
            if [ ! -e "$backup" ]; then
                install -o root -g root -m 0644 "$destination" "$backup"
            fi
        fi
    fi
    install -o root -g root -m 0644 "$source_path" "$destination"
done

install -o root -g root -m 0755 "$launcher" /usr/local/bin/aurum-gui
install -o root -g root -m 0755 "$starter" /usr/local/bin/aurum-gui-start
install -o root -g root -m 0755 "$stopper" /usr/local/bin/aurum-gui-stop

printf 'AURUM_GUI_INSTALLED module_sha256=%s context_sha256=%s persistent_service=false\n' \
    "$(sha256sum /opt/boxbrain/codelation/seed/aurum_gui.py | awk '{print $1}')" \
    "$(sha256sum /opt/boxbrain/codelation/seed/aurum_gui_context.py | awk '{print $1}')"
