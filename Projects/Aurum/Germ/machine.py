#!/usr/bin/env python3
"""Small, read-only machine/platform discovery helpers for the Aurum Reseed Germ."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping


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


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unknown"


def _species_family(
    *, architecture_name: str, firmware: str, model: str | None
) -> str:
    normalized_model = (model or "").lower()
    pi_generation = re.search(r"\braspberry pi\s+(\d+)\b", normalized_model)
    if pi_generation:
        return f"raspberry-pi-{pi_generation.group(1)}"
    if "raspberry pi" in normalized_model:
        return "raspberry-pi"
    if architecture_name == "x86_64":
        return "generic-x86-64-pc"
    if architecture_name == "arm64":
        return "generic-arm64"
    return f"generic-{_slug(architecture_name)}-{_slug(firmware)}"


def species_from_observation(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce a coarse bootstrap observation to a stable machine family receipt.

    This is intentionally not a unique node identity or a complete hardware
    inventory. It contains only enough family-level evidence to select a
    compatible first-boot profile. Exact specimen discovery happens after the
    first internal reboot.
    """

    architecture_name = str(observation.get("architecture") or "unknown")
    firmware = str(observation.get("firmware") or "unknown")
    model_value = observation.get("model")
    vendor_value = observation.get("vendor")
    model = str(model_value) if model_value else None
    vendor = str(vendor_value) if vendor_value else None
    family = _species_family(
        architecture_name=architecture_name,
        firmware=firmware,
        model=model,
    )
    first_boot_profile = f"{family}-{architecture_name}"
    identity_basis = {
        "architecture": architecture_name,
        "family": family,
        "firmware": firmware,
        "first_boot_profile": first_boot_profile,
    }
    encoded = json.dumps(
        identity_basis, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    missing = [
        name
        for name, value in (("model", model), ("vendor", vendor))
        if value is None
    ]
    return {
        "schema": "aurum-machine-species-v1",
        "scope": "coarse-first-boot-selection-not-node-identity",
        "species_id": f"sha256:{hashlib.sha256(encoded).hexdigest()}",
        **identity_basis,
        "model": model,
        "vendor": vendor,
        "observed": {
            "kernel_machine": str(observation.get("kernel_machine") or "unknown"),
            "model": model,
            "vendor": vendor,
        },
        "missing": missing,
    }


def detect_species() -> dict[str, Any]:
    return species_from_observation(detect())


def main() -> int:
    print(json.dumps(detect_species(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
