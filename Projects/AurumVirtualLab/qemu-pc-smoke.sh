#!/usr/bin/env bash
set -euo pipefail

ISO=${1:?usage: qemu-pc-smoke.sh ISO LOG}
LOG=${2:?usage: qemu-pc-smoke.sh ISO LOG}

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

cp "$vars" /tmp/AURUM_VLAB_OVMF_VARS.fd
set +e
timeout 150s qemu-system-x86_64 \
  -machine q35,accel=tcg \
  -cpu qemu64 \
  -m 1024 \
  -smp 2 \
  -drive if=pflash,format=raw,readonly=on,file="$code" \
  -drive if=pflash,format=raw,file=/tmp/AURUM_VLAB_OVMF_VARS.fd \
  -cdrom "$ISO" \
  -boot d \
  -display none \
  -serial stdio \
  -monitor none \
  -no-reboot \
  > "$LOG" 2>&1
status=$?
set -e
cat "$LOG"
grep -F 'AURUM_PC_READY version=0.01 arch=x86_64' "$LOG"
grep -F 'selftest=ok' "$LOG"
if [ "$status" -ne 0 ] && [ "$status" -ne 124 ]; then
  echo "QEMU PC exited unexpectedly with status $status" >&2
  exit "$status"
fi
echo 'AURUM_VIRTUAL_PC_UEFI_OK'
