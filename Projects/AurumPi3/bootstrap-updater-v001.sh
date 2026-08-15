#!/bin/sh
# One-time migration of an already-flashed Aurum Pi3 v0.01 card.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_PREFIX=/
if [ "${1:-}" = "--root" ]; then
  [ -n "${2:-}" ] || { echo "--root requires the mounted root filesystem path" >&2; exit 2; }
  ROOT_PREFIX=$2
  shift 2
fi
[ "$#" -eq 0 ] || { echo "Usage: $0 [--root /mounted/pi/root]" >&2; exit 2; }
case "$ROOT_PREFIX" in
  /*) ;;
  *) echo "--root must be an absolute path" >&2; exit 2 ;;
esac
[ -d "$ROOT_PREFIX" ] || { echo "Root filesystem is unavailable: $ROOT_PREFIX" >&2; exit 2; }
[ -f "$SCRIPT_DIR/aurum_updater.py" ] || { echo "Updater source is missing" >&2; exit 2; }
[ -d "$SCRIPT_DIR/systemd" ] || { echo "Updater systemd units are missing" >&2; exit 2; }

under_root() {
  case "$ROOT_PREFIX" in
    /) printf '/%s' "$1" ;;
    *) printf '%s/%s' "${ROOT_PREFIX%/}" "$1" ;;
  esac
}

BASE=$(under_root opt/aurum)
UPDATER="$BASE/updater"
RELEASES="$BASE/releases"
BOOTSTRAP="$RELEASES/0.01-bootstrap"
SYSTEMD=$(under_root etc/systemd/system)
STATE=$(under_root var/lib/aurum-updater)

[ -f "$BASE/aurum_pi3_console.py" ] || [ -f "$BOOTSTRAP/aurum_pi3_console.py" ] || {
  echo "Existing Aurum Pi3 v0.01 runtime was not found under $BASE" >&2
  exit 2
}
[ -d "$BASE/codelation" ] || [ -d "$BOOTSTRAP/codelation" ] || {
  echo "Existing Codelation payload was not found under $BASE" >&2
  exit 2
}

mkdir -p "$UPDATER" "$RELEASES" "$STATE" "$SYSTEMD/multi-user.target.wants"
chmod 0700 "$STATE"
install -m 0755 "$SCRIPT_DIR/aurum_updater.py" "$UPDATER/aurum_updater.py"

if [ ! -d "$BOOTSTRAP" ]; then
  TEMP_RELEASE="$RELEASES/.0.01-bootstrap.$$"
  trap 'rm -rf -- "$TEMP_RELEASE"' EXIT INT TERM
  mkdir -m 0755 "$TEMP_RELEASE"
  install -m 0755 "$BASE/aurum_pi3_console.py" "$TEMP_RELEASE/aurum_pi3_console.py"
  cp -a "$BASE/codelation" "$TEMP_RELEASE/codelation"
  find "$TEMP_RELEASE/codelation" -type f -name '*.py' -exec chmod 0644 {} +
  cat > "$TEMP_RELEASE/RELEASE.json" <<'EOF'
{
  "application_layer_only": true,
  "architecture": "arm64",
  "includes_boot_firmware": false,
  "includes_kernel": false,
  "release_id": "0.01-bootstrap",
  "schema": "aurum-runtime-release-v1",
  "target": "raspberry-pi-3",
  "version": "0.01"
}
EOF
  chmod 0644 "$TEMP_RELEASE/RELEASE.json"
  mv "$TEMP_RELEASE" "$BOOTSTRAP"
  trap - EXIT INT TERM
fi

if [ -e "$BASE/current" ] && [ ! -L "$BASE/current" ]; then
  echo "$BASE/current exists and is not a symlink; refusing to replace it" >&2
  exit 2
fi
ln -sfn releases/0.01-bootstrap "$BASE/current"

for unit in \
  aurum-pi3-console.service \
  aurum-pi3-serial.service \
  aurum-pi3-update.service \
  aurum-pi3-update-recovery.service
do
  install -m 0644 "$SCRIPT_DIR/systemd/$unit" "$SYSTEMD/$unit"
done
ln -sfn ../aurum-pi3-console.service "$SYSTEMD/multi-user.target.wants/aurum-pi3-console.service"
ln -sfn ../aurum-pi3-serial.service "$SYSTEMD/multi-user.target.wants/aurum-pi3-serial.service"
ln -sfn ../aurum-pi3-update-recovery.service "$SYSTEMD/multi-user.target.wants/aurum-pi3-update-recovery.service"
ln -sfn /dev/null "$SYSTEMD/getty@tty1.service"
ln -sfn /dev/null "$SYSTEMD/serial-getty@serial0.service"
ln -sfn /dev/null "$SYSTEMD/serial-getty@ttyAMA0.service"

if [ "$ROOT_PREFIX" = / ] && command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  systemctl daemon-reload
  systemctl enable aurum-pi3-console.service aurum-pi3-serial.service aurum-pi3-update-recovery.service
  systemctl restart aurum-pi3-update-recovery.service
  systemctl restart aurum-pi3-console.service aurum-pi3-serial.service
  echo "AURUM_PI3_UPDATER_BOOTSTRAPPED mode=online release=0.01-bootstrap"
else
  echo "AURUM_PI3_UPDATER_BOOTSTRAPPED mode=offline release=0.01-bootstrap next=reboot-pi"
fi
