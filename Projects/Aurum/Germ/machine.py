#!/usr/bin/env python3
"""Small, read-only machine/platform discovery helpers for the Aurum Reseed Germ."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _read(path: str) -> str | None:
    try:
        value = Path(path).read_text(encoding="utf-8", errors="replace").replace("\x00", "").strip()
    except OSError:
        return None
    return value or None


def architecture() -> str:
    machine = os.uname().machine.lower()
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    return machine or "unknown"


def detect() -> dict[str, Any]:
    machine = os.uname().machine.lower()
    model = _read("/sys/firmware/devicetree/base/model") or _read("/sys/class/dmi/id/product_name")
    vendor = _read("/sys/class/dmi/id/sys_vendor")
    firmware = "uefi" if Path("/sys/firmware/efi").is_dir() else "firmware-native"
    if model and "raspberry pi" in model.lower():
        firmware = "raspberry-pi"
    return {
        "schema": "aurum-germ-machine-v1",
        "architecture": architecture(),
        "kernel_machine": machine,
        "firmware": firmware,
        "model": model,
        "vendor": vendor,
    }


def main() -> int:
    print(json.dumps(detect(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
