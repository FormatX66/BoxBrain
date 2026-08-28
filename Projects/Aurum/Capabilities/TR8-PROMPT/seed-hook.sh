#!/usr/bin/env bash
set -euo pipefail
root="${1:-/}"; root="${root%/}"; [[ -n "$root" ]] || root=/
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$root" == / ]]; then exec "$here/materialize.sh"; fi
[[ -d "$root" ]] || { echo "TR8:PROMPT target root missing: $root" >&2; exit 2; }
stage="$root/var/lib/aurum/seed/TR8-PROMPT"
install -d -m 0755 "$stage"
install -m 0755 "$here/materialize.sh" "$stage/materialize.sh"
install -m 0755 "$here/server.py" "$stage/server.py"
install -m 0644 "$here/index.html" "$stage/index.html"
chroot "$root" /var/lib/aurum/seed/TR8-PROMPT/materialize.sh
echo "TR8:PROMPT seeded into $root"
