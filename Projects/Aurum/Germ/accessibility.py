#!/usr/bin/env python3
"""Start Tiny Seed's explicit spoken/blind boot path."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


CMDLINE = Path("/proc/cmdline")
MARKER = "AURUM_TINYSEED_ACCESSIBILITY_READY screen_reader=true ui=plain"


def boot_tokens(raw: str | None = None) -> set[str]:
    if raw is None:
        raw = os.environ.get("AURUM_TINYSEED_CMDLINE")
    if raw is None:
        try:
            raw = CMDLINE.read_text(encoding="utf-8")
        except OSError:
            raw = ""
    return {token.strip() for token in raw.split() if token.strip()}


def enabled(raw: str | None = None) -> bool:
    return "aurum.accessibility=blind" in boot_tokens(raw)


def _run(args: list[str]) -> bool:
    executable = shutil.which(args[0])
    if not executable:
        return False
    result = subprocess.run(
        [executable, *args[1:]],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=20,
    )
    return result.returncode == 0


def _announce(value: str) -> None:
    print(value, flush=True)
    for target in (Path("/dev/console"), Path("/dev/ttyS0")):
        try:
            if target.exists():
                target.write_text(value + "\n", encoding="utf-8")
        except OSError:
            continue


def activate() -> bool:
    if not enabled():
        return True
    module_ready = _run(["modprobe", "speakup_soft"])
    daemon_ready = module_ready and _run(["systemctl", "start", "espeakup.service"])
    active = daemon_ready and _run(["systemctl", "is-active", "--quiet", "espeakup.service"])
    if active:
        _announce(MARKER)
        return True
    _announce("AURUM_TINYSEED_ACCESSIBILITY_FAILED screen_reader=false ui=plain")
    return False


def main() -> int:
    return 0 if activate() else 1


if __name__ == "__main__":
    raise SystemExit(main())
