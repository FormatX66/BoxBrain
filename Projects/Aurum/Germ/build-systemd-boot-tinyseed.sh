#!/bin/sh
set -eu

BINARY_DIR=${1:?usage: build-systemd-boot-tinyseed.sh LIVE_BUILD_BINARY OUTPUT_IMAGE}
OUTPUT_IMAGE=${2:?usage: build-systemd-boot-tinyseed.sh LIVE_BUILD_BINARY OUTPUT_IMAGE}
OUTPUT_DIR=$(dirname "$OUTPUT_IMAGE")
OUTPUT_NAME=$(basename "$OUTPUT_IMAGE")
OUTPUT_PARENT=$(dirname "$OUTPUT_DIR")
OUTPUT_DIR_NAME=$(basename "$OUTPUT_DIR")

for tool in parted mkfs.vfat mkfs.ext4 mmd mcopy truncate sha256sum dd du find head wc tr cp mkdir rm awk; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "missing systemd-boot Tiny Seed build dependency: $tool" >&2
    exit 2
  }
done

BOOTLOADER=/usr/lib/systemd/boot/efi/systemd-bootx64.efi
if [ ! -s "$BOOTLOADER" ]; then
  echo "missing x86_64 systemd-boot EFI binary: $BOOTLOADER (install systemd-boot-efi)" >&2
  exit 2
fi
if [ ! -d "$BINARY_DIR/live" ]; then
  echo "live-build binary tree is missing $BINARY_DIR/live" >&2
  exit 2
fi

KERNEL=$(find "$BINARY_DIR/live" -maxdepth 1 -name 'vmlinuz*' -print | head -n 1)
INITRD=$(find "$BINARY_DIR/live" -maxdepth 1 \( -name 'initrd*.img' -o -name 'initrd*' \) -print | head -n 1)
SQUASH=$(find "$BINARY_DIR/live" -maxdepth 1 -name 'filesystem.squashfs' -print | head -n 1)
for item in "$KERNEL" "$INITRD" "$SQUASH"; do
  if [ -z "${item:-}" ] || [ ! -s "$item" ]; then
    echo "systemd-boot Tiny Seed input is missing from $BINARY_DIR/live" >&2
    exit 1
  fi
done

WORK_DIR=$(mktemp -d /tmp/aurum-tinyseed-systemd-boot.XXXXXX)
ESP_IMAGE="$WORK_DIR/esp.img"
DATA_IMAGE="$WORK_DIR/data.img"
DATA_ROOT="$WORK_DIR/data-root"
LOADER_CONF="$WORK_DIR/loader.conf"
ENTRY_CONF="$WORK_DIR/aurum.conf"
mkdir -p "$DATA_ROOT" "$OUTPUT_DIR"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT HUP INT TERM

cat > "$LOADER_CONF" <<'EOF'
default aurum.conf
timeout 3
console-mode keep
editor no
EOF

cat > "$ENTRY_CONF" <<'EOF'
title Aurum Tiny Seed
linux /EFI/Aurum/vmlinuz.efi
initrd /EFI/Aurum/initrd.img
options boot=live components edd=off quiet live-media-path=/live console=tty0 console=ttyS0,115200n8
EOF

# This fallback deliberately avoids the systemd-stub UKI -> inner-kernel handoff
# that previously returned EFI_INVALID_PARAMETER on physical HP firmware. The
# firmware starts systemd-boot, and systemd-boot starts the Debian kernel's own
# EFI stub as a file on the ESP with a separate initrd.
ESP_MIB=384
truncate -s "${ESP_MIB}M" "$ESP_IMAGE"
mkfs.vfat -F 32 -n AURUMEFI "$ESP_IMAGE" >/dev/null
mmd -i "$ESP_IMAGE" ::/EFI
mmd -i "$ESP_IMAGE" ::/EFI/BOOT
mmd -i "$ESP_IMAGE" ::/EFI/Aurum
mmd -i "$ESP_IMAGE" ::/loader
mmd -i "$ESP_IMAGE" ::/loader/entries
mcopy -i "$ESP_IMAGE" "$BOOTLOADER" ::/EFI/BOOT/BOOTX64.EFI
mcopy -i "$ESP_IMAGE" "$KERNEL" ::/EFI/Aurum/vmlinuz.efi
mcopy -i "$ESP_IMAGE" "$INITRD" ::/EFI/Aurum/initrd.img
mcopy -i "$ESP_IMAGE" "$LOADER_CONF" ::/loader/loader.conf
mcopy -i "$ESP_IMAGE" "$ENTRY_CONF" ::/loader/entries/aurum.conf

cp -a "$BINARY_DIR"/. "$DATA_ROOT"/
cat > "$DATA_ROOT/aurum-systemd-boot.txt" <<'EOF'
AURUM_TINYSEED_SYSTEMD_BOOT version=1
status=experimental-fallback-not-current-release
boot_contract=firmware->systemd-boot->kernel-EFI-stub+separate-initrd->live-media-scan->/live/filesystem.squashfs
fallback_contract=independent-from-grub-iso-hybrid-and-systemd-stub-UKI-inner-kernel-path
recovery_contract=carry-the-same-verified-offline-phenotype-and-protected-germ-as-current-x86-seed
construction_contract=file-native-no-loop-no-mount
secure_boot=unsigned-experimental-seed
known_physical_reason=avoid-prior-HP-EFI_INVALID_PARAMETER-at-systemd-stub-inner-kernel-start
EOF

BINARY_KIB=$(du -sk "$DATA_ROOT" | awk '{print $1}')
DATA_MIB=$(( (BINARY_KIB + 1023) / 1024 + 192 ))
truncate -s "${DATA_MIB}M" "$DATA_IMAGE"
mkfs.ext4 -q -F -L AURUM_LIVE -d "$DATA_ROOT" "$DATA_IMAGE"

DATA_START_MIB=$((1 + ESP_MIB))
DATA_END_MIB=$((DATA_START_MIB + DATA_MIB))
TOTAL_MIB=$((DATA_END_MIB + 4))
rm -f "$OUTPUT_IMAGE" "$OUTPUT_IMAGE.sha256"
truncate -s "${TOTAL_MIB}M" "$OUTPUT_IMAGE"
parted -s "$OUTPUT_IMAGE" mklabel gpt
parted -s "$OUTPUT_IMAGE" mkpart ESP fat32 1MiB "${DATA_START_MIB}MiB"
parted -s "$OUTPUT_IMAGE" set 1 esp on
parted -s "$OUTPUT_IMAGE" mkpart AURUM_LIVE ext4 "${DATA_START_MIB}MiB" "${DATA_END_MIB}MiB"

dd if="$ESP_IMAGE" of="$OUTPUT_IMAGE" bs=1M seek=1 conv=notrunc status=none
dd if="$DATA_IMAGE" of="$OUTPUT_IMAGE" bs=1M seek="$DATA_START_MIB" conv=notrunc status=none

(
  cd "$OUTPUT_PARENT"
  sha256sum "$OUTPUT_DIR_NAME/$OUTPUT_NAME" > "$OUTPUT_DIR_NAME/$OUTPUT_NAME.sha256"
)

echo "AURUM_TINYSEED_SYSTEMD_BOOT_BUILD_OK image=$OUTPUT_IMAGE data_start_mib=$DATA_START_MIB"
ls -lh "$OUTPUT_IMAGE" "$OUTPUT_IMAGE.sha256"
