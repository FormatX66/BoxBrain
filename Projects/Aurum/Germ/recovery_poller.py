#!/usr/bin/env python3
"""Poll the public desired-state channel and apply only signed bounded recovery.

The transport is not trusted. Authenticity comes from the enrolled Ed25519 key,
request freshness, per-machine addressing, immutable refs, and replay protection.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import recovery_control


DESIRED_STATE_URL = os.environ.get(
    "AURUM_RECOVERY_URL",
    "https://raw.githubusercontent.com/FormatX66/BoxBrain/main/Projects/Aurum/Recovery/desired-state.json",
)
PUBLIC_KEY = Path(os.environ.get("AURUM_RECOVERY_PUBLIC_KEY", "/etc/aurum/recovery-authority.pem"))
TRUST_FILE = Path(os.environ.get("AURUM_RECOVERY_TRUST_FILE", "/etc/aurum/recovery-trusted-refs.json"))
MACHINE_ID = Path(os.environ.get("AURUM_RECOVERY_NODE_ID_FILE", "/etc/machine-id"))
STATE_ROOT = Path(os.environ.get("AURUM_GERM_STATE_ROOT", "/var/lib/aurum/germ"))
SLOT_STATE = STATE_ROOT / "slots.json"
REPLAY_FILE = STATE_ROOT / "recovery-replay.json"
RECEIPT_ROOT = STATE_ROOT / "recovery-receipts"


class PollerError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PollerError(f"state unreadable: {path}: {exc}") from exc
    return value if isinstance(value, dict) else {}


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _node_id() -> str:
    try:
        node_id = MACHINE_ID.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise PollerError(f"machine identity unavailable: {exc}") from exc
    if len(node_id) < 8 or len(node_id) > 128:
        raise PollerError("machine identity is invalid")
    return node_id


def _fetch() -> dict[str, Any]:
    request = urllib.request.Request(
        DESIRED_STATE_URL,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "Aurum-Recovery-Poller/1",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(262144)
    except Exception as exc:
        raise PollerError(f"desired-state fetch failed: {type(exc).__name__}") from exc
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        raise PollerError("desired-state response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise PollerError("desired-state response must be an object")
    return value


def _replay() -> dict[str, Any]:
    if not REPLAY_FILE.exists():
        return {"schema": "aurum-recovery-replay-v1", "consumed": []}
    value = _json(REPLAY_FILE)
    if value.get("schema") != "aurum-recovery-replay-v1" or not isinstance(value.get("consumed"), list):
        raise PollerError("recovery replay state is invalid")
    return value


def _already_consumed(request_id: str) -> bool:
    return any(
        isinstance(item, dict) and item.get("request_id") == request_id
        for item in _replay()["consumed"]
    )


def _consume(request_id: str, result: dict[str, Any]) -> None:
    state = _replay()
    entries = [item for item in state["consumed"] if isinstance(item, dict)]
    entries.append(
        {
            "request_id": request_id,
            "consumed_at_unix": int(time.time()),
            "result": str(result.get("status") or result.get("state") or "applied")[:128],
        }
    )
    state["consumed"] = entries[-128:]
    _atomic_json(REPLAY_FILE, state)


def _run_json(args: list[str], timeout: int) -> dict[str, Any]:
    result = subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=timeout,
    )
    output = result.stdout.strip()
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        value = {"status": "command-failed", "detail": output[-2000:]}
    if result.returncode != 0:
        raise PollerError(str(value.get("detail") or output[-2000:] or "recovery action failed"))
    if not isinstance(value, dict):
        raise PollerError("recovery action returned invalid state")
    return value


def _steady_lkg() -> tuple[bool, dict[str, Any]]:
    state = _json(SLOT_STATE)
    return (
        state.get("active") == state.get("lkg") and state.get("trial") is None,
        state,
    )


def _apply(request: dict[str, Any]) -> dict[str, Any]:
    target = request["target"]
    request_id = request["request_id"]
    germ = Path(__file__).resolve().parent
    guardian = germ / "guardian.py"
    reseed = germ / "reseed.py"

    if target in {"last-known-good", "previous"}:
        steady, before = _steady_lkg()
        if target == "previous" and steady:
            raise PollerError("previous recovery state is unavailable while Guardian is steady")
        if steady:
            return {
                "status": "already-last-known-good",
                "active": before.get("active"),
                "lkg": before.get("lkg"),
            }
        return _run_json(
            [
                sys.executable,
                str(guardian),
                "rollback",
                "--reason",
                f"signed-remote-recovery:{request_id}",
            ],
            timeout=30,
        )

    ref = request.get("ref")
    if not isinstance(ref, str):
        raise PollerError("specific recovery request lost its immutable ref")
    result = _run_json(
        [
            sys.executable,
            str(reseed),
            "regrow",
            "--ref",
            ref,
            "--authorize-network",
        ],
        timeout=1200,
    )
    if result.get("status") not in {"trial-armed", "platform-source-staged"}:
        raise PollerError(f"specific recovery did not reach a safe staged state: {result.get('status')}")
    return result


def poll_once() -> dict[str, Any]:
    desired = _fetch()
    if desired.get("schema") == "aurum-recovery-idle-v1" and desired.get("state") == "idle":
        return {"status": "idle"}
    if not PUBLIC_KEY.is_file():
        return {"status": "disabled-no-authority"}
    if not TRUST_FILE.is_file():
        raise PollerError("recovery trust file is missing")

    trusted = recovery_control.load_trusted_commits(TRUST_FILE)
    request = recovery_control.verify_envelope(
        desired,
        public_key=PUBLIC_KEY,
        local_node_id=_node_id(),
        trusted_commits=trusted,
    )
    request_id = request["request_id"]
    if _already_consumed(request_id):
        return {"status": "replay-ignored", "request_id": request_id}

    result = _apply(request)
    receipt = {
        "schema": "aurum-remote-recovery-receipt-v1",
        "status": "applied",
        "request": request,
        "result": result,
        "applied_at_unix": int(time.time()),
    }
    RECEIPT_ROOT.mkdir(parents=True, exist_ok=True)
    _atomic_json(RECEIPT_ROOT / f"{request_id}.json", receipt)
    _consume(request_id, result)

    if request.get("reboot") is True:
        trial_armed = result.get("status") == "trial-armed"
        rollback_changed_active = result.get("status") == "rollback"
        if trial_armed or rollback_changed_active:
            subprocess.run(["/bin/systemctl", "reboot"], check=False, timeout=10)
            receipt["reboot_requested"] = True
    return receipt


def main() -> int:
    try:
        result = poll_once()
    except (PollerError, recovery_control.RecoveryControlError) as exc:
        print(json.dumps({"status": "refused", "detail": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
