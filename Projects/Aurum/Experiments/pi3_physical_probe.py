"""Read-only Raspberry Pi 3 experiment probe.

This module gathers physical receipts from a real Pi 3 without changing boot state,
network configuration, drivers, firmware, or the active/LKG kernel profile.  The
receipt can then be fed into the existing StateWeave + Adaptive Kernel experiment.
"""

from __future__ import annotations

import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiment_suite import combined_trial

PI3_RECEIPT_SCHEMA = "aurum-pi3-physical-receipt-v1"


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip("\x00\n ")
    except (FileNotFoundError, PermissionError, OSError):
        return ""


def _mem_total_mb() -> int:
    text = _read_text("/proc/meminfo")
    for line in text.splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) // 1024
    return 0


def collect_receipt() -> dict[str, Any]:
    """Collect only read-only physical evidence available to an unprivileged process."""
    net_root = Path("/sys/class/net")
    try:
        interfaces = sorted(entry.name for entry in net_root.iterdir())
    except (FileNotFoundError, PermissionError, OSError):
        interfaces = []

    model = _read_text("/proc/device-tree/model")
    if not model:
        model = _read_text("/sys/firmware/devicetree/base/model")

    return {
        "schema": PI3_RECEIPT_SCHEMA,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "hostname": platform.node(),
        "model": model,
        "arch": platform.machine().lower(),
        "kernel": platform.release(),
        "cores": os.cpu_count() or 1,
        "ram_mb": _mem_total_mb(),
        "boot_id": _read_text("/proc/sys/kernel/random/boot_id"),
        "interfaces": interfaces,
    }


def gate_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Fail closed unless the receipt proves a live Raspberry Pi 3-class system."""
    problems: list[str] = []
    if receipt.get("schema") != PI3_RECEIPT_SCHEMA:
        problems.append("unknown-receipt-schema")

    model = str(receipt.get("model", ""))
    if "Raspberry Pi 3" not in model:
        problems.append("model-not-raspberry-pi-3")

    arch = str(receipt.get("arch", "")).lower()
    if arch not in {"armv7l", "armv8l", "aarch64", "arm64"}:
        problems.append("unexpected-arm-architecture")

    if int(receipt.get("cores", 0) or 0) < 1:
        problems.append("missing-cpu-evidence")
    if int(receipt.get("ram_mb", 0) or 0) < 256:
        problems.append("insufficient-memory-evidence")
    if not str(receipt.get("boot_id", "")).strip():
        problems.append("missing-boot-receipt")
    if not isinstance(receipt.get("interfaces"), list):
        problems.append("missing-network-inventory")

    return {
        "accepted": not problems,
        "gate": "physical-receipt-valid" if not problems else "hold",
        "problems": problems,
        "promotion_allowed": False,
        "mutation_allowed": False,
    }


def build_observe_only_trial(receipt: dict[str, Any]) -> dict[str, Any]:
    """Create the next experiment trial only after real Pi 3 evidence passes the gate."""
    gate = gate_receipt(receipt)
    if not gate["accepted"]:
        raise ValueError("Pi3 physical receipt did not pass: " + ",".join(gate["problems"]))

    hardware = {
        "arch": receipt["arch"],
        "cores": receipt["cores"],
        "ram_mb": receipt["ram_mb"],
        "devices": [f"net:{name}" for name in receipt["interfaces"]],
    }
    machine_state = {
        "hostname": receipt["hostname"],
        "model": receipt["model"],
        "kernel": receipt["kernel"],
        "boot_id": receipt["boot_id"],
        "interfaces": receipt["interfaces"],
    }
    trial = combined_trial(
        hardware,
        machine_state,
        active_profile="pi3-current-observed",
        lkg_profile="pi3-current-observed",
    )
    trial["physical_gate"] = gate
    trial["future_branch_next"] = [
        "capture-stateweave-before-change",
        "evaluate-adaptive-kernel-candidate",
        "probe-mesh-read-only",
    ]
    return trial


if __name__ == "__main__":
    receipt = collect_receipt()
    result: dict[str, Any] = {"receipt": receipt, "gate": gate_receipt(receipt)}
    if result["gate"]["accepted"]:
        result["trial"] = build_observe_only_trial(receipt)
    print(json.dumps(result, indent=2, sort_keys=True))
