#!/bin/sh
set -eu

usage() {
    echo "usage: $0 SOURCE_LIVE_ISO OUTPUT_ISO EXPECTED_HOPPER_HEAD" >&2
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

kernel_candidates=$(xorriso -indev "$source_iso" \
    -find /live -type f -name 'vmlinuz*' -exec echo -- -end 2>/dev/null \
    | sed -n "s|^'\(/live/vmlinuz[^']*\)'$|\1|p")
kernel_path=$(printf '%s\n' "$kernel_candidates" \
    | awk '/^\/live\/vmlinuz-/{candidate=$0} END{print candidate}')
[ -n "$kernel_path" ] || kernel_path=/live/vmlinuz
echo "$kernel_path" | grep -Eq '^/live/vmlinuz[-A-Za-z0-9.+_]*$' \
    || { echo "source live kernel path is unsafe" >&2; exit 2; }
kernel_suffix=${kernel_path#/live/vmlinuz}
initrd_path=/live/initrd.img$kernel_suffix
echo "$initrd_path" | grep -Eq '^/live/initrd\.img[-A-Za-z0-9.+_]*$' \
    || { echo "source live initrd path is unsafe" >&2; exit 2; }

xorriso -osirrox on -indev "$source_iso" \
    -extract "$kernel_path" "$build_root/source-vmlinuz" \
    -extract "$initrd_path" "$build_root/source-initrd.img" \
    -end >/dev/null

python3 - "$build_root/source-vmlinuz" "$kernel_path" <<'PY'
from pathlib import Path
import struct
import sys

path = Path(sys.argv[1])
label = sys.argv[2]
data = path.read_bytes()
if len(data) < 0x40 or data[:2] != b"MZ":
    raise SystemExit(f"source live kernel is not a signed EFI-loadable image: {label}")
pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
if pe_offset + 24 > len(data) or data[pe_offset:pe_offset + 4] != b"PE\0\0":
    raise SystemExit(f"source live kernel has no PE header: {label}")
optional = pe_offset + 24
magic = struct.unpack_from("<H", data, optional)[0]
if magic == 0x20B:
    directories = optional + 112
elif magic == 0x10B:
    directories = optional + 96
else:
    raise SystemExit(f"source live kernel has an unknown PE format: {label}")
certificate_offset, certificate_size = struct.unpack_from(
    "<II", data, directories + (4 * 8)
)
if (
    certificate_offset == 0
    or certificate_size < 8
    or certificate_offset + certificate_size > len(data)
):
    raise SystemExit(
        f"source live kernel is unsigned; refusing a Secure Boot recovery image: {label}"
    )
print(
    "SIGNED_KERNEL_PROVEN "
    f"path={label} certificate_bytes={certificate_size}"
)
PY

sed \
    -e "s|@KERNEL_LIVE@|$kernel_path|g" \
    -e "s|@INITRD_LIVE@|$initrd_path|g" \
    "$script_dir/recovery-assets/grub.cfg" >"$build_root/grub.cfg"
sed \
    -e "s|@KERNEL_LIVE@|$kernel_path|g" \
    -e "s|@INITRD_LIVE@|$initrd_path|g" \
    "$script_dir/recovery-assets/isolinux.cfg" >"$build_root/isolinux.cfg"

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
    -map "$build_root/grub.cfg" /boot/grub/grub.cfg \
    -map "$build_root/isolinux.cfg" /isolinux/isolinux.cfg \
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
