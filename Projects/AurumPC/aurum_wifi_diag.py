#!/usr/bin/env python3
"""Read-only Wi-Fi controller diagnostics for the Aurum PC seed."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aurum_hardware import collect_hardware_profile
from aurum_network import wireless_interfaces

NETWORK_CLASS_PREFIX = "0x02"
WIRELESS_CLASS_PREFIXES = ("0x0280", "0x028000")


def _likely_wireless_pci(device: dict[str, Any]) -> bool:
    cls = str(device.get("class") or "").lower()
    return cls.startswith(WIRELESS_CLASS_PREFIXES) or cls.startswith(NETWORK_CLASS_PREFIX)


def diagnose() -> dict[str, Any]:
    profile = collect_hardware_profile()
    candidates = [d for d in profile.get("pci_devices", []) if _likely_wireless_pci(d)]
    usb_candidates = []
    for d in profile.get("usb_devices", []):
        text = " ".join(str(d.get(k) or "") for k in ("manufacturer", "product_name", "modalias")).lower()
        if any(token in text for token in ("wireless", "wifi", "802.11", "wlan")):
            usb_candidates.append(d)
    result = {
        "status": "wifi-interface-present" if wireless_interfaces() else "wifi-interface-missing",
        "wireless_interfaces": wireless_interfaces(),
        "pci_network_candidates": candidates,
        "usb_wireless_candidates": usb_candidates,
        "loaded_modules": profile.get("loaded_modules", []),
        "firmware_search_hint": "match candidate modalias/vendor/device to an existing kernel module before driver synthesis",
        "read_only": True,
    }
    return result


def main() -> int:
    print("AURUM_WIFI_DIAG " + json.dumps(diagnose(), sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
