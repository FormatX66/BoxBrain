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
nvme_sentinel="$work_dir/pc01-nvme-readonly.raw"
serial_input="$work_dir/input"
cp "$vars" "$ovmf_vars"
truncate -s 10G "$installed_disk"
truncate -s 64M "$nvme_sentinel"
nvme_sha_before=$(sha256sum "$nvme_sentinel" | awk '{print $1}')
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

start_live_qemu() {
  timeout 900s qemu-system-x86_64 \
    -machine q35,accel=tcg \
    -cpu qemu64 \
    -m 1024 \
    -smp 2 \
    -drive if=pflash,format=raw,readonly=on,file="$code" \
    -drive if=pflash,format=raw,file="$ovmf_vars" \
    -drive file="$installed_disk",format=raw,if=virtio \
    -drive file="$nvme_sentinel",format=raw,if=none,readonly=on,id=nvme-sentinel \
    -device nvme,drive=nvme-sentinel,serial=AURUMROPC01 \
    -netdev user,id=aurumnet \
    -device virtio-net-pci,netdev=aurumnet \
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
    -machine q35,accel=tcg \
    -cpu qemu64 \
    -m 1024 \
    -smp 2 \
    -drive if=pflash,format=raw,readonly=on,file="$code" \
    -drive if=pflash,format=raw,file="$ovmf_vars" \
    -drive file="$installed_disk",format=raw,if=virtio \
    -drive file="$nvme_sentinel",format=raw,if=none,readonly=on,id=nvme-sentinel \
    -device nvme,drive=nvme-sentinel,serial=AURUMROPC01 \
    -netdev user,id=aurumnet \
    -device virtio-net-pci,netdev=aurumnet \
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

marker_count() {
  grep -Fc "$1" "$LOG" 2>/dev/null || true
}

wait_for_new_marker() {
  marker=$1
  previous=$2
  attempts=$3
  for _ in $(seq 1 "$attempts"); do
    current=$(marker_count "$marker")
    if [ "$current" -gt "$previous" ]; then
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
  previous_passes=$2
  previous_failures=$3
  for _ in $(seq 1 "$attempts"); do
    passes=$(marker_count 'AURUM_SELF_BUILD_FINISHED status=passed')
    failures=$(grep -Ec 'AURUM_SELF_BUILD_FINISHED status=(failed|cancelled)' "$LOG" 2>/dev/null || true)
    if [ "$passes" -gt "$previous_passes" ]; then
      return 0
    fi
    if [ "$failures" -gt "$previous_failures" ]; then
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

printf 'hardware\n' >&3
if ! wait_for_marker '"nvme0n1"' 30; then
  cat "$LOG"
  echo 'Aurum PC did not expose the read-only PC-01 NVMe probe.' >&2
  exit 1
fi

printf 'network-status\n' >&3
if ! wait_for_marker 'AURUM_NETWORK status=ready' 90; then
  cat "$LOG"
  echo 'Aurum PC did not acquire wired DHCP, a default route, and working DNS.' >&2
  exit 1
fi

printf 'git-status\n' >&3
if ! wait_for_marker '"status": "not-initialized"' 30; then
  cat "$LOG"
  echo 'Aurum PC did not begin with a clean, uninitialized Git workspace.' >&2
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
if ! grep -Fq 'AURUM_INSTALL_TARGET device=/dev/vda' "$LOG" || \
   grep -Fq 'AURUM_INSTALL_TARGET device=/dev/nvme0n1' "$LOG"; then
  cat "$LOG"
  echo 'The install plan did not isolate the writable synthetic disk from read-only NVMe.' >&2
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

network_ready_before=$(marker_count 'AURUM_NETWORK status=ready')
printf 'network-status\n' >&3
if ! wait_for_new_marker 'AURUM_NETWORK status=ready' "$network_ready_before" 90; then
  cat "$LOG"
  echo 'The installed Aurum runtime did not restore wired DHCP and DNS.' >&2
  exit 1
fi

git_uninitialized_before=$(marker_count '"status": "not-initialized"')
printf 'git-status\n' >&3
if ! wait_for_new_marker '"status": "not-initialized"' "$git_uninitialized_before" 30; then
  cat "$LOG"
  echo 'The installed Aurum runtime unexpectedly depended on a pre-existing Git checkout.' >&2
  exit 1
fi

self_build_passes=$(marker_count 'AURUM_SELF_BUILD_FINISHED status=passed')
self_build_failures=$(grep -Ec 'AURUM_SELF_BUILD_FINISHED status=(failed|cancelled)' "$LOG" 2>/dev/null || true)
printf 'self-build\n' >&3
if ! wait_for_self_build 720 "$self_build_passes" "$self_build_failures"; then
  cat "$LOG"
  echo 'Aurum PC installed-runtime self-build did not pass.' >&2
  exit 1
fi
if ! grep -Fq '"completed_generations": 64' "$LOG" || \
   ! grep -Fq '"blocked_reason": "generation-bound-reached"' "$LOG"; then
  cat "$LOG"
  echo 'The installed self-build did not preserve the generation-64 checkpoint.' >&2
  exit 1
fi

seeded_before=$(marker_count '"status": "seeded"')
printf 'seed\n' >&3
if ! wait_for_new_marker '"status": "seeded"' "$seeded_before" 60; then
  cat "$LOG"
  echo 'Aurum PC did not create persistent seed state before reboot.' >&2
  exit 1
fi

printf 'reboot\n' >&3
finish_qemu

installed_ready_before=$(marker_count 'mode=installed')
start_installed_qemu
if ! wait_for_new_marker 'mode=installed' "$installed_ready_before" 180 || \
   ! grep -Fq 'AURUM_PC_READY version=0.01 arch=x86_64' "$LOG" || \
   ! grep -Fq 'selftest=ok' "$LOG"; then
  cat "$LOG"
  echo 'The installed Aurum disk did not return cleanly after explicit reboot.' >&2
  exit 1
fi

seeded_before=$(marker_count '"status": "seeded"')
printf 'seed-status\n' >&3
if ! wait_for_new_marker '"status": "seeded"' "$seeded_before" 30; then
  cat "$LOG"
  echo 'Aurum PC seed state did not persist across installed-disk reboot.' >&2
  exit 1
fi

self_build_passes=$(marker_count 'AURUM_SELF_BUILD_FINISHED status=passed')
self_build_failures=$(grep -Ec 'AURUM_SELF_BUILD_FINISHED status=(failed|cancelled)' "$LOG" 2>/dev/null || true)
printf 'self-build\n' >&3
if ! wait_for_self_build 720 "$self_build_passes" "$self_build_failures"; then
  cat "$LOG"
  echo 'Aurum PC did not resume its persisted generation-64 self-build state.' >&2
  exit 1
fi

git_ready_before=$(marker_count '"configured_branch": "aurum/trunk-v0.01"')
printf 'git-sync authorize-network\n' >&3
if ! wait_for_new_marker '"configured_branch": "aurum/trunk-v0.01"' "$git_ready_before" 300; then
  cat "$LOG"
  echo 'Aurum PC could not initialize its fixed trunk workspace over verified HTTPS.' >&2
  exit 1
fi
if ! grep -Fq '"dirty": false' "$LOG"; then
  cat "$LOG"
  echo 'The initialized Aurum Git workspace was not clean.' >&2
  exit 1
fi

printf 'poweroff\n' >&3
finish_qemu

nvme_sha_after=$(sha256sum "$nvme_sentinel" | awk '{print $1}')
if [ "$nvme_sha_after" != "$nvme_sha_before" ]; then
  echo 'The read-only NVMe sentinel changed during the Aurum PC test.' >&2
  exit 1
fi

trap - EXIT
exec 3>&-
cat "$LOG"
grep -F 'AURUM_PC_READY version=0.01 arch=x86_64' "$LOG"
grep -F 'mode=live' "$LOG"
grep -F 'AURUM_INSTALL_PLAN status=ready' "$LOG"
grep -F 'AURUM_INSTALL_FINISHED status=passed' "$LOG"
grep -F 'mode=installed' "$LOG"
grep -F 'AURUM_SELF_BUILD_FINISHED status=passed' "$LOG"
grep -F 'AURUM_NETWORK status=ready' "$LOG"
grep -F '"configured_branch": "aurum/trunk-v0.01"' "$LOG"
echo 'AURUM_VIRTUAL_PC_NETWORK_DHCP_DNS_OK'
echo 'AURUM_VIRTUAL_PC_READ_ONLY_NVME_OK'
echo 'AURUM_VIRTUAL_PC_PERSISTENCE_REBOOT_OK'
echo 'AURUM_VIRTUAL_PC_WORKSPACE_GIT_SYNC_OK'
echo 'AURUM_VIRTUAL_PC_REBOOT_POWEROFF_CLEANUP_OK'
echo 'AURUM_VIRTUAL_PC_UEFI_RUNTIME_SELF_BUILD_OK'
echo 'AURUM_VIRTUAL_PC_UEFI_INSTALL_AND_SELF_BUILD_OK'
rm -rf "$work_dir"
