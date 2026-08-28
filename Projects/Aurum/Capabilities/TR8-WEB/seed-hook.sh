#!/usr/bin/env bash
set -euo pipefail

# Run from an Aurum full-seed build/install environment.
# Usage: seed-hook.sh [TARGET_ROOT]
# TARGET_ROOT defaults to / for an installed system. For image construction,
# pass the mounted/chroot root of the candidate filesystem.

root="${1:-/}"
root="${root%/}"
[[ -n "$root" ]] || root=/

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$root" == / ]]; then
  exec "$here/materialize.sh"
fi

[[ -d "$root" ]] || { echo "TR8:WEB target root does not exist: $root" >&2; exit 2; }
[[ -x "$root/bin/bash" || -x "$root/usr/bin/bash" ]] || { echo "TR8:WEB target root is not a usable Linux filesystem: $root" >&2; exit 3; }

stage="$root/var/lib/aurum/seed/TR8-WEB"
install -d -m 0755 "$stage"
install -m 0755 "$here/materialize.sh" "$stage/materialize.sh"

# Execute inside the candidate filesystem so package installation and paths land
# in the seed rather than on the build host.
chroot "$root" /var/lib/aurum/seed/TR8-WEB/materialize.sh

install -m 0755 "$here/acceptance.sh" "$stage/acceptance.sh"

echo "TR8:WEB seeded into $root"
