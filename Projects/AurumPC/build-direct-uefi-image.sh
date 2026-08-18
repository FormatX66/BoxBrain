#!/bin/sh
set -eu

BINARY_DIR=${1:?usage: build-direct-uefi-image.sh LIVE_BUILD_BINARY OUTPUT_IMAGE}
OUTPUT_IMAGE=${2:?usage: build-direct-uefi-image.sh LIVE_BUILD_BINARY OUTPUT_IMAGE}
OUTPUT_DIR=$(dirname "$OUTPUT_IMAGE")
OUTPUT_NAME=$(basename "$OUTPUT_IMAGE")
OUTPUT_PARENT=$(dirname "$OUTPUT_DIR")
OUTPUT_DIR_NAME=$(basename "$OUTPUT_DIR")

for tool in parted mkfs.vfat mkfs.ext4 mmd mcopy objcopy truncate sha256sum dd du find head wc tr cp mkdir rm; do
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

# Keep the PE section layout bounded and reject overlap during construction.
KERNEL_BYTES=$(wc -c < "$KERNEL" | tr -d ' ')
MAX_KERNEL_BYTES=$((32 * 1024 * 1024))
if [ "$KERNEL_BYTES" -ge "$MAX_KERNEL_BYTES" ]; then
  echo "kernel is too large for the bounded UKI section layout: $KERNEL_BYTES bytes" >&2
  exit 1
fi

WORK_DIR=$(mktemp -d /tmp/aurum-direct-uefi.XXXXXX)
OSREL="$WORK_DIR/os-release"
CMDLINE="$WORK_DIR/cmdline"
UKI="$WORK_DIR/BOOTX64.EFI"
ESP_IMAGE="$WORK_DIR/esp.img"
DATA_IMAGE="$WORK_DIR/data.img"
DATA_ROOT="$WORK_DIR/data-root"
mkdir -p "$DATA_ROOT" "$OUTPUT_DIR"

cleanup() {
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

objcopy \
  --add-section .osrel="$OSREL" --change-section-vma .osrel=0x20000 \
  --add-section .cmdline="$CMDLINE" --change-section-vma .cmdline=0x30000 \
  --add-section .linux="$KERNEL" --change-section-vma .linux=0x2000000 \
  --add-section .initrd="$INITRD" --change-section-vma .initrd=0x4000000 \
  "$STUB" "$UKI"

# Build each filesystem as an ordinary file. This deliberately avoids loop
# devices, udev-created partition nodes, mount namespaces, and host kernel
# filesystem state. The same byte-for-byte partition images can therefore be
# assembled in Docker, GitHub Actions, recovery environments, or a normal host.
ESP_MIB=256
truncate -s "${ESP_MIB}M" "$ESP_IMAGE"
mkfs.vfat -F 32 -n AURUMEFI "$ESP_IMAGE" >/dev/null
mmd -i "$ESP_IMAGE" ::/EFI
mmd -i "$ESP_IMAGE" ::/EFI/BOOT
mmd -i "$ESP_IMAGE" ::/EFI/Linux
mcopy -i "$ESP_IMAGE" "$UKI" ::/EFI/BOOT/BOOTX64.EFI
mcopy -i "$ESP_IMAGE" "$UKI" ::/EFI/Linux/aurum-v0.01.efi

cp -a "$BINARY_DIR"/. "$DATA_ROOT"/
cat > "$DATA_ROOT/aurum-direct-uefi.txt" <<'EOF'
AURUM_DIRECT_UEFI version=0.01
boot_contract=firmware->BOOTX64.EFI(UKI)->kernel+initrd->live-media-scan->/live/filesystem.squashfs
fallback_contract=independent-from-grub-iso-hybrid-path
construction_contract=file-native-no-loop-no-mount
secure_boot=unsigned-test-seed
EOF

BINARY_KIB=$(du -sk "$DATA_ROOT" | awk '{print $1}')
DATA_MIB=$(( (BINARY_KIB + 1023) / 1024 + 192 ))
truncate -s "${DATA_MIB}M" "$DATA_IMAGE"
mkfs.ext4 -q -F -L AURUM_LIVE -d "$DATA_ROOT" "$DATA_IMAGE"

# Assemble a GPT disk after the filesystems are complete. Leave four MiB after
# the live partition so writing the filesystem image can never overlap the GPT
# backup header/table at the physical end of the disk.
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

# Record a checksum path relative to the output directory's parent. This keeps
# the checksum portable across the privileged build container and the host
# workspace that verifies and publishes the artifact.
(
  cd "$OUTPUT_PARENT"
  sha256sum "$OUTPUT_DIR_NAME/$OUTPUT_NAME" > "$OUTPUT_DIR_NAME/$OUTPUT_NAME.sha256"
)
ls -lh "$OUTPUT_IMAGE" "$OUTPUT_IMAGE.sha256"
