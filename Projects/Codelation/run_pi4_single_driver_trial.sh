#!/usr/bin/env bash
set -euo pipefail

TARGET="gpio-leds"
GENERATOR="${1:-./pi4_driver_synthesizer.py}"
GENERATION="${AURUM_DRIVER_GENERATION:-2}"
RUN_TAG="${AURUM_RUN_TAG:-manual}"
BACKUP_BASE="${AURUM_BACKUP_BASE:-$HOME/.local/share/aurum/driver-backups}"

fail() {
  echo "AURUM_PI4_DRIVER_TRIAL status=blocked reason=$1" >&2
  exit "${2:-1}"
}

MODEL="$(tr -d '\000' </proc/device-tree/model 2>/dev/null || true)"
[[ "$MODEL" == *"Raspberry Pi 4"* ]] || fail "not_raspberry_pi_4" 40
KERNEL="$(uname -r)"
ARCH="$(uname -m)"
BUILD_DIR="/lib/modules/$KERNEL/build"

command -v python3 >/dev/null || fail "python3_missing" 41
command -v make >/dev/null || fail "make_missing" 42
command -v gcc >/dev/null || fail "gcc_missing" 43
command -v sudo >/dev/null || fail "sudo_missing" 44
sudo -n true >/dev/null 2>&1 || fail "passwordless_sudo_required_for_bounded_bind_test" 45
[[ -f "$BUILD_DIR/Makefile" ]] || fail "exact_kernel_headers_missing:$BUILD_DIR" 46
[[ -f "$GENERATOR" ]] || fail "synthesizer_missing:$GENERATOR" 47
[[ "$GENERATION" == "1" || "$GENERATION" == "2" ]] || fail "unsupported_generation:$GENERATION" 48

DRIVER_DIR=""
for candidate in /sys/bus/platform/drivers/leds-gpio /sys/bus/platform/drivers/gpio-leds; do
  if [[ -d "$candidate" ]]; then
    DRIVER_DIR="$candidate"
    break
  fi
done
[[ -n "$DRIVER_DIR" ]] || fail "working_gpio_led_driver_not_found" 49
WORKING_DRIVER="$(basename "$DRIVER_DIR")"

DEVICE=""
for entry in "$DRIVER_DIR"/*; do
  [[ -L "$entry" ]] || continue
  name="$(basename "$entry")"
  [[ "$name" == "module" ]] && continue
  node="/sys/bus/platform/devices/$name/of_node/compatible"
  if [[ -r "$node" ]] && tr '\000' '\n' <"$node" | grep -Fxq 'gpio-leds'; then
    DEVICE="$name"
    break
  fi
done
[[ -n "$DEVICE" ]] || fail "bound_gpio_led_device_not_found" 50

COMPATIBLE="$(tr '\000' '\n' </sys/bus/platform/devices/$DEVICE/of_node/compatible | head -n1)"
[[ "$COMPATIBLE" == "gpio-leds" ]] || fail "unexpected_compatible:$COMPATIBLE" 51

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SAFE_DEVICE="${DEVICE//\//_}"
BACKUP_DIR="$BACKUP_BASE/${STAMP}-${RUN_TAG}-${WORKING_DRIVER}-${SAFE_DEVICE}-g${GENERATION}"
mkdir -p "$BACKUP_DIR"

printf '%s\n' "$MODEL" >"$BACKUP_DIR/model.txt"
printf '%s\n' "$ARCH" >"$BACKUP_DIR/arch.txt"
printf '%s\n' "$KERNEL" >"$BACKUP_DIR/kernel.txt"
printf '%s\n' "$WORKING_DRIVER" >"$BACKUP_DIR/working-driver.txt"
printf '%s\n' "$DEVICE" >"$BACKUP_DIR/device.txt"
printf '%s\n' "$COMPATIBLE" >"$BACKUP_DIR/compatible.txt"
printf '%s\n' "$GENERATION" >"$BACKUP_DIR/generation.txt"
readlink -f "/sys/bus/platform/devices/$DEVICE/driver" >"$BACKUP_DIR/original-driver-link.txt" || true
cat "/sys/bus/platform/devices/$DEVICE/uevent" >"$BACKUP_DIR/device-uevent.txt" 2>/dev/null || true
cat "/sys/bus/platform/devices/$DEVICE/modalias" >"$BACKUP_DIR/device-modalias.txt" 2>/dev/null || true
find "/sys/bus/platform/devices/$DEVICE/of_node" -maxdepth 1 -type f -printf '%f\n' 2>/dev/null | sort >"$BACKUP_DIR/of-node-files.txt" || true

: >"$BACKUP_DIR/led-state.tsv"
{
  for led in /sys/class/leds/*; do
    [[ -e "$led" ]] || continue
    name="$(basename "$led")"
    device_path="$(readlink -f "$led/device" 2>/dev/null || true)"
    brightness="$(cat "$led/brightness" 2>/dev/null || true)"
    max_brightness="$(cat "$led/max_brightness" 2>/dev/null || true)"
    trigger_line="$(cat "$led/trigger" 2>/dev/null || true)"
    active_trigger="$(printf '%s' "$trigger_line" | sed -n 's/.*\[\([^]]*\)\].*/\1/p')"
    echo "[$name]"
    printf 'device=%s\n' "$device_path"
    printf 'brightness=%s\n' "$brightness"
    printf 'max_brightness=%s\n' "$max_brightness"
    printf 'trigger=%s\n' "$trigger_line"
    printf '%s\t%s\t%s\t%s\n' "$name" "$brightness" "$active_trigger" "$device_path" >>"$BACKUP_DIR/led-state.tsv"
  done
} >"$BACKUP_DIR/led-state.txt"

