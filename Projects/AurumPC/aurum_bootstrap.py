#!/usr/bin/env python3
"""Aurum PC boot entry point with read-only exact-machine evidence capture."""
from __future__ import annotations

import json

import aurum_console
from aurum_hardware import (
    DEFAULT_PLAN,
    DEFAULT_PROFILE,
    capture_hardware_evidence,
    collect_hardware_profile,
)


def main() -> int:
    try:
        profile, plan = capture_hardware_evidence()
        print(
            "AURUM_HARDWARE_PROFILE "
            f"status=ready profile={DEFAULT_PROFILE} plan={DEFAULT_PLAN} "
            f"pci={len(profile['pci_devices'])} usb={len(profile['usb_devices'])} "
            f"block={len(profile['block_devices'])} input={len(profile['input_devices'])} "
            f"graphics={len(profile['graphics_devices'])} net={len(profile['network_interfaces'])} "
            f"drivers={len(plan['required_existing_drivers'])} unresolved={len(plan['unresolved_devices'])}",
            flush=True,
        )
    except Exception as exc:  # evidence collection must never prevent recovery-console boot
        print(
            "AURUM_HARDWARE_PROFILE "
            f"status=degraded detail={json.dumps(type(exc).__name__ + ':' + str(exc))}",
            flush=True,
        )

    # Preserve the existing bounded operator surface while upgrading its
    # hardware/status view to a fresh detailed read-only profile.  This avoids
    # adding an arbitrary shell or a second command interpreter.
    aurum_console.hardware = collect_hardware_profile
    return aurum_console.main()


if __name__ == "__main__":
    raise SystemExit(main())
