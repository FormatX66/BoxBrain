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
# Keep the VM otherwise generic, but present Hopper's already-authorized target
# identity so the machine-bound physical GUI and Remote Desktop can be proved
# without adding a production-only CI bypass. The raw file remains sparse.
truncate -s 512110190592 "$installed_disk"
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
    -drive if=none,id=installed,file="$installed_disk",format=raw \
    -device virtio-blk-pci,drive=installed,serial=BTTE934116YM512B-1 \
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
    -drive if=none,id=installed,file="$installed_disk",format=raw \
    -device virtio-blk-pci,drive=installed,serial=BTTE934116YM512B-1 \
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

wait_for_remote_transport() {
  for _ in $(seq 1 60); do
    printf 'remote-status\n' >&3
    sleep 1
    if grep -Fq 'AURUM_REMOTE status=pairing-required action=status desktop=stopped' "$LOG" && \
       grep -Fq '"ssh_service": "active"' "$LOG" && \
       grep -Fq 'raw_shell=false' "$LOG"; then
      return 0
    fi
    if ! kill -0 "$qemu_pid" 2>/dev/null; then
      return 1
    fi
  done
  return 1
}

start_remote_desktop() {
  for _ in $(seq 1 8); do
    printf 'remote-desktop-start\n' >&3
    if wait_for_marker 'AURUM_REMOTE status=running action=desktop-start desktop=running loopback=true raw_shell=false' 25; then
      return 0
    fi
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

# The installed seed must expose only the restricted remote identity, then
# prove the actual physical GUI can be viewed through VNC + noVNC listeners
# bound exclusively to loopback. Pairing is intentionally left for Hopper's
# local GUI; the VM never invents or embeds a controller private key.
if ! wait_for_remote_transport; then
  cat "$LOG"
  echo 'Aurum PC installed runtime did not expose the restricted remote transport.' >&2
  exit 1
fi

printf 'gui-start\n' >&3
if ! wait_for_marker 'AURUM_GUI_RUNTIME status=running address=127.0.0.1 port=8765' 420; then
  cat "$LOG"
  echo 'Aurum PC installed GUI was not ready for remote-desktop proof.' >&2
  exit 1
fi

if ! start_remote_desktop || \
   ! grep -Fq 'vnc_listeners=127.0.0.1' "$LOG" || \
   ! grep -Fq 'websocket_listeners=127.0.0.1' "$LOG"; then
  cat "$LOG"
  echo 'Aurum PC remote desktop did not prove both loopback-only listeners.' >&2
  exit 1
fi

printf 'remote-desktop-stop\n' >&3
if ! wait_for_marker 'AURUM_REMOTE status=stopped action=desktop-stop desktop=stopped loopback=true raw_shell=false' 60 || \
   ! grep -Fq 'vnc_listeners=none' "$LOG" || \
   ! grep -Fq 'websocket_listeners=none' "$LOG"; then
  cat "$LOG"
  echo 'Aurum PC remote desktop did not stop cleanly.' >&2
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
grep -F 'AURUM_REMOTE status=running action=desktop-start desktop=running loopback=true raw_shell=false' "$LOG"
grep -F 'AURUM_REMOTE status=stopped action=desktop-stop desktop=stopped loopback=true raw_shell=false' "$LOG"
grep -F 'AURUM_SELF_BUILD_FINISHED status=passed' "$LOG"
{
  echo 'AURUM_VIRTUAL_PC_REMOTE_CONTROL_OK'
  echo 'AURUM_VIRTUAL_PC_UEFI_RUNTIME_SELF_BUILD_OK'
  echo 'AURUM_VIRTUAL_PC_UEFI_INSTALL_AND_SELF_BUILD_OK'
} | tee -a "$LOG"
rm -rf "$work_dir"
