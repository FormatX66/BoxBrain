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
serial_dir=$(mktemp -d /tmp/aurum-vlab-serial.XXXXXX)
serial_input="$serial_dir/input"
mkfifo "$serial_input"
exec 3<>"$serial_input"

set +e
timeout 180s qemu-system-x86_64 \
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
  <&3 > "$LOG" 2>&1 &
qemu_pid=$!
set -e

cleanup() {
  if kill -0 "$qemu_pid" 2>/dev/null; then
    kill "$qemu_pid" 2>/dev/null || true
    wait "$qemu_pid" 2>/dev/null || true
  fi
  exec 3>&-
}
trap cleanup EXIT

ready=false
for _ in $(seq 1 120); do
  if grep -Fq 'AURUM_PC_READY version=0.01 arch=x86_64' "$LOG" && grep -Fq 'selftest=ok' "$LOG"; then
    ready=true
    break
  fi
  if ! kill -0 "$qemu_pid" 2>/dev/null; then
    break
  fi
  sleep 1
done
if [ "$ready" != true ]; then
  cat "$LOG"
  echo 'Aurum PC did not reach its UEFI runtime-ready marker.' >&2
  exit 1
fi

printf 'self-build\n' >&3
self_build=false
for _ in $(seq 1 120); do
  if grep -Fq 'AURUM_SELF_BUILD_FINISHED status=passed' "$LOG"; then
    self_build=true
    break
  fi
  if grep -Fq 'AURUM_SELF_BUILD_FINISHED status=failed' "$LOG"; then
    break
  fi
  if ! kill -0 "$qemu_pid" 2>/dev/null; then
    break
  fi
  sleep 1
done
if [ "$self_build" != true ]; then
  cat "$LOG"
  echo 'Aurum PC on-machine self-build did not pass.' >&2
  exit 1
fi

printf 'poweroff\n' >&3
set +e
wait "$qemu_pid"
status=$?
set -e
trap - EXIT
exec 3>&-
cat "$LOG"
grep -F 'AURUM_PC_READY version=0.01 arch=x86_64' "$LOG"
grep -F 'selftest=ok' "$LOG"
grep -F 'AURUM_SELF_BUILD_FINISHED status=passed' "$LOG"
if [ "$status" -ne 0 ]; then
  echo "QEMU PC exited unexpectedly with status $status" >&2
  exit "$status"
fi
echo 'AURUM_VIRTUAL_PC_UEFI_RUNTIME_SELF_BUILD_OK'
