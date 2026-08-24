#!/usr/bin/env python3
"""Capture a small, non-secret boot receipt for Aurum/Tiny Seed.

The receipt is evidence, not a health decision. Guardian remains the authority for
promotion/rollback. This module records enough machine/slot context to prove that
a specific seed actually reached userspace on real or virtual hardware.
"""
from __future__ import annotations

import json
import os
import platform
import socket
import time
from pathlib import Path
from typing import Any


EVIDENCE_ROOT = Path(os.environ.get("AURUM_EVIDENCE_ROOT", "/var/lib/aurum/evidence"))
SLOT_STATE = Path(os.environ.get("AURUM_SLOT_STATE", "/var/lib/aurum/germ/slots.json"))
ACTIVE_LINK = Path(os.environ.get("AURUM_ACTIVE_LINK", "/opt/aurum"))
BOOT_ID_PATH = Path(os.environ.get("AURUM_BOOT_ID_PATH", "/proc/sys/kernel/random/boot_id"))
CMDLINE_PATH = Path(os.environ.get("AURUM_CMDLINE_PATH", "/proc/cmdline"))
RECEIPT = EVIDENCE_ROOT / "boot-proof.json"


def _read_text(path: Path, limit: int = 4096) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit].strip()
    except OSError:
        return None


def _read_json(path: Path) -> dict[str, Any]:
    text = _read_text(path, 65536)
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _active_target() -> str | None:
    try:
        return str(ACTIVE_LINK.resolve(strict=True))
    except OSError:
        return None


def build_receipt() -> dict[str, Any]:
    state = _read_json(SLOT_STATE)
    return {
        "schema": "aurum-boot-proof-v1",
        "captured_at_unix": int(time.time()),
        "hostname": socket.gethostname()[:255],
        "architecture": platform.machine(),
        "kernel_release": platform.release(),
        "boot_id": _read_text(BOOT_ID_PATH, 128),
        "kernel_cmdline": _read_text(CMDLINE_PATH, 4096),
        "active_runtime": _active_target(),
        "guardian": {
            "schema": state.get("schema"),
            "active": state.get("active"),
            "lkg": state.get("lkg"),
            "trial": state.get("trial"),
            "trial_boots": state.get("trial_boots"),
            "last_result": state.get("last_result"),
        },
    }


def capture(path: Path = RECEIPT) -> dict[str, Any]:
    payload = build_receipt()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return payload


def main() -> int:
    payload = capture()
    print(json.dumps(payload, sort_keys=True), flush=True)
    print(f"AURUM_BOOT_PROOF_READY path={RECEIPT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
