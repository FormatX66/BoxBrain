#!/usr/bin/env python3
"""Bounded Hopper pointer discovery and resume-safe wake policy."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "aurum.input.v2"
SYS_INPUT = Path("/sys/class/input")
DEV_INPUT = Path("/dev/input")
DEFAULT_STATE = Path("/run/aurum-input-status.json")
COMMON_MODULES = ("i2c_hid_acpi", "hid_multitouch", "psmouse", "usbhid")
POINTER_KINDS = frozenset({"touchpad", "mouse", "relative-pointer", "absolute-pointer"})


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


def classify_device(name: str, *, rel: tuple[int, ...], abs_axes: tuple[int, ...]) -> str:
    lowered = name.lower()
    if any(marker in lowered for marker in ("touchpad", "trackpad", "clickpad", "glidepoint")):
        return "touchpad"
    if "mouse" in lowered:
        return "mouse"
    if _has_any(abs_axes) and not _has_any(rel):
        return "absolute-pointer"
    if _has_any(rel):
        return "relative-pointer"
    return "other"


def _power_files(device: Path) -> dict[str, Path]:
    """Find the nearest power policy for each setting exposed by this device.

    Each setting stops at its first match and the search is bounded to eight
    ancestors so a pointer cannot walk all the way to a broad machine policy.
    """

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


def input_devices(
    *,
    sys_input: Path = SYS_INPUT,
    dev_input: Path = DEV_INPUT,
) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    if not sys_input.exists():
        return devices
    for event in sorted(sys_input.glob("event*")):
        device = event / "device"
        name = _read(device / "name", event.name)
        rel = _hex_words(device / "capabilities" / "rel")
        abs_axes = _hex_words(device / "capabilities" / "abs")
        kind = classify_device(name, rel=rel, abs_axes=abs_axes)
        node = dev_input / event.name
        devices.append(
            {
                "event": event.name,
                "node": str(node),
                "name": name,
                "kind": kind,
                "present": node.exists(),
                "readable": os.access(node, os.R_OK) if node.exists() else False,
                "relative_axes": [hex(value) for value in rel],
                "absolute_axes": [hex(value) for value in abs_axes],
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


def apply_pointer_wake_policy(devices: list[dict[str, Any]]) -> dict[str, Any]:
    changed: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    managed = 0
    for item in devices:
        if item.get("kind") not in POINTER_KINDS:
            continue
        files = _power_files(Path(str(item.get("_device_path") or "")))
        if not files:
            continue
        managed += 1
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
        "managed_pointer_count": managed,
        "changed": changed,
        "errors": errors,
        "runtime_pm_disabled_for_managed_pointers": not errors,
    }


def module_state() -> dict[str, bool]:
    return {name: (Path("/sys/module") / name).exists() for name in COMMON_MODULES}


def libinput_available() -> bool:
    try:
        result = subprocess.run(
            ["libinput", "list-devices"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def status(*, apply_wake: bool = False) -> dict[str, Any]:
    devices = input_devices()
    pointers = [item for item in devices if item["kind"] in POINTER_KINDS]
    touchpads = [item for item in pointers if item["kind"] == "touchpad"]
    wake_policy = (
        apply_pointer_wake_policy(devices)
        if apply_wake
        else {"status": "observed", "managed_pointer_count": 0, "changed": [], "errors": []}
    )
    for item in devices:
        item.pop("_device_path", None)
    return {
        "schema": SCHEMA,
        "status": "ready" if pointers and not wake_policy["errors"] else "no-pointer-detected" if not pointers else "degraded",
        "libinput_available": libinput_available(),
        "modules": module_state(),
        "wake_policy": wake_policy,
        "touchpads": touchpads,
        "pointers": pointers,
        "devices": devices,
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect and wake Hopper pointer devices")
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
