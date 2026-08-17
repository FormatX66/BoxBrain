#!/usr/bin/env python3
"""Bounded clock recovery for Aurum PC first boot.

The physical HP boot produced a timestamp months behind the actual date.  That
can make HTTPS/Git operations fail even after basic TCP networking is working.
This helper asks systemd-timesyncd to synchronize from NTP and records evidence;
it does not write firmware RTC/NVRAM or require the clock to be correct for
offline Aurum self-builds.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from typing import Any


def _run(arguments: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def _ntp_synchronized() -> bool:
    timedatectl = shutil.which("timedatectl")
    if not timedatectl:
        return False
    result = _run([timedatectl, "show", "--property=NTPSynchronized", "--value"], timeout=5)
    return result.returncode == 0 and result.stdout.strip().lower() == "yes"


def synchronize_clock(*, timeout_seconds: int = 35) -> dict[str, Any]:
    before_epoch = int(time.time())
    timedatectl = shutil.which("timedatectl")
    systemctl = shutil.which("systemctl")
    if not timedatectl or not systemctl:
        return {
            "status": "helper-unavailable",
            "before_epoch": before_epoch,
            "after_epoch": int(time.time()),
            "synchronized": False,
        }

    _run([timedatectl, "set-ntp", "true"], timeout=5)
    _run([systemctl, "start", "systemd-timesyncd.service"], timeout=10)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _ntp_synchronized():
            return {
                "status": "synchronized",
                "before_epoch": before_epoch,
                "after_epoch": int(time.time()),
                "synchronized": True,
            }
        time.sleep(1)
    return {
        "status": "timeout",
        "before_epoch": before_epoch,
        "after_epoch": int(time.time()),
        "synchronized": _ntp_synchronized(),
    }
