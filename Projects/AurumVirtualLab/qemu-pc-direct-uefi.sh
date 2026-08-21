#!/usr/bin/env bash
set -euo pipefail

IMAGE=${1:?usage: qemu-pc-direct-uefi.sh IMAGE LOG}
LOG=${2:?usage: qemu-pc-direct-uefi.sh IMAGE LOG}

if [ -f /usr/share/OVMF/OVMF_CODE.fd ] && [ -f /usr/share/OVMF/OVMF_VARS.fd ]; then
  code=/usr/share/OVMF/OVMF_CODE.fd
  vars=/usr/share/OVMF/OVMF_VARS.fd
elif [ -f /usr/share/OVMF/OVMF_CODE_4M.fd ] && [ -f /usr/share/OVMF/OVMF_VARS_4M.fd ]; then
  code=/usr/share/OVMF/OVMF_CODE_4M.fd
  vars=/usr/share/OVMF/OVMF_VARS_4M.fd
else
  echo 'No matching OVMF CODE/VARS pair found.' >&2
  exit 1
fi

for tool in qemu-system-x86_64 sha256sum; do
  command -v "$tool" >/dev/null || { echo "missing tool: $tool" >&2; exit 2; }
done
[ -s "$IMAGE" ] || { echo "direct UEFI image is missing: $IMAGE" >&2; exit 2; }

work_dir=$(mktemp -d /tmp/aurum-direct-uefi-qemu.XXXXXX)
ovmf_vars="$work_dir/OVMF_VARS.fd"
serial_input="$work_dir/input"
cp "$vars" "$ovmf_vars"
mkfifo "$serial_input"
exec 3<>"$serial_input"
: > "$LOG"
qemu_pid=

cleanup() {
  if [ -n "${qemu_pid:-}" ] && kill -0 "$qemu_pid" 2>/dev/null; then
    kill "$qemu_pid" 2>/dev/null || true
    wait "$qemu_pid" 2>/dev/null || true
  fi
  exec 3>&-
  rm -rf "$work_dir"
}
trap cleanup EXIT

wait_for_marker() {
  local marker=$1
  local attempts=$2
  for _ in $(seq 1 "$attempts"); do
    grep -Fq "$marker" "$LOG" && return 0
    kill -0 "$qemu_pid" 2>/dev/null || return 1
    sleep 1
  done
  return 1
}

# Boot the raw GPT image as removable USB media. There is no CD/ISO device and
# no GRUB command path in this test: OVMF must execute EFI/BOOT/BOOTX64.EFI from
# the FAT ESP, the UKI must hand off its embedded kernel+initrd, and live-boot
# must find the /live filesystem on the image's data partition.
timeout 300s qemu-system-x86_64 \
  -machine q35,accel=tcg \
  -cpu qemu64 \
  -m 2048 \
  -smp 2 \
  -drive if=pflash,format=raw,readonly=on,file="$code" \
  -drive if=pflash,format=raw,file="$ovmf_vars" \
  -device qemu-xhci,id=xhci \
  -drive if=none,id=seed,file="$IMAGE",format=raw,readonly=on \
  -device usb-storage,drive=seed,bootindex=1 \
  -netdev user,id=net0,restrict=on \
  -device e1000e,netdev=net0 \
  -boot strict=on \
  -display none \
  -serial stdio \
  -no-reboot \
  <&3 >> "$LOG" 2>&1 &
qemu_pid=$!

if ! wait_for_marker 'AURUM_PC_READY version=0.01 arch=x86_64' 210; then
  cat "$LOG"
  echo 'Direct UEFI seed did not reach Aurum runtime.' >&2
  exit 1
fi
if ! grep -Fq 'AURUM_HARDWARE_PROFILE status=ready' "$LOG"; then
  cat "$LOG"
  echo 'Direct UEFI seed reached runtime without hardware-profile readiness.' >&2
  exit 1
fi

printf 'poweroff\n' >&3
set +e
wait "$qemu_pid"
status=$?
set -e
qemu_pid=
if [ "$status" -ne 0 ]; then
  cat "$LOG"
  echo "Direct UEFI QEMU exited unexpectedly with status $status" >&2
  exit "$status"
fi

printf '%s\n' \
  'AURUM_DIRECT_UEFI_USB_BOOT_OK' \
  'AURUM_DIRECT_UEFI_GRUB_INDEPENDENT_OK' \
  >> "$LOG"
cat "$LOG"