echo "built-in" >"$BACKUP_DIR/module-status.txt"
if [[ -L "$DRIVER_DIR/module" ]]; then
  MODULE_NAME="$(basename "$(readlink -f "$DRIVER_DIR/module")")"
  printf '%s\n' "$MODULE_NAME" >"$BACKUP_DIR/module-status.txt"
  modinfo "$MODULE_NAME" >"$BACKUP_DIR/modinfo.txt" 2>&1 || true
  MODULE_FILE="$(modinfo -n "$MODULE_NAME" 2>/dev/null || true)"
  if [[ -f "$MODULE_FILE" ]]; then
    cp -a "$MODULE_FILE" "$BACKUP_DIR/"
    sha256sum "$MODULE_FILE" >"$BACKUP_DIR/original-module.sha256"
  fi
fi

python3 - "$BACKUP_DIR/evidence.json" <<PY
import json, sys
path=sys.argv[1]
obj={
  "target":"gpio-leds",
  "compatible":${COMPATIBLE@Q},
  "working_driver":${WORKING_DRIVER@Q},
  "device":${DEVICE@Q},
  "kernel":${KERNEL@Q},
  "model":${MODEL@Q},
  "arch":${ARCH@Q},
  "backup_dir":${BACKUP_DIR@Q},
}
open(path,"w",encoding="utf-8").write(json.dumps(obj,indent=2,sort_keys=True)+"\n")
PY

TRIAL_ROOT="$(mktemp -d /tmp/aurum-pi4-driver.XXXXXX)"
CANDIDATE_DIR="$TRIAL_ROOT/candidate"
mkdir -p "$CANDIDATE_DIR"
cp "$BACKUP_DIR/evidence.json" "$TRIAL_ROOT/evidence.json"

python3 "$GENERATOR" --evidence "$TRIAL_ROOT/evidence.json" --out "$CANDIDATE_DIR" --generation "$GENERATION" | tee "$BACKUP_DIR/synthesis-output.json"
make -C "$BUILD_DIR" M="$CANDIDATE_DIR" modules 2>&1 | tee "$BACKUP_DIR/build.log"
KO="$CANDIDATE_DIR/aurum_gpio_leds.ko"
[[ -s "$KO" ]] || fail "candidate_module_not_built" 52
sha256sum "$KO" | tee "$BACKUP_DIR/candidate-module.sha256"
modinfo "$KO" >"$BACKUP_DIR/candidate-modinfo.txt"
cp "$CANDIDATE_DIR/candidate-manifest.json" "$BACKUP_DIR/"
cp "$CANDIDATE_DIR/aurum_gpio_leds.c" "$BACKUP_DIR/"
cp "$KO" "$BACKUP_DIR/"

restore_led_state() {
  [[ -f "$BACKUP_DIR/led-state.tsv" ]] || return 0
  while IFS=$'\t' read -r name brightness active_trigger original_device; do
    [[ -n "$name" && -e "/sys/class/leds/$name" ]] || continue
    if [[ -w "/sys/class/leds/$name/trigger" ]]; then
      printf '%s' none | sudo tee "/sys/class/leds/$name/trigger" >/dev/null 2>&1 || true
    fi
    if [[ -n "$brightness" && -w "/sys/class/leds/$name/brightness" ]]; then
      printf '%s' "$brightness" | sudo tee "/sys/class/leds/$name/brightness" >/dev/null 2>&1 || true
    fi
    if [[ -n "$active_trigger" && "$active_trigger" != "none" && -w "/sys/class/leds/$name/trigger" ]]; then
      printf '%s' "$active_trigger" | sudo tee "/sys/class/leds/$name/trigger" >/dev/null 2>&1 || true
    fi
  done <"$BACKUP_DIR/led-state.tsv"
}

restore_original() {
  set +e
  CANDIDATE_DRIVER_DIR="/sys/bus/platform/drivers/aurum-gpio-leds"
  if [[ -L "$CANDIDATE_DRIVER_DIR/$DEVICE" ]]; then
    printf '%s' "$DEVICE" | sudo tee "$CANDIDATE_DRIVER_DIR/unbind" >/dev/null
  fi
  if lsmod | awk '{print $1}' | grep -Fxq aurum_gpio_leds; then
    sudo rmmod aurum_gpio_leds >/dev/null 2>&1 || true
  fi
  if [[ ! -L "$DRIVER_DIR/$DEVICE" ]]; then
    printf '%s' "$DEVICE" | sudo tee "$DRIVER_DIR/bind" >/dev/null 2>&1 || true
  fi
  restore_led_state
  RESTORED="$(basename "$(readlink -f "/sys/bus/platform/devices/$DEVICE/driver" 2>/dev/null || true)")"
  printf '%s\n' "$RESTORED" >"$BACKUP_DIR/restored-driver.txt"
  rm -rf "$TRIAL_ROOT"
}
trap restore_original EXIT

