#!/bin/sh
set -eu

BINARY_DIR=${1:?usage: build-direct-uefi-image.sh LIVE_BUILD_BINARY OUTPUT_IMAGE}
OUTPUT_IMAGE=${2:?usage: build-direct-uefi-image.sh LIVE_BUILD_BINARY OUTPUT_IMAGE}

if [ "$(id -u)" -ne 0 ]; then
  echo "direct UEFI image build requires root for loop/mount operations" >&2
  exit 2
fi

for tool in parted losetup mkfs.vfat mkfs.ext4 mount umount objcopy truncate sha256sum awk; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "missing direct UEFI build dependency: $tool" >&2
    exit 2
  }
done

STUB=/usr/lib/systemd/boot/efi/linuxx64.efi.stub
if [ ! -s "$STUB" ]; then
  echo "missing x86_64 systemd UEFI stub: $STUB (install systemd-boot-efi)" >&2
  exit 2
fi
if [ ! -d "$BINARY_DIR/live" ]; then
  echo "live-build binary tree is missing $BINARY_DIR/live" >&2
  exit 2
fi

KERNEL=$(find "$BINARY_DIR/live" -maxdepth 1 -name 'vmlinuz*' -print | head -n 1)
INITRD=$(find "$BINARY_DIR/live" -maxdepth 1 \( -name 'initrd*.img' -o -name 'initrd*' \) -print | head -n 1)
if [ -z "${KERNEL:-}" ] || [ ! -s "$KERNEL" ]; then
  echo "could not locate live kernel in $BINARY_DIR/live" >&2
  exit 1
fi
if [ -z "${INITRD:-}" ] || [ ! -s "$INITRD" ]; then
  echo "could not locate live initrd in $BINARY_DIR/live" >&2
  exit 1
fi

# The bookworm systemd-stub assembly layout reserves 32 MiB between the Linux
# and initrd sections. Refuse to make an overlapping PE image if a future
# kernel grows beyond that contract; the failure then becomes a build variable,
# not an intermittently unbootable physical seed.
KERNEL_BYTES=$(wc -c < "$KERNEL" | tr -d ' ')
MAX_KERNEL_BYTES=$((32 * 1024 * 1024))
if [ "$KERNEL_BYTES" -ge "$MAX_KERNEL_BYTES" ]; then
  echo "kernel is too large for the bounded UKI section layout: $KERNEL_BYTES bytes" >&2
  exit 1
fi

WORK_DIR=$(mktemp -d /tmp/aurum-direct-uefi.XXXXXX)
ESP_LOOP=
DATA_LOOP=
ESP_MOUNT="$WORK_DIR/esp"
DATA_MOUNT="$WORK_DIR/data"
OSREL="$WORK_DIR/os-release"
CMDLINE="$WORK_DIR/cmdline"
mkdir -p "$ESP_MOUNT" "$DATA_MOUNT" "$(dirname "$OUTPUT_IMAGE")"

