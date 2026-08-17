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

work_dir=$(mktemp -d /tmp/aurum-vlab-pc.XXXXXX)
ovmf_vars="$work_dir/OVMF_VARS.fd"
installed_disk="$work_dir/aurum-installed.raw"
readonly_nvme="$work_dir/pc01-readonly-nvme.raw"
serial_input="$work_dir/input"
cp "$vars" "$ovmf_vars"
truncate -s 10G "$installed_disk"
# PC-01 has an internal NVMe device. Attach a large sparse NVMe device read-only
# so discovery is exercised while any attempted write would fail closed.
truncate -s 12G "$readonly_nvme"
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

common_qemu_args() {
  printf '%s\n' \
    -machine q35,accel=tcg \
    -cpu qemu64 \
    -m 1024 \
    -smp 2 \
    -drive "if=pflash,format=raw,readonly=on,file=$code" \
    -drive "if=pflash,format=raw,file=$ovmf_vars" \
    -drive "file=$installed_disk,format=raw,if=virtio" \
    -drive "file=$readonly_nvme,format=raw,if=none,id=pc01nvme,readonly=on" \
    -device "nvme,drive=pc01nvme,serial=PC01NVME0001" \
    -nic user,model=virtio-net-pci \
    -display none \
    -serial stdio \
    -monitor none \
    -no-reboot
}

start_live_qemu() {
  mapfile -t args < <(common_qemu_args)
  timeout 900s qemu-system-x86_64 \
    "${args[@]}" \
    -cdrom "$ISO" \
    -boot order=d \
    <&3 >> "$LOG" 2>&1 &
  qemu_pid=$!
}

start_installed_qemu() {
  printf '\n===== AURUM INSTALLED DISK BOOT =====\n' >> "$LOG"
  mapfile -t args < <(common_qemu_args)
  timeout 900s qemu-system-x86_64 \
    "${args[@]}" \
    -boot order=c \
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

# Exercise the actual PC-01 network recovery path with a predictable PCI NIC.
printf 'network-repair\n' >&3
if ! wait_for_marker 'AURUM_NETWORK_REPAIR status=ready' 60; then
  cat "$LOG"
  echo 'Aurum PC did not acquire DHCP, a default route, and working DNS.' >&2
  exit 1
fi

# The read-only NVMe must be visible for diagnostics but never offered as an
# installation target. The explicit read-only bit also makes any accidental
# write attempt fail at the virtual hardware boundary.
printf 'storage-status\n' >&3
if ! wait_for_marker 'AURUM_STORAGE_STATUS status=ok' 30 || \
   ! wait_for_marker 'readonly_nvme=1' 30 || \
   ! grep -Fq '"name": "nvme0n1"' "$LOG"; then
  cat "$LOG"
  echo 'Aurum PC did not observe the PC-01-style read-only NVMe device safely.' >&2
  exit 1
fi

printf 'install\n' >&3
if ! wait_for_marker 'AURUM_INSTALL_PLAN status=ready' 60; then
  cat "$LOG"
  echo 'Aurum PC did not expose a guided install plan.' >&2
  exit 1
fi
if grep -Fq 'AURUM_INSTALL_TARGET device=/dev/nvme' "$LOG"; then
  cat "$LOG"
  echo 'Aurum PC incorrectly offered the read-only NVMe as an install target.' >&2
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

# Recheck DHCP/DNS from the installed runtime, then initialize the real Git
# workspace. This catches the physical-image path failures that previously
# surfaced as missing Projects and /opt/.github paths.
printf 'network-repair\n' >&3
if ! wait_for_marker 'AURUM_NETWORK_REPAIR status=ready' 60; then
  cat "$LOG"
  echo 'Installed Aurum runtime did not recover working network/DNS.' >&2
  exit 1
fi
printf 'git-sync authorize-network\n' >&3
if ! wait_for_marker '"workspace": "/var/lib/aurum/workspace/BoxBrain"' 240; then
  cat "$LOG"
  echo 'Installed Aurum runtime could not initialize its Git workspace.' >&2
  exit 1
fi

printf 'self-build\n' >&3
if ! wait_for_self_build 720; then
  cat "$LOG"
  echo 'Aurum PC installed-runtime self-build did not pass from the initialized workspace.' >&2
  exit 1
fi

# Verify a clean reboot boundary after network, Git, and self-build activity.
printf 'reboot\n' >&3
if ! wait_for_marker 'AURUM_PC_REBOOT requested=true' 30; then
  cat "$LOG"
  echo 'Aurum PC did not accept the bounded reboot request.' >&2
  exit 1
fi
finish_qemu

start_installed_qemu
if ! wait_for_marker 'mode=installed' 180 || ! grep -Fq 'selftest=ok' "$LOG"; then
  cat "$LOG"
  echo 'Aurum PC did not return cleanly after reboot.' >&2
  exit 1
fi
printf 'git-status\n' >&3
if ! wait_for_marker '"workspace": "/var/lib/aurum/workspace/BoxBrain"' 60; then
  cat "$LOG"
  echo 'Aurum Git workspace did not survive the reboot boundary.' >&2
  exit 1
fi
printf 'poweroff\n' >&3
finish_qemu

trap - EXIT
exec 3>&-
cat "$LOG"
grep -F 'AURUM_PC_READY version=0.01 arch=x86_64' "$LOG"
grep -F 'mode=live' "$LOG"
grep -F 'AURUM_NETWORK_REPAIR status=ready' "$LOG"
grep -F 'AURUM_STORAGE_STATUS status=ok' "$LOG"
grep -F 'readonly_nvme=1' "$LOG"
grep -F 'AURUM_INSTALL_PLAN status=ready' "$LOG"
grep -F 'AURUM_INSTALL_FINISHED status=passed' "$LOG"
grep -F 'mode=installed' "$LOG"
grep -F '"workspace": "/var/lib/aurum/workspace/BoxBrain"' "$LOG"
grep -F 'AURUM_SELF_BUILD_FINISHED status=passed' "$LOG"
grep -F 'AURUM_PC_REBOOT requested=true' "$LOG"
echo 'AURUM_VIRTUAL_PC01_NETWORK_DNS_OK'
echo 'AURUM_VIRTUAL_PC01_READONLY_NVME_OK'
echo 'AURUM_VIRTUAL_PC01_WORKSPACE_SELF_BUILD_OK'
echo 'AURUM_VIRTUAL_PC01_REBOOT_CLEAN_OK'
echo 'AURUM_VIRTUAL_PC_UEFI_INSTALL_AND_SELF_BUILD_OK'
rm -rf "$work_dir"
