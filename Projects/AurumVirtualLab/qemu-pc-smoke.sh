#!/usr/bin/env bash
set -euo pipefail

ISO=${1:?usage: qemu-pc-smoke.sh ISO LOG}
LOG=${2:?usage: qemu-pc-smoke.sh ISO LOG}
QEMU_ACCEL=${AURUM_QEMU_ACCEL:-tcg}
case "$QEMU_ACCEL" in
  kvm|tcg) ;;
  *) echo "Unsupported Aurum QEMU accelerator: $QEMU_ACCEL" >&2; exit 2 ;;
esac

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

work_dir=$(mktemp -d /tmp/aurum-vlab-pc.XXXXXX)
ovmf_vars="$work_dir/OVMF_VARS.fd"
installed_disk="$work_dir/aurum-installed.raw"
serial_input="$work_dir/input"
cp "$vars" "$ovmf_vars"
truncate -s 10G "$installed_disk"
mkfifo "$serial_input"
exec 3<>"$serial_input"
: > "$LOG"
echo "AURUM_QEMU_ACCELERATION selected=$QEMU_ACCEL" >> "$LOG"
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

start_live_qemu() {
  timeout 900s qemu-system-x86_64 \
    -machine "q35,accel=$QEMU_ACCEL" \
    -cpu qemu64 \
    -m 1024 \
    -smp 2 \
    -drive if=pflash,format=raw,readonly=on,file="$code" \
    -drive if=pflash,format=raw,file="$ovmf_vars" \
    -drive file="$installed_disk",format=raw,if=virtio \
    -cdrom "$ISO" \
    -boot order=d \
    -display none \
    -serial stdio \
    -monitor none \
    -no-reboot \
    <&3 >> "$LOG" 2>&1 &
  qemu_pid=$!
}

start_installed_qemu() {
  printf '\n===== AURUM INSTALLED DISK BOOT =====\n' >> "$LOG"
  timeout 900s qemu-system-x86_64 \
    -machine "q35,accel=$QEMU_ACCEL" \
    -cpu qemu64 \
    -m 1024 \
    -smp 2 \
    -drive if=pflash,format=raw,readonly=on,file="$code" \
    -drive if=pflash,format=raw,file="$ovmf_vars" \
    -drive file="$installed_disk",format=raw,if=virtio \
    -boot order=c \
    -display none \
    -serial stdio \
    -monitor none \
    -no-reboot \
    <&3 >> "$LOG" 2>&1 &
  qemu_pid=$!
}

wait_for_marker() {
  marker=$1
  attempts=$2
  for _ in $(seq 1 "$attempts"); do
    if grep -Fq "$marker" "$LOG"; then
      return 0
    fi
    if ! kill -0 "$qemu_pid" 2>/dev/null; then
      return 1
    fi
    sleep 1
  done
  return 1
}

wait_for_install() {
  attempts=$1
  for _ in $(seq 1 "$attempts"); do
    if grep -Fq 'AURUM_INSTALL_FINISHED status=passed' "$LOG"; then
      return 0
    fi
    if grep -Fq 'AURUM_INSTALL_FINISHED status=refused' "$LOG"; then
      return 1
    fi
    if ! kill -0 "$qemu_pid" 2>/dev/null; then
      return 1
    fi
    sleep 1
  done
  return 1
}

wait_for_self_build() {
  attempts=$1
  for _ in $(seq 1 "$attempts"); do
    if grep -Fq 'AURUM_SELF_BUILD_FINISHED status=passed' "$LOG"; then
      return 0
    fi
    if grep -Eq 'AURUM_SELF_BUILD_FINISHED status=(failed|cancelled)' "$LOG"; then
      return 1
    fi
    if ! kill -0 "$qemu_pid" 2>/dev/null; then
      return 1
    fi
    sleep 1
  done
  return 1
}

finish_qemu() {
  set +e
  wait "$qemu_pid"
  status=$?
  set -e
  qemu_pid=
  if [ "$status" -ne 0 ]; then
    cat "$LOG"
    echo "QEMU PC exited unexpectedly with status $status" >&2
    exit "$status"
  fi
}

start_live_qemu
if ! wait_for_marker 'AURUM_PC_READY version=0.01 arch=x86_64' 180 || \
   ! grep -Fq 'mode=live' "$LOG" || \
   ! grep -Fq 'selftest=ok' "$LOG"; then
  cat "$LOG"
  echo 'Aurum PC did not reach its UEFI live-runtime marker.' >&2
  exit 1
fi

printf 'install\n' >&3
if ! wait_for_marker 'AURUM_INSTALL_PLAN status=ready' 60; then
  cat "$LOG"
  echo 'Aurum PC did not expose a guided install plan.' >&2
  exit 1
fi
confirmation=$(
  sed -n 's/^AURUM_INSTALL_TARGET .*confirm=\(ERASE-[A-F0-9]\{8\}\).*$/\1/p' "$LOG" |
    tail -n 1
)
if [ -z "$confirmation" ]; then
  cat "$LOG"
  echo 'Aurum PC install plan did not provide a bounded confirmation code.' >&2
  exit 1
fi
printf 'install confirm %s\n' "$confirmation" >&3
if ! wait_for_install 600; then
  cat "$LOG"
  echo 'Aurum PC guided installation did not pass.' >&2
  exit 1
fi

printf 'poweroff\n' >&3
finish_qemu

start_installed_qemu
if ! wait_for_marker 'mode=installed' 180 || \
   ! grep -Fq 'AURUM_PC_READY version=0.01 arch=x86_64' "$LOG" || \
   ! grep -Fq 'selftest=ok' "$LOG"; then
  cat "$LOG"
  echo 'The installed Aurum disk did not reach its UEFI runtime-ready marker.' >&2
  exit 1
fi

printf 'self-build\n' >&3
if ! wait_for_self_build 720; then
  cat "$LOG"
  echo 'Aurum PC installed-runtime self-build did not pass.' >&2
  exit 1
fi

printf 'poweroff\n' >&3
finish_qemu

trap - EXIT
exec 3>&-
cat "$LOG"
grep -F 'AURUM_PC_READY version=0.01 arch=x86_64' "$LOG"
grep -F 'mode=live' "$LOG"
grep -F 'AURUM_INSTALL_PLAN status=ready' "$LOG"
grep -F 'AURUM_INSTALL_FINISHED status=passed' "$LOG"
grep -F 'mode=installed' "$LOG"
grep -F 'AURUM_SELF_BUILD_FINISHED status=passed' "$LOG"
echo 'AURUM_VIRTUAL_PC_UEFI_RUNTIME_SELF_BUILD_OK'
echo 'AURUM_VIRTUAL_PC_UEFI_INSTALL_AND_SELF_BUILD_OK'
rm -rf "$work_dir"
