#!/usr/bin/env python3
"""Minimal healthy phenotype used only as the Tiny Seed bootstrap/LKG slot."""
from __future__ import annotations

import json
import platform
import time


def selftest() -> tuple[bool, str]:
    return True, "tiny-seed-bootstrap"


def main() -> int:
    print(
        json.dumps(
            {
                "schema": "aurum-tinyseed-bootstrap-v1",
                "status": "ready",
                "architecture": platform.machine(),
                "purpose": "protected germ bootstrap; regrow current genetics to replace this phenotype",
                "started_at_unix": int(time.time()),
            },
            indent=2,
            sort_keys=True,
        ),
        flush=True,
    )
    while True:
        try:
            command = input("aurum-germ> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            continue
        if command in {"status", "help", "?", ""}:
            print("Tiny Seed bootstrap is healthy. Use the setup screen or aurum-reseed regrow --authorize-network.")
        elif command in {"reboot", "poweroff"}:
            import subprocess
            subprocess.run(["/bin/systemctl", command], check=False)
        else:
            print("Bootstrap surface is intentionally minimal; use the Tiny Seed setup screen.")


if __name__ == "__main__":
    raise SystemExit(main())
