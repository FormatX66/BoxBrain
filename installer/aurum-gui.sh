#!/bin/sh
set -eu

root=${AURUM_ROOT:-/opt/boxbrain/codelation}
if [ "$root" != "/opt/boxbrain/codelation" ]; then
    echo "Aurum GUI root must remain /opt/boxbrain/codelation." >&2
    exit 1
fi

exec /usr/bin/python3 \
    /opt/boxbrain/codelation/seed/aurum_gui_context.py \
    --root "$root" \
    "$@"
