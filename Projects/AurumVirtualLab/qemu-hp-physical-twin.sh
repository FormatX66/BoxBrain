#!/usr/bin/env bash
set -euo pipefail

ISO=${1:?usage: qemu-hp-physical-twin.sh ISO LOG}
LOG=${2:?usage: qemu-hp-physical-twin.sh ISO LOG}

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

for tool in qemu-system-x86_64 parted sha256sum; do
  command -v "$tool" >/dev/null || { echo "missing tool: $tool" >&2; exit 2; }
done

work_dir=$(mktemp -d /tmp/aurum-hp-twin.XXXXXX)
ovmf_vars="$work_dir/OVMF_VARS.fd"
internal_nvme="$work_dir/hp-internal-nvme.raw"
secondary_usb="$work_dir/hp-secondary-usb.raw"
serial_input="$work_dir/input"
monitor="$work_dir/monitor"
cp "$vars" "$ovmf_vars"

# Match the physical topology classes seen on the HP: NVMe with four
# partitions plus removable USB media.  The internal NVMe is attached read-only
# during live preflight so any accidental write attempt fails closed.
truncate -s 64G "$internal_nvme"
parted -s "$internal_nvme" mklabel gpt
parted -s "$internal_nvme" mkpart ESP fat32 1MiB 513MiB
parted -s "$internal_nvme" mkpart primary 513MiB 16GiB
parted -s "$internal_nvme" mkpart primary 16GiB 48GiB
parted -s "$internal_nvme" mkpart primary 48GiB 100%
truncate -s 2G "$secondary_usb"
parted -s "$secondary_usb" mklabel gpt
parted -s "$secondary_usb" mkpart primary 1MiB 1025MiB
parted -s "$secondary_usb" mkpart primary 1025MiB 100%

nvme_before=$(dd if="$internal_nvme" bs=1M count=8 status=none | sha256sum | awk '{print $1}')
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
  marker=$1
  attempts=$2
  for _ in $(seq 1 "$attempts"); do
    grep -Fq "$marker" "$LOG" && return 0
    kill -0 "$qemu_pid" 2>/dev/null || return 1
    sleep 1
  done
  return 1
}

# Physical observations encoded here:
# - HP x86_64 UEFI laptop
# - ~7.4 GiB usable RAM -> 7680 MiB logical twin
# - NVMe internal disk
# - boot from removable USB mass storage, not CD-ROM
# - second SCSI-style removable device present
# - enp4s0 MAC observed as 04:0e:3c:54:54:49 and link down
# - no visible Wi-Fi interface
# - RTC observed months behind current date
# Unknown CPU/GPU/Wi-Fi PCI identities remain explicit unknowns until the next
# detailed physical profile; this test matches topology and failure behavior,
# not invented device identities.
timeout 420s qemu-system-x86_64 \
  -machine q35,accel=tcg \
  -cpu qemu64 \
  -m 7680 \
  -smp 4 \
  -smbios type=1,manufacturer=HP,product='Aurum HP Physical Twin',version=physical-evidence-v1 \
  -drive if=pflash,format=raw,readonly=on,file="$code" \
  -drive if=pflash,format=raw,file="$ovmf_vars" \
  -drive if=none,id=nvme0,file="$internal_nvme",format=raw,readonly=on \
  -device nvme,drive=nvme0,serial=AURUMHPNVME \
  -device qemu-xhci,id=xhci \
  -drive if=none,id=seed,file="$ISO",format=raw,readonly=on \
  -device usb-storage,drive=seed,bootindex=1 \
  -drive if=none,id=usb2,file="$secondary_usb",format=raw \
  -device usb-storage,drive=usb2 \
  -device usb-kbd \
  -netdev user,id=net0,restrict=on \
  -device e1000e,id=hpeth,netdev=net0,mac=04:0e:3c:54:54:49 \
  -rtc base=2026-04-27T19:50:12,clock=vm \
  -boot strict=on \
  -display none \
  -serial stdio \
  -monitor pipe:"$monitor" \
  -no-reboot \
  <&3 >> "$LOG" 2>&1 &
qemu_pid=$!

# Force the emulated Ethernet link down after monitor startup to reproduce the
# observed no-carrier state while still leaving an Ethernet controller visible.
for _ in $(seq 1 40); do
  if [ -p "$monitor.in" ]; then
    printf 'set_link hpeth off\n' > "$monitor.in" || true
    break
  fi
  sleep 0.25
done

if ! wait_for_marker 'AURUM_PC_READY version=0.01 arch=x86_64' 180; then
  cat "$LOG"
  echo 'HP twin did not reach Aurum runtime.' >&2
  exit 1
fi
if ! grep -Fq 'AURUM_HARDWARE_PROFILE status=ready' "$LOG"; then
  cat "$LOG"
  echo 'HP twin did not capture the exact-machine profile.' >&2
  exit 1
fi
if ! grep -Fq 'AURUM_WIFI_DIAG ' "$LOG"; then
  cat "$LOG"
  echo 'HP twin did not automatically diagnose the missing Wi-Fi interface.' >&2
  exit 1
fi

# The bounded serial console must expose the detailed provider, not the old
# shallow architecture/block/net summary that the physical boot revealed.
printf 'hardware\n' >&3
if ! wait_for_marker '"pci_devices"' 60 || ! grep -Fq '"network_interfaces"' "$LOG"; then
  cat "$LOG"
  echo 'HP twin hardware command did not expose detailed PCI/network evidence.' >&2
  exit 1
fi

# No install command is sent.  The internal NVMe must remain byte-for-byte
# unchanged across the live preflight even though it is present and partitioned.
printf 'poweroff\n' >&3
set +e
wait "$qemu_pid"
qemu_status=$?
set -e
qemu_pid=
if [ "$qemu_status" -ne 0 ]; then
  cat "$LOG"
  echo "HP twin exited unexpectedly with status $qemu_status" >&2
  exit "$qemu_status"
fi
nvme_after=$(dd if="$internal_nvme" bs=1M count=8 status=none | sha256sum | awk '{print $1}')
if [ "$nvme_before" != "$nvme_after" ]; then
  cat "$LOG"
  echo 'HP twin internal NVMe changed during live preflight.' >&2
  exit 1
fi

cat "$LOG"
echo 'AURUM_HP_TWIN_UEFI_USB_BOOT_OK'
echo 'AURUM_HP_TWIN_NVME_PRESERVED_OK'
echo 'AURUM_HP_TWIN_WIFI_MISSING_DIAGNOSTIC_OK'
echo 'AURUM_HP_TWIN_DETAILED_HARDWARE_OK'