sudo insmod "$KO"
lsmod | grep '^aurum_gpio_leds' | tee "$BACKUP_DIR/candidate-loaded.txt"
[[ -d /sys/bus/platform/drivers/aurum-gpio-leds ]] || fail "candidate_driver_registration_missing" 53

printf '%s' "$DEVICE" | sudo tee "$DRIVER_DIR/unbind" >/dev/null
[[ ! -L "$DRIVER_DIR/$DEVICE" ]] || fail "working_driver_unbind_failed" 54

printf '%s' "$DEVICE" | sudo tee /sys/bus/platform/drivers/aurum-gpio-leds/bind >/dev/null
BOUND_DRIVER="$(basename "$(readlink -f "/sys/bus/platform/devices/$DEVICE/driver" 2>/dev/null || true)")"
printf '%s\n' "$BOUND_DRIVER" | tee "$BACKUP_DIR/candidate-bound-driver.txt"
[[ "$BOUND_DRIVER" == "aurum-gpio-leds" ]] || fail "candidate_bind_failed:$BOUND_DRIVER" 55

dmesg | tail -n 100 >"$BACKUP_DIR/dmesg-after-candidate-bind.txt" 2>/dev/null || true

if [[ "$GENERATION" == "2" ]]; then
  : >"$BACKUP_DIR/behavior-test.txt"
  tested=0
  for led in /sys/class/leds/*; do
    [[ -e "$led" ]] || continue
    led_device="$(readlink -f "$led/device" 2>/dev/null || true)"
    if [[ "$led_device" != *"/$DEVICE" && "$led_device" != *"/$DEVICE/"* ]]; then
      continue
    fi
    name="$(basename "$led")"
    max="$(cat "$led/max_brightness" 2>/dev/null || echo 0)"
    [[ "$max" =~ ^[0-9]+$ && "$max" -ge 1 ]] || fail "candidate_led_invalid_max_brightness:$name" 56
    if [[ -w "$led/trigger" ]]; then
      printf '%s' none | sudo tee "$led/trigger" >/dev/null
    fi
    printf '%s' 0 | sudo tee "$led/brightness" >/dev/null
    zero="$(cat "$led/brightness")"
    printf '%s' 1 | sudo tee "$led/brightness" >/dev/null
    one="$(cat "$led/brightness")"
    printf '%s' 0 | sudo tee "$led/brightness" >/dev/null
    zero2="$(cat "$led/brightness")"
    printf '%s\tzero=%s\tone=%s\tzero2=%s\n' "$name" "$zero" "$one" "$zero2" | tee -a "$BACKUP_DIR/behavior-test.txt"
    [[ "$zero" == "0" && "$one" == "1" && "$zero2" == "0" ]] || fail "candidate_led_roundtrip_failed:$name" 57
    tested=$((tested + 1))
  done
  [[ "$tested" -gt 0 ]] || fail "candidate_created_no_target_led_class_devices" 58
  printf '%s\n' "$tested" >"$BACKUP_DIR/behavior-led-count.txt"
fi

printf '%s' "$DEVICE" | sudo tee /sys/bus/platform/drivers/aurum-gpio-leds/unbind >/dev/null
sudo rmmod aurum_gpio_leds
printf '%s' "$DEVICE" | sudo tee "$DRIVER_DIR/bind" >/dev/null
restore_led_state
RESTORED_DRIVER="$(basename "$(readlink -f "/sys/bus/platform/devices/$DEVICE/driver" 2>/dev/null || true)")"
printf '%s\n' "$RESTORED_DRIVER" | tee "$BACKUP_DIR/restored-driver.txt"
[[ "$RESTORED_DRIVER" == "$WORKING_DRIVER" ]] || fail "rollback_rebind_failed:$RESTORED_DRIVER" 59

trap - EXIT
rm -rf "$TRIAL_ROOT"

echo "AURUM_PI4_DRIVER_BACKUP path=$BACKUP_DIR working_driver=$WORKING_DRIVER device=$DEVICE"
echo "AURUM_PI4_DRIVER_SYNTHESIS target=$TARGET generation=$GENERATION exact_kernel=$KERNEL compile=passed"
if [[ "$GENERATION" == "2" ]]; then
  echo "AURUM_PI4_DRIVER_BEHAVIOR on_off_roundtrip=passed physical_led_writes=true raw_mmio=false"
fi
echo "AURUM_PI4_DRIVER_SWAP candidate=aurum-gpio-leds bind=passed rollback=passed"
echo "AURUM_PI4_DRIVER_TRIAL status=passed"
