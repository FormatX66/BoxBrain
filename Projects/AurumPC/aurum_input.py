#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

SYS_INPUT = Path("/sys/class/input")
DEV_INPUT = Path("/dev/input")
COMMON_MODULES = ("i2c_hid_acpi", "hid_multitouch", "psmouse", "usbhid")


def _read(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default


def _hex_words(path: Path) -> tuple[int, ...]:
    raw = _read(path)
    if not raw:
        return ()
    values: list[int] = []
    for word in raw.split():
        try:
            values.append(int(word, 16))
        except ValueError:
            continue
    return tuple(values)


def _has_any(words: tuple[int, ...]) -> bool:
    return any(value != 0 for value in words)


def classify_device(name: str, *, rel: tuple[int, ...], abs_axes: tuple[int, ...]) -> str:
    lowered = name.lower()
    if "touchpad" in lowered or "trackpad" in lowered:
        return "touchpad"
    if "mouse" in lowered:
        return "mouse"
    if _has_any(abs_axes) and not _has_any(rel):
        return "absolute-pointer"
    if _has_any(rel):
        return "relative-pointer"
    return "other"


def input_devices() -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    if not SYS_INPUT.exists():
        return devices
    for event in sorted(SYS_INPUT.glob("event*")):
        device = event / "device"
        name = _read(device / "name", event.name)
        rel = _hex_words(device / "capabilities" / "rel")
        abs_axes = _hex_words(device / "capabilities" / "abs")
        kind = classify_device(name, rel=rel, abs_axes=abs_axes)
        node = DEV_INPUT / event.name
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
            }
        )
    return devices


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


def status() -> dict[str, Any]:
    devices = input_devices()
    pointers = [item for item in devices if item["kind"] in {"touchpad", "mouse", "relative-pointer", "absolute-pointer"}]
    touchpads = [item for item in devices if item["kind"] == "touchpad"]
    return {
        "schema": "aurum.input.v1",
        "status": "ready" if pointers else "no-pointer-detected",
        "libinput_available": libinput_available(),
        "modules": module_state(),
        "touchpads": touchpads,
        "pointers": pointers,
        "devices": devices,
    }


def main() -> int:
    payload = status()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
