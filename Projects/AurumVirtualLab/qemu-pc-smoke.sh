#!/usr/bin/env bash
set -euo pipefail

ISO=${1:?usage: qemu-pc-smoke.sh ISO LOG}
LOG=${2:?usage: qemu-pc-smoke.sh ISO LOG}
QEMU_ACCEL=${AURUM_QEMU_ACCEL:-tcg}
QEMU_FIRMWARE=${AURUM_QEMU_FIRMWARE:-uefi}
SKIP_SELF_BUILD=${AURUM_QEMU_SKIP_SELF_BUILD:-0}
case "$QEMU_ACCEL" in
  kvm|tcg) ;;
  *) echo "Unsupported Aurum QEMU accelerator: $QEMU_ACCEL" >&2; exit 2 ;;
esac
case "$QEMU_FIRMWARE" in
  uefi|legacy) ;;
  *) echo "Unsupported Aurum QEMU firmware: $QEMU_FIRMWARE" >&2; exit 2 ;;
esac
case "$SKIP_SELF_BUILD" in
  0|1) ;;
  *) echo "Unsupported Aurum self-build switch: $SKIP_SELF_BUILD" >&2; exit 2 ;;
esac

if [ "$QEMU_FIRMWARE" = uefi ]; then
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
fi

work_dir=$(mktemp -d /tmp/aurum-vlab-pc.XXXXXX)
installed_disk="$work_dir/aurum-installed.raw"
serial_input="$work_dir/input"
firmware_args=()
if [ "$QEMU_FIRMWARE" = uefi ]; then
  ovmf_vars="$work_dir/OVMF_VARS.fd"
  cp "$vars" "$ovmf_vars"
  firmware_args=(
    -drive "if=pflash,format=raw,readonly=on,file=$code"
    -drive "if=pflash,format=raw,file=$ovmf_vars"
  )
fi
truncate -s 10G "$installed_disk"
mkfifo "$serial_input"
exec 3<>"$serial_input"
: > "$LOG"
echo "AURUM_QEMU_ACCELERATION selected=$QEMU_ACCEL" >> "$LOG"
echo "AURUM_QEMU_FIRMWARE selected=$QEMU_FIRMWARE" >> "$LOG"
qemu_pid=

cleanup() {
  local result=$?
  if [ -n "${qemu_pid:-}" ] && kill -0 "$qemu_pid" 2>/dev/null; then
    # The installed assessment is useful only after guest writes are flushed.
    # Ask this disposable Aurum VM to power down, then retain the existing hard
    # stop as a bounded fallback if its secondary console is no longer responsive.
    printf 'poweroff\n' >&3 || true
    for _ in $(seq 1 60); do
      kill -0 "$qemu_pid" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$qemu_pid" 2>/dev/null; then
      kill "$qemu_pid" 2>/dev/null || true
    fi
    wait "$qemu_pid" 2>/dev/null || true
  fi
  if [ "$result" -ne 0 ] && [ -f "$installed_disk" ]; then
    # This is the disposable image created above, never a host disk. Read the
    # installed primary console's persisted assessment after QEMU has stopped.
    # Its output is on VT1, while the harness observes the secondary serial VT.
    # Root starts at 515 MiB in AurumInstaller's fixed image layout. Copy that
    # bounded range sparsely into this uniquely created work directory, then use
    # debugfs without mounting or replaying the guest filesystem journal. This
    # does not depend on the hosted runner having an unused loop device.
    local diagnostic_root="$work_dir/aurum-root-diagnostic.ext4"
    echo 'AURUM_VIRTUAL_PC_FAILURE_ASSESSMENT_BEGIN' | tee -a "$LOG"
    if timeout 45s dd if="$installed_disk" of="$diagnostic_root" \
        iflag=skip_bytes skip=540016640 bs=4M conv=sparse status=none; then
      timeout 10s debugfs -R 'cat /var/lib/aurum/state/first-boot-assessment.json' "$diagnostic_root" 2>&1 | tee -a "$LOG" || true
    else
      echo 'AURUM_VIRTUAL_PC_FAILURE_ASSESSMENT unavailable=sparse-copy' | tee -a "$LOG"
    fi
    echo 'AURUM_VIRTUAL_PC_FAILURE_ASSESSMENT_END' | tee -a "$LOG"
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
    "${firmware_args[@]}" \
    -drive file="$installed_disk",format=raw,if=virtio \
    -cdrom "$ISO" \
    -boot order=d \
    -nic none \
    -display none \
    -serial stdio \
    -monitor none \
    -no-reboot \
    <&3 >> "$LOG" 2>&1 &
  qemu_pid=$!
}

