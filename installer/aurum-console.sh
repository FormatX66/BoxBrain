#!/bin/sh
set -eu
umask 077

root=/opt/boxbrain/codelation
console="$root/seed/aurum_console.py"
dialogue="$root/seed/aurum_dialogue.py"

if [ ! -r "$console" ] || [ ! -r "$dialogue" ]; then
    echo "The bounded Aurum console installation is incomplete." >&2
    exit 1
fi

exec /usr/bin/python3 "$console" --root "$root" "$@"
