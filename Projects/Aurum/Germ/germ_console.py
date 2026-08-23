#!/usr/bin/env python3
"""Compatibility adapter exposing the protected germ through the Aurum console."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

GERM = Path("/usr/lib/aurum/germ/reseed.py")
GUARDIAN = Path("/usr/lib/aurum/germ/guardian.py")


def _run(args: list[str]) -> dict:
    result = subprocess.run(
        ["/usr/bin/python3", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=900,
    )
    text = result.stdout.strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {"status": "failed" if result.returncode else "finished", "detail": text[-2000:]}
    payload.setdefault("returncode", result.returncode)
    return payload


def handle_reseed(tokens: list[str]) -> dict:
    if not GERM.is_file():
        return {"status": "refused", "detail": "protected reseed germ is not installed"}
    if not tokens or tokens == ["status"]:
        germ = _run([str(GERM), "status"])
        guardian = _run([str(GUARDIAN), "status"]) if GUARDIAN.is_file() else {"status": "missing"}
        return {"schema": "aurum-reseed-console-v1", "germ": germ, "guardian": guardian}
    if tokens[0] == "plan":
        ref = tokens[1] if len(tokens) > 1 else "main"
        return _run([str(GERM), "plan", "--ref", ref])
    if tokens[0] == "current" and tokens[1:] == ["authorize-network"]:
        return _run([str(GERM), "regrow", "--ref", "main", "--authorize-network"])
    if tokens[0] == "commit" and len(tokens) == 3 and tokens[2] == "authorize-network":
        return _run([str(GERM), "regrow", "--ref", tokens[1], "--authorize-network"])
    if tokens[0] == "rollback" and tokens[1:] == ["confirm"] and GUARDIAN.is_file():
        return _run([str(GUARDIAN), "rollback", "--reason", "operator-confirmed"])
    return {
        "status": "refused",
        "detail": "use: reseed status | reseed plan [REF] | reseed current authorize-network | reseed commit SHA authorize-network | reseed rollback confirm",
    }