start_installed_qemu() {
  installed_start_line=$(( $(wc -l < "$LOG") + 1 ))
  printf '\n===== AURUM INSTALLED DISK BOOT =====\n' >> "$LOG"
  timeout 1200s qemu-system-x86_64 \
    -machine "q35,accel=$QEMU_ACCEL" \
    -cpu qemu64 \
    -m 1024 \
    -smp 2 \
    "${firmware_args[@]}" \
    -drive file="$installed_disk",format=raw,if=virtio \
    -boot order=c \
    -nic none \
    -display none \
    -serial stdio \
    -monitor none \
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

wait_for_installed_ready() {
  # Neither the live boot nor the preceding installed boot may satisfy this.
  for _ in $(seq 1 180); do
    if tail -n +"$installed_start_line" "$LOG" |
        grep -E '^AURUM_PC_READY version=0\.01 arch=x86_64 .*mode=installed selftest=ok' >/dev/null; then
      return 0
    fi
    if ! kill -0 "$qemu_pid" 2>/dev/null; then
      return 1
    fi
    sleep 1
  done
  return 1
}

wait_for_primary_gui() {
  # Status only: never make the test start a GUI that boot failed to start.
  # Scope the response to this boot; a previous session cannot satisfy proof.
  for _ in $(seq 1 30); do
    printf 'gui-status\n' >&3
    for _ in $(seq 1 5); do
      if tail -n +"$installed_start_line" "$LOG" |
          grep -F 'AURUM_GUI_RUNTIME status=running physical_desktop=true' >/dev/null; then
        echo 'AURUM_VIRTUAL_PC_INSTALLED_PRIMARY_GUI_OK network=offline' >> "$LOG"
        return 0
      fi
      if ! kill -0 "$qemu_pid" 2>/dev/null; then
        return 1
      fi
      sleep 1
    done
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
  echo "Aurum PC did not reach its $QEMU_FIRMWARE live-runtime marker." >&2
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
if ! wait_for_installed_ready; then
  cat "$LOG"
  echo "The installed Aurum disk did not reach its $QEMU_FIRMWARE runtime-ready marker." >&2
  exit 1
fi

if ! wait_for_primary_gui; then
  cat "$LOG"
  echo 'Installed Aurum did not automatically open its primary GUI while offline.' >&2
  exit 1
fi

if [ "$SKIP_SELF_BUILD" = 0 ]; then
  printf 'self-build\n' >&3
  if ! wait_for_self_build 720; then
    cat "$LOG"
    echo 'Aurum PC installed-runtime self-build did not pass.' >&2
    exit 1
  fi
fi

# Exercise the guest's real reboot in the same VM, not a new power-on. Keep
# networking absent and discard all previous boot markers from acceptance.
installed_start_line=$(( $(wc -l < "$LOG") + 1 ))
printf '\n===== AURUM INSTALLED GUEST REBOOT =====\n' >> "$LOG"
printf 'reboot\n' >&3
if ! wait_for_installed_ready || ! wait_for_primary_gui; then
  cat "$LOG"
  echo 'Installed Aurum did not regain its primary GUI after an offline reboot.' >&2
  exit 1
fi
echo 'AURUM_VIRTUAL_PC_INSTALLED_REBOOT_GUI_OK network=offline' >> "$LOG"

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
if [ "$SKIP_SELF_BUILD" = 0 ]; then
  grep -F 'AURUM_SELF_BUILD_FINISHED status=passed' "$LOG"
fi
if [ "$QEMU_FIRMWARE" = uefi ] && [ "$SKIP_SELF_BUILD" = 0 ]; then
  echo 'AURUM_VIRTUAL_PC_UEFI_RUNTIME_SELF_BUILD_OK'
  echo 'AURUM_VIRTUAL_PC_UEFI_INSTALL_AND_SELF_BUILD_OK'
elif [ "$QEMU_FIRMWARE" = legacy ]; then
  echo 'AURUM_VIRTUAL_PC_LEGACY_INSTALL_BOOT_OK'
fi
rm -rf "$work_dir"
