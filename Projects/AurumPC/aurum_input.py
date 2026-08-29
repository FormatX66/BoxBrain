#!/usr/bin/env python3
"""Bounded Hopper pointer discovery and resume-safe input recovery."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "aurum.input.v4"
SYS_INPUT = Path("/sys/class/input")
DEV_INPUT = Path("/dev/input")
DEFAULT_STATE = Path("/run/aurum-input-status.json")
DEFAULT_STATE_DIR = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
GUI_EVENT_PROOF = "gui-input-proof.json"
_GUI_EVENT_LOCK = threading.Lock()
COMMON_MODULES = (
    "i2c_hid_acpi",
    "hid_multitouch",
    "psmouse",
    "usbhid",
    "hid_generic",
    "atkbd",
)
POINTER_KINDS = frozenset({"touchpad", "mouse", "relative-pointer", "absolute-pointer"})
HUMAN_INPUT_KINDS = POINTER_KINDS | {"keyboard"}
XORG_LIBINPUT_DRIVERS = (
    Path("/usr/lib/xorg/modules/input/libinput_drv.so"),
    Path("/usr/lib/x86_64-linux-gnu/xorg/modules/input/libinput_drv.so"),
)
LIBINPUT_PACKAGES = ("xserver-xorg-input-libinput", "libinput-tools")


def _read(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default


def _hex_words(path: Path) -> tuple[int, ...]:
    values: list[int] = []
    for word in _read(path).split():
        try:
            values.append(int(word, 16))
        except ValueError:
            continue
    return tuple(values)


def _has_any(words: Iterable[int]) -> bool:
    return any(value != 0 for value in words)


def classify_device(
    name: str,
    *,
    rel: tuple[int, ...],
    abs_axes: tuple[int, ...],
    key_bits: tuple[int, ...] = (),
) -> str:
    lowered = name.lower()
    if any(marker in lowered for marker in ("keyboard", "kbd", "translated set 2")):
        return "keyboard"
    if any(marker in lowered for marker in ("touchpad", "trackpad", "clickpad", "glidepoint")):
        return "touchpad"
    if "mouse" in lowered:
        return "mouse"
    if _has_any(abs_axes) and not _has_any(rel):
        return "absolute-pointer"
    if _has_any(rel):
        return "relative-pointer"
    # A keyboard exposes many EV_KEY bitmap words but no relative or absolute
    # axes.  Requiring more than one non-zero word avoids treating a single
    # mouse button bitmap as a keyboard.
    if sum(1 for value in key_bits if value) > 1:
        return "keyboard"
    return "other"


def _kernel_driver(device: Path) -> str | None:
    """Find the nearest bound kernel driver without mutating the device."""
    try:
        current = device.resolve(strict=True)
    except OSError:
        return None
    for depth, candidate in enumerate((current, *current.parents)):
        if depth > 10:
            break
        driver = candidate / "driver"
        if not driver.exists() and not driver.is_symlink():
            continue
        try:
            return driver.resolve(strict=True).name
        except OSError:
            continue
    return None


def parse_libinput_devices(text: str) -> dict[str, dict[str, Any]]:
    """Parse stable identity/capability fields from ``libinput list-devices``."""
    devices: dict[str, dict[str, Any]] = {}
    block: dict[str, str] = {}

    def flush() -> None:
        kernel = block.get("Kernel", "").strip()
        if not kernel:
            block.clear()
            return
        capabilities = [token for token in block.get("Capabilities", "").split() if token]
        devices[kernel] = {
            "name": block.get("Device") or None,
            "kernel": kernel,
            "group": block.get("Group") or None,
            "seat": block.get("Seat") or None,
            "capabilities": capabilities,
        }
        block.clear()

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if block:
                flush()
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in {"Device", "Kernel", "Group", "Seat", "Capabilities"}:
            block[key] = value.strip()
    if block:
        flush()
    return devices


def libinput_device_details() -> dict[str, dict[str, Any]]:
    """Read libinput's classification/capability view once, bounded to five seconds."""
    executable = shutil.which("libinput")
    if not executable:
        return {}
    try:
        result = subprocess.run(
            [executable, "list-devices"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    return parse_libinput_devices(result.stdout)


def _power_files(device: Path) -> dict[str, Path]:
    try:
        current = device.resolve(strict=True)
    except OSError:
        return {}
    files: dict[str, Path] = {}
    for depth, candidate in enumerate((current, *current.parents)):
        if depth > 8:
            break
        power = candidate / "power"
        for name in ("control", "wakeup"):
            path = power / name
            if name not in files and path.is_file():
                files[name] = path
        if len(files) == 2:
            break
    return files


def _power_snapshot(device: Path) -> dict[str, Any]:
    files = _power_files(device)
    return {
        "managed": bool(files),
        "control": _read(files["control"]) if "control" in files else None,
        "wakeup": _read(files["wakeup"]) if "wakeup" in files else None,
    }


def input_devices(*, sys_input: Path = SYS_INPUT, dev_input: Path = DEV_INPUT) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    if not sys_input.exists():
        return devices
    for event in sorted(sys_input.glob("event*")):
        device = event / "device"
        name = _read(device / "name", event.name)
        rel = _hex_words(device / "capabilities" / "rel")
        abs_axes = _hex_words(device / "capabilities" / "abs")
        key_bits = _hex_words(device / "capabilities" / "key")
        kind = classify_device(name, rel=rel, abs_axes=abs_axes, key_bits=key_bits)
        node = dev_input / event.name
        devices.append(
            {
                "event": event.name,
                "node": str(node),
                "name": name,
                "kind": kind,
                "kernel_driver": _kernel_driver(device),
                "present": node.exists(),
                "readable": os.access(node, os.R_OK) if node.exists() else False,
                "relative_axes": [hex(value) for value in rel],
                "absolute_axes": [hex(value) for value in abs_axes],
                "key_bitmap_words": len([value for value in key_bits if value]),
                "power": _power_snapshot(device),
                "_device_path": str(device),
            }
        )
    return devices


def _write_policy(path: Path, desired: str) -> tuple[bool, str | None]:
    current = _read(path)
    if not current or current == desired:
        return False, None
    try:
        path.write_text(desired + "\n", encoding="ascii")
    except OSError as exc:
        return False, f"{type(exc).__name__}:{exc}"
    return True, None


def apply_input_wake_policy(devices: list[dict[str, Any]]) -> dict[str, Any]:
    changed: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    managed_inputs = 0
    managed_pointers = 0
    managed_keyboards = 0
    for item in devices:
        kind = str(item.get("kind") or "")
        if kind not in HUMAN_INPUT_KINDS:
            continue
        files = _power_files(Path(str(item.get("_device_path") or "")))
        if not files:
            continue
        managed_inputs += 1
        if kind in POINTER_KINDS:
            managed_pointers += 1
        elif kind == "keyboard":
            managed_keyboards += 1
        for name, desired in (("control", "on"), ("wakeup", "enabled")):
            path = files.get(name)
            if path is None:
                continue
            did_change, error = _write_policy(path, desired)
            if did_change:
                changed.append({"event": str(item.get("event")), "setting": name, "value": desired})
            if error:
                errors.append({"event": str(item.get("event")), "setting": name, "detail": error})
        item["power"] = _power_snapshot(Path(str(item.get("_device_path") or "")))
    return {
        "status": "ready" if not errors else "degraded",
        "managed_input_count": managed_inputs,
        "managed_pointer_count": managed_pointers,
        "managed_keyboard_count": managed_keyboards,
        "changed": changed,
        "errors": errors,
        "runtime_pm_disabled_for_managed_inputs": not errors,
    }


def apply_pointer_wake_policy(devices: list[dict[str, Any]]) -> dict[str, Any]:
    """Backward-compatible name for the now keyboard-and-pointer policy."""
    return apply_input_wake_policy(devices)


def _boot_id() -> str | None:
    return _read(Path("/proc/sys/kernel/random/boot_id")) or None


def gui_event_proof(*, state_dir: Path = DEFAULT_STATE_DIR) -> dict[str, Any]:
    path = state_dir / GUI_EVENT_PROOF
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    same_boot = bool(value.get("boot_id") and value.get("boot_id") == _boot_id())
    keyboard = value.get("keyboard") if isinstance(value.get("keyboard"), dict) else {}
    pointer = value.get("pointer") if isinstance(value.get("pointer"), dict) else {}
    keyboard_count = keyboard.get("event_count", 0)
    pointer_count = pointer.get("event_count", 0)
    keyboard_observed = bool(
        same_boot
        and isinstance(keyboard_count, int)
        and not isinstance(keyboard_count, bool)
        and keyboard_count > 0
        and keyboard.get("last_at")
    )
    pointer_observed = bool(
        same_boot
        and isinstance(pointer_count, int)
        and not isinstance(pointer_count, bool)
        and pointer_count > 0
        and pointer.get("last_at")
    )
    return {
        "schema": "aurum.gui-input-proof.v1",
        "same_boot": same_boot,
        "keyboard_observed": keyboard_observed,
        "pointer_observed": pointer_observed,
        "ready": bool(keyboard_observed and pointer_observed),
        "keyboard": keyboard,
        "pointer": pointer,
    }


def record_gui_event(kind: str, *, state_dir: Path = DEFAULT_STATE_DIR) -> dict[str, Any]:
    """Record only event-path evidence, never the key pressed or pointer position."""
    selected = str(kind or "").strip().lower()
    if selected not in {"keyboard", "pointer"}:
        raise ValueError("GUI input proof kind must be keyboard or pointer")
    path = state_dir / GUI_EVENT_PROOF
    # Keyboard and pointer proof can arrive on separate request threads. Keep
    # their read/modify/write cycle atomic so neither proof is overwritten.
    with _GUI_EVENT_LOCK:
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = {}
        boot_id = _boot_id()
        if not isinstance(current, dict) or current.get("boot_id") != boot_id:
            current = {"schema": "aurum.gui-input-proof.v1", "boot_id": boot_id}
        existing = current.get(selected) if isinstance(current.get(selected), dict) else {}
        count = existing.get("event_count", 0)
        count = count if isinstance(count, int) and not isinstance(count, bool) and count >= 0 else 0
        current[selected] = {
            "event_count": count + 1,
            "last_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _atomic_json(path, current)
    return gui_event_proof(state_dir=state_dir)


def module_state() -> dict[str, bool]:
    return {name: (Path("/sys/module") / name).exists() for name in COMMON_MODULES}


def libinput_cli_available() -> bool:
    executable = shutil.which("libinput")
    if not executable:
        return False
    try:
        result = subprocess.run(
            [executable, "list-devices"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def xorg_libinput_driver_available() -> bool:
    return any(path.is_file() for path in XORG_LIBINPUT_DRIVERS)


def repair_libinput() -> dict[str, Any]:
    before = {
        "cli": libinput_cli_available(),
        "xorg_driver": xorg_libinput_driver_available(),
    }
    if before["cli"] and before["xorg_driver"]:
        return {"status": "already-ready", "before": before, "after": before, "installed": []}
    apt = shutil.which("apt-get")
    if not apt:
        return {"status": "blocked", "reason": "apt-get-unavailable", "before": before, "installed": []}
    if os.geteuid() != 0:
        return {"status": "blocked", "reason": "root-required", "before": before, "installed": []}
    env = dict(os.environ)
    env["DEBIAN_FRONTEND"] = "noninteractive"
    try:
        result = subprocess.run(
            [apt, "install", "-y", "--no-install-recommends", *LIBINPUT_PACKAGES],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=600,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "status": "failed",
            "reason": f"{type(exc).__name__}:{exc}",
            "before": before,
            "installed": [],
        }
    after = {
        "cli": libinput_cli_available(),
        "xorg_driver": xorg_libinput_driver_available(),
    }
    ready = after["cli"] and after["xorg_driver"]
    return {
        "status": "ready" if ready else "failed",
        "before": before,
        "after": after,
        "installed": list(LIBINPUT_PACKAGES) if result.returncode == 0 else [],
        "returncode": result.returncode,
        "detail": "" if result.returncode == 0 else result.stdout[-1600:],
        "gui_restart_required": bool(result.returncode == 0 and before != after),
    }


def status(*, apply_wake: bool = False) -> dict[str, Any]:
    devices = input_devices()
    pointers = [item for item in devices if item["kind"] in POINTER_KINDS]
    touchpads = [item for item in pointers if item["kind"] == "touchpad"]
    keyboards = [item for item in devices if item["kind"] == "keyboard"]
    human_inputs = [item for item in devices if item["kind"] in HUMAN_INPUT_KINDS]
    wake_policy = (
        apply_input_wake_policy(devices)
        if apply_wake
        else {
            "status": "observed",
            "managed_input_count": 0,
            "managed_pointer_count": 0,
            "managed_keyboard_count": 0,
            "changed": [],
            "errors": [],
        }
    )
    libinput = {
        "cli": libinput_cli_available(),
        "xorg_driver": xorg_libinput_driver_available(),
    }
    repair = repair_libinput() if apply_wake and human_inputs and not all(libinput.values()) else {"status": "not-needed"}
    if repair.get("status") in {"ready", "already-ready"}:
        libinput = {
            "cli": libinput_cli_available(),
            "xorg_driver": xorg_libinput_driver_available(),
        }
    libinput_devices = libinput_device_details() if libinput["cli"] else {}
    for item in devices:
        item["libinput"] = libinput_devices.get(str(item.get("node") or ""))
    for item in devices:
        item.pop("_device_path", None)
    pointer_ready = bool(
        pointers
        and all(item.get("present") and item.get("readable") for item in pointers)
    )
    keyboard_ready = bool(
        keyboards
        and all(item.get("present") and item.get("readable") for item in keyboards)
    )
    xorg_event_path_ready = bool(
        pointer_ready
        and keyboard_ready
        and not wake_policy["errors"]
        and libinput["xorg_driver"]
    )
    identified_pointers = [
        {
            "event": item.get("event"),
            "node": item.get("node"),
            "name": item.get("name"),
            "kind": item.get("kind"),
            "kernel_driver": item.get("kernel_driver"),
            "libinput": item.get("libinput"),
        }
        for item in pointers
    ]
    return {
        "schema": SCHEMA,
        "status": (
            "ready"
            if xorg_event_path_ready
            else "no-pointer-detected"
            if not pointers
            else "no-keyboard-detected"
            if not keyboards
            else "degraded"
        ),
        "pointer_ready": pointer_ready,
        "keyboard_ready": keyboard_ready,
        "xorg_event_path_ready": xorg_event_path_ready,
        "libinput_available": bool(libinput["cli"]),
        "libinput": libinput,
        "repair": repair,
        "modules": module_state(),
        "wake_policy": wake_policy,
        "touchpads": touchpads,
        "pointers": pointers,
        "keyboards": keyboards,
        "identified_pointers": identified_pointers,
        "gui_event_proof": gui_event_proof(),
        "devices": devices,
        "gui_restart_required": bool(repair.get("gui_restart_required")),
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect and recover Hopper pointer devices")
    parser.add_argument("--apply-wake-policy", action="store_true")
    parser.add_argument("--write-state", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args()
    payload = status(apply_wake=args.apply_wake_policy)
    try:
        _atomic_json(args.write_state, payload)
    except OSError as exc:
        payload["state_write"] = {"status": "failed", "detail": f"{type(exc).__name__}:{exc}"}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
