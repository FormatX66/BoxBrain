#!/bin/sh
set -eu

usage() {
    echo "usage: $0 SOURCE_KALI_ISO OUTPUT_ISO EXPECTED_HOPPER_HEAD" >&2
    exit 2
}

[ "$#" -eq 3 ] || usage
source_iso=$1
output_iso=$2
expected_head=$3
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

[ -f "$source_iso" ] || { echo "source ISO is unavailable" >&2; exit 2; }
[ -d "$(dirname -- "$output_iso")" ] || { echo "output directory is unavailable" >&2; exit 2; }
[ ! -e "$output_iso" ] || { echo "refusing to overwrite an existing output ISO" >&2; exit 2; }
[ ! -e "$output_iso.sha256" ] || { echo "refusing to overwrite an existing checksum receipt" >&2; exit 2; }
source_absolute=$(readlink -f -- "$source_iso")
output_absolute=$(readlink -f -- "$output_iso")
[ "$source_absolute" != "$output_absolute" ] || { echo "source and output ISO must differ" >&2; exit 2; }
echo "$expected_head" | grep -Eq '^[0-9a-f]{40}$' || { echo "expected Hopper head is invalid" >&2; exit 2; }

for tool in mksquashfs python3 sha256sum xorriso; do
    command -v "$tool" >/dev/null 2>&1 || { echo "required build tool is missing: $tool" >&2; exit 2; }
done

build_root=$(mktemp -d)
cleanup() {
    case "$build_root" in
        /tmp/*|/var/tmp/*) rm -rf -- "$build_root" ;;
        *) echo "refusing unsafe temporary cleanup path: $build_root" >&2 ;;
    esac
}
trap cleanup EXIT HUP INT TERM

overlay=$build_root/overlay
mkdir -p \
    "$overlay/etc/aurum" \
    "$overlay/etc/systemd/system" \
    "$overlay/etc/systemd/system/aurum-hopper-seed-recovery.target.wants" \
    "$overlay/usr/local/sbin"

install -m 0755 "$script_dir/aurum_seed_recovery.py" \
    "$overlay/usr/local/sbin/aurum-seed-recovery"
install -m 0644 "$script_dir/recovery-assets/aurum-hopper-seed-recovery.service" \
    "$overlay/etc/systemd/system/aurum-hopper-seed-recovery.service"
install -m 0644 "$script_dir/recovery-assets/aurum-hopper-seed-recovery.target" \
    "$overlay/etc/systemd/system/aurum-hopper-seed-recovery.target"
ln -s ../aurum-hopper-seed-recovery.service \
    "$overlay/etc/systemd/system/aurum-hopper-seed-recovery.target.wants/aurum-hopper-seed-recovery.service"

source_sha256=$(sha256sum "$source_iso" | awk '{print $1}')
python3 - "$overlay/etc/aurum/hopper-seed-recovery-policy.json" "$expected_head" "$source_sha256" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = {
    "schema": "aurum.hopper-seed-recovery-policy.v1",
    "machine": {
        "serial": "BTTE934116YM512B-1",
        "size_bytes": 512110190592,
    },
    "repository": "https://github.com/FormatX66/BoxBrain.git",
    "branch": "aurum/trunk-v0.01",
    "expected_head": sys.argv[2],
    "workspace": "/var/lib/aurum/workspace/BoxBrain",
    "state_directory": "/var/lib/aurum/state",
    "dirty_worktree_paths": [
        "Projects/AurumPC/aurum_desktop.py",
        "Projects/AurumPC/aurum_hopper_gui.py",
    ],
    "source_iso_sha256": sys.argv[3],
}
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

mksquashfs "$overlay" "$build_root/filesystem.aurum-recovery.squashfs" \
    -noappend -comp zstd -Xcompression-level 15 >/dev/null
printf '%s\n' 'filesystem.squashfs' 'filesystem.aurum-recovery.squashfs' \
    >"$build_root/filesystem.module"

xorriso \
    -indev "$source_iso" \
    -outdev "$output_iso" \
    -boot_image any replay \
    -overwrite on \
    -map "$build_root/filesystem.aurum-recovery.squashfs" /live/filesystem.aurum-recovery.squashfs \
    -map "$build_root/filesystem.module" /live/filesystem.module \
    -map "$script_dir/recovery-assets/grub.cfg" /boot/grub/grub.cfg \
    -map "$script_dir/recovery-assets/isolinux.cfg" /isolinux/isolinux.cfg \
    -volid AURUM_HOPPER_RECOVERY \
    -commit \
    -end

xorriso -indev "$output_iso" \
    -find /live/filesystem.aurum-recovery.squashfs -exec lsdl -- \
    -find /live/filesystem.module -exec lsdl -- \
    -find /boot/grub/grub.cfg -exec lsdl -- \
    -find /isolinux/isolinux.cfg -exec lsdl -- \
    -end

output_sha256=$(sha256sum "$output_iso" | awk '{print $1}')
printf '%s  %s\n' "$output_sha256" "$(basename -- "$output_iso")" >"$output_iso.sha256"
printf 'AURUM_HOPPER_RECOVERY_ISO_READY sha256=%s source_sha256=%s\n' \
    "$output_sha256" "$source_sha256"
