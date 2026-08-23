#!/usr/bin/env python3
"""Small, read-only platform discovery helpers for the Aurum Reseed Germ."""
from __future__ import annotations

import json
import platform as _platform
from pathlib import Path
from typing import Any


def _read(path: str) -> str | None:
    try:
        value = Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    return value or None


def detect() -> dict[str, Any]:
    machine = _platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        family = "x86_64"
    elif machine in {"aarch64", "arm64"}:
        family = "arm64"
    else:
        family = machine or "unknown"

    model = _read("/sys/firmware/devicetree/base/model") or _read("/sys/class/dmi/id/product_name")
    vendor = _read("/sys/class/dmi/id/sys_vendor")
    firmware = "uefi" if Path("/sys/firmware/efi").is_dir() else "firmware-native"
    if model and "raspberry pi" in model.lower():
        firmware = "raspberry-pi"

    return {
        "schema": "aurum-germ-platform-v1",
        "architecture": family,
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