cleanup() {
  set +e
  if mountpoint -q "$ESP_MOUNT" 2>/dev/null; then umount "$ESP_MOUNT"; fi
  if mountpoint -q "$DATA_MOUNT" 2>/dev/null; then umount "$DATA_MOUNT"; fi
  if [ -n "${ESP_LOOP:-}" ]; then losetup -d "$ESP_LOOP" 2>/dev/null || true; fi
  if [ -n "${DATA_LOOP:-}" ]; then losetup -d "$DATA_LOOP" 2>/dev/null || true; fi
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT HUP INT TERM

cat > "$OSREL" <<'EOF'
NAME="Aurum PC"
ID=aurum
VERSION="0.01"
VERSION_ID="0.01"
PRETTY_NAME="Aurum PC v0.01 direct UEFI seed"
EOF

cat > "$CMDLINE" <<'EOF'
boot=live components quiet preempt=voluntary transparent_hugepage=madvise live-media-path=/live console=tty0 console=ttyS0,115200n8
EOF

# Size the raw image from the actual live-build tree. The 256 MiB ESP is kept
# deliberately simple; the rest is a normal ext4 live-media partition. This
# removes the hybrid-ISO/GRUB filesystem-discovery dependency from the direct
# UEFI path while preserving the existing ISO as an independent fallback.
BINARY_KIB=$(du -sk "$BINARY_DIR" | awk '{print $1}')
DATA_MIB=$(( (BINARY_KIB + 1023) / 1024 + 192 ))
ESP_MIB=256
TOTAL_MIB=$((1 + ESP_MIB + DATA_MIB))
rm -f "$OUTPUT_IMAGE" "$OUTPUT_IMAGE.sha256"
truncate -s "${TOTAL_MIB}M" "$OUTPUT_IMAGE"
parted -s "$OUTPUT_IMAGE" mklabel gpt
parted -s "$OUTPUT_IMAGE" mkpart ESP fat32 1MiB 257MiB
parted -s "$OUTPUT_IMAGE" set 1 esp on
parted -s "$OUTPUT_IMAGE" mkpart AURUM_LIVE ext4 257MiB 100%

# Do not depend on kernel-created /dev/loopXpN partition nodes. Minimal CI and
# recovery environments may not have udev running, so --partscan can succeed
# while the partition device nodes never materialize. Read the exact partition
# byte ranges from the GPT and bind each range to its own loop device instead.
# This preserves the raw GPT image while removing udev/device-manager timing as
# a build dependency.
PARTITION_TABLE=$(parted -sm "$OUTPUT_IMAGE" unit B print)
ESP_RANGE=$(printf '%s\n' "$PARTITION_TABLE" | awk -F: '$1=="1" {gsub(/B/,"",$2); gsub(/B/,"",$4); print $2, $4}')
DATA_RANGE=$(printf '%s\n' "$PARTITION_TABLE" | awk -F: '$1=="2" {gsub(/B/,"",$2); gsub(/B/,"",$4); print $2, $4}')
set -- $ESP_RANGE
ESP_OFFSET=${1:-}
ESP_SIZE=${2:-}
set -- $DATA_RANGE
DATA_OFFSET=${1:-}
DATA_SIZE=${2:-}
if [ -z "$ESP_OFFSET" ] || [ -z "$ESP_SIZE" ] || [ -z "$DATA_OFFSET" ] || [ -z "$DATA_SIZE" ]; then
  echo "could not resolve GPT partition byte ranges" >&2
  printf '%s\n' "$PARTITION_TABLE" >&2
  exit 1
fi

ESP_LOOP=$(losetup --find --show --offset "$ESP_OFFSET" --sizelimit "$ESP_SIZE" "$OUTPUT_IMAGE")
DATA_LOOP=$(losetup --find --show --offset "$DATA_OFFSET" --sizelimit "$DATA_SIZE" "$OUTPUT_IMAGE")

mkfs.vfat -F 32 -n AURUMEFI "$ESP_LOOP" >/dev/null
mkfs.ext4 -F -L AURUM_LIVE "$DATA_LOOP" >/dev/null
mount "$ESP_LOOP" "$ESP_MOUNT"
mount "$DATA_LOOP" "$DATA_MOUNT"

# Carry the complete live-build binary tree so live-boot sees /live together
# with its generated .disk metadata/UUID instead of relying on guessed device
# names. The kernel/initrd themselves are also embedded in the UKI below.
cp -a "$BINARY_DIR"/. "$DATA_MOUNT"/
mkdir -p "$ESP_MOUNT/EFI/BOOT" "$ESP_MOUNT/EFI/Linux"

objcopy \
  --add-section .osrel="$OSREL" --change-section-vma .osrel=0x20000 \
  --add-section .cmdline="$CMDLINE" --change-section-vma .cmdline=0x30000 \
  --add-section .linux="$KERNEL" --change-section-vma .linux=0x2000000 \
  --add-section .initrd="$INITRD" --change-section-vma .initrd=0x4000000 \
  "$STUB" "$ESP_MOUNT/EFI/BOOT/BOOTX64.EFI"
cp "$ESP_MOUNT/EFI/BOOT/BOOTX64.EFI" "$ESP_MOUNT/EFI/Linux/aurum-v0.01.efi"

cat > "$DATA_MOUNT/aurum-direct-uefi.txt" <<EOF
AURUM_DIRECT_UEFI version=0.01
boot_contract=firmware->BOOTX64.EFI(UKI)->kernel+initrd->live-media-scan->/live/filesystem.squashfs
fallback_contract=independent-from-grub-iso-hybrid-path
secure_boot=unsigned-test-seed
EOF

sync
umount "$ESP_MOUNT"
umount "$DATA_MOUNT"
losetup -d "$ESP_LOOP"
ESP_LOOP=
losetup -d "$DATA_LOOP"
DATA_LOOP=
sha256sum "$OUTPUT_IMAGE" > "$OUTPUT_IMAGE.sha256"
ls -lh "$OUTPUT_IMAGE" "$OUTPUT_IMAGE.sha256"
