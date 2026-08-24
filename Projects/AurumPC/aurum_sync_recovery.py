#!/usr/bin/env python3
"""Safe dirty-workspace checkpoint and sync helper for Aurum PC.

This helper exists specifically for the bootstrap case where the installed
Aurum console refuses git-sync because the workspace has legitimate local
changes. It preserves those changes before moving the workspace forward and
never uses reset --hard or force checkout.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
BRANCH = os.environ.get("AURUM_GIT_BRANCH", "aurum/trunk-v0.01")
STATE_DIR = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=WORKSPACE,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stdout.strip()[-2000:] or f"git exited {result.returncode}")
    return result


def main() -> int:
    if not (WORKSPACE / ".git").is_dir():
        print("AURUM_RECOVERY_SYNC status=failed detail=workspace-not-initialized")
        return 2

    origin = run("remote", "get-url", "origin").stdout.strip()
    if origin.rstrip("/").removesuffix(".git").lower() != "https://github.com/formatx66/boxbrain".lower():
        print("AURUM_RECOVERY_SYNC status=failed detail=unexpected-origin")
        return 2

    current_branch = run("branch", "--show-current").stdout.strip()
    if current_branch != BRANCH:
        print(f"AURUM_RECOVERY_SYNC status=failed detail=unexpected-branch:{current_branch}")
        return 2

    changes = [line for line in run("status", "--porcelain=v1").stdout.splitlines() if line]
    checkpoint = None
    if changes:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        checkpoint = f"aurum-auto-checkpoint-{stamp}"
        run("stash", "push", "-u", "-m", checkpoint)
        receipt = {
            "schema": "aurum-workspace-checkpoint-v1",
            "at": stamp,
            "branch": current_branch,
            "origin": origin,
            "checkpoint": checkpoint,
            "changes": changes,
            "preserved": True,
            "reapplied": False,
        }
        (STATE_DIR / "last-workspace-checkpoint.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    try:
        run("fetch", "--prune", "origin", BRANCH)
        run("merge", "--ff-only", "FETCH_HEAD")
    except Exception:
        # The checkpoint remains in the stash and on-disk receipt. Do not
        # automatically reapply it here: the updated runtime gets to inspect
        # and reconcile it deliberately after its health checks pass.
        raise

    payload = {
        "schema": "aurum-workspace-recovery-sync-v1",
        "status": "ready",
        "branch": run("branch", "--show-current").stdout.strip(),
        "head": run("rev-parse", "HEAD").stdout.strip(),
        "dirty": bool(run("status", "--porcelain=v1").stdout.strip()),
        "checkpoint": checkpoint,
        "checkpoint_preserved": checkpoint is not None,
        "checkpoint_reapplied": False,
        "next": "run-aurum-sync-from-updated-runtime",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(
        "AURUM_RECOVERY_SYNC status=ready checkpoint_preserved="
        + str(bool(checkpoint)).lower()
        + " checkpoint_reapplied=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
