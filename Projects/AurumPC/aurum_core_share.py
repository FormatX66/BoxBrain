#!/usr/bin/env python3
"""Open Aurum core status and forward-only seed sharing for peer nodes.

The core surface intentionally has no authentication. It exposes only two
fixed operations and never serves files, directories, credentials, Wi-Fi
profiles, user content, or Slush data.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # Windows source tests; Hopper runtime is Linux.
    fcntl = None

SCHEMA = "aurum.open-core-share.v1"
RECEIPT_SCHEMA = "aurum.open-core-sync-receipt.v1"
REPOSITORY = "https://github.com/FormatX66/BoxBrain.git"
BRANCH = "aurum/trunk-v0.01"
DEFAULT_BIND = os.environ.get("AURUM_CORE_SHARE_BIND", "0.0.0.0")
# The local Hopper GUI owns 8765 and its arcade owns 8766.  Keep the open
# core surface on its own listener so boot sync can never prevent the physical
# desktop from starting.
DEFAULT_PORT = int(os.environ.get("AURUM_CORE_SHARE_PORT", "8767"))
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_RUN = Path(os.environ.get("AURUM_RUN_DIR", "/run/aurum"))
DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
DEFAULT_RUNTIME = Path(os.environ.get("AURUM_RUNTIME_ROOT", "/opt/aurum"))
CORE_ACTIONS = ("status", "seed-sync")


class CoreShareError(RuntimeError):
    pass


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _load_module(filename: str, prefix: str):
    candidates = (
        DEFAULT_RUNTIME / filename,
        DEFAULT_WORKSPACE / "Projects" / "AurumPC" / filename,
        Path(__file__).with_name(filename),
    )
    for path in candidates:
        if not path.is_file():
            continue
        spec = importlib.util.spec_from_file_location(f"{prefix}_{os.getpid()}_{time.time_ns()}", path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    raise CoreShareError(f"required core module is unavailable: {filename}")


def catalog() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "machine": "Hopper",
        "visibility": "open-core",
        "authentication_required": False,
        "actions": list(CORE_ACTIONS),
        "repository": REPOSITORY,
        "branch": BRANCH,
        "port": DEFAULT_PORT,
        "fast_forward_only": True,
        "arbitrary_command": False,
        "file_serving": False,
        "directory_listing": False,
        "personal_slush": {
            "exported": False,
            "readable_by_core_share": False,
            "ownership": "user-only",
        },
    }


def _safe_git(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": value.get("status"),
        "repository": value.get("repository"),
        "branch": value.get("branch"),
        "head": value.get("head"),
        "dirty": value.get("dirty"),
    }


def _safe_runtime(value: dict[str, Any]) -> dict[str, Any]:
    generation = value.get("generation") if isinstance(value.get("generation"), dict) else {}
    proof = generation.get("prove") if isinstance(generation.get("prove"), dict) else {}
    return {
        "status": value.get("status"),
        "changed": list(value.get("changed") or []),
        "system_changed": list(value.get("system_changed") or []),
        "become_next_seed": generation.get("become_next_seed") is True,
        "proof_status": {
            name: item.get("status")
            for name, item in proof.items()
            if isinstance(name, str) and isinstance(item, dict)
        },
        "reboot_required": bool(value.get("reboot_required")),
    }


def _latest_public_sync(*, state_dir: Path = DEFAULT_STATE) -> dict[str, Any] | None:
    payload = _json_file(state_dir / "core-share" / "latest.json")
    if payload.get("schema") != RECEIPT_SCHEMA:
        return None
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    return {
        "status": result.get("status"),
        "head": (result.get("git") or {}).get("head") if isinstance(result.get("git"), dict) else None,
        "observed_at": payload.get("observed_at"),
    }


def status(*, state_dir: Path = DEFAULT_STATE) -> dict[str, Any]:
    git: dict[str, Any]
    try:
        workspace_module = _load_module("aurum_workspace.py", "aurum_core_status")
        workspace = workspace_module.AurumWorkspace(
            installed_root=DEFAULT_RUNTIME / "codelation",
            workspace=DEFAULT_WORKSPACE,
            state_dir=state_dir,
        )
        git = _safe_git(workspace.git_status())
    except Exception:
        git = {
            "status": "not-ready",
            "repository": REPOSITORY,
            "branch": BRANCH,
            "head": None,
            "dirty": None,
        }
    return {
        **catalog(),
        "status": "ready",
        "git": git,
        "latest_sync": _latest_public_sync(state_dir=state_dir),
    }


def seed_sync(*, state_dir: Path = DEFAULT_STATE) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise CoreShareError("core seed sync requires the root-owned Aurum service")
    DEFAULT_RUN.mkdir(parents=True, mode=0o700, exist_ok=True)
    lock_path = DEFAULT_RUN / "core-seed-sync.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        if fcntl is not None:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise CoreShareError("another forward seed sync is already running") from exc
        network = _load_module("aurum_network.py", "aurum_core_network")
        online = network.ensure_online(interactive=False)
        if online.get("online") is not True:
            raise CoreShareError("core network is offline")
        workspace_module = _load_module("aurum_workspace.py", "aurum_core_workspace")
        workspace = workspace_module.AurumWorkspace(
            installed_root=DEFAULT_RUNTIME / "codelation",
            workspace=DEFAULT_WORKSPACE,
            state_dir=state_dir,
        )
        git_result = workspace.git_sync(authorize_network=True)
        if git_result.get("status") not in {
            "ready",
            "cloned",
            "fast-forwarded",
            "fast-forwarded-with-checkpoint",
        }:
            raise CoreShareError("core Git sync did not reach a verified state")
        if (
            str(git_result.get("repository") or "").rstrip("/").removesuffix(".git")
            != REPOSITORY.removesuffix(".git")
            or git_result.get("branch") != BRANCH
            or git_result.get("dirty") is True
        ):
            raise CoreShareError("core Git sync left the fixed clean Aurum trunk")
        runtime_module = _load_module("aurum_runtime_update.py", "aurum_core_runtime")
        runtime_result = runtime_module.RuntimeUpdater(
            workspace=DEFAULT_WORKSPACE,
            target=DEFAULT_RUNTIME,
            state_dir=state_dir,
        ).apply()
        runtime = _safe_runtime(runtime_result)
        result = {
            "status": "verified" if runtime["become_next_seed"] else "applied-awaiting-proof",
            "git": _safe_git(git_result),
            "runtime": runtime,
            "fast_forward_only": True,
            "personal_slush_accessed": False,
            "personal_data_exported": False,
        }
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "machine": "Hopper",
            "result": result,
            "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _atomic_json(state_dir / "core-share" / "latest.json", receipt)
        return receipt


class CoreShareHandler(BaseHTTPRequestHandler):
    server_version = "AurumOpenCore/1"

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        body = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib handler contract
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler contract
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        if self.path in {"/", "/status"}:
            self._send(200, status())
            return
        self._send(404, {"schema": SCHEMA, "status": "not-found", "actions": list(CORE_ACTIONS)})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        length = int(self.headers.get("Content-Length", "0") or "0")
        if self.path != "/seed-sync" or length != 0:
            self._send(404, {"schema": SCHEMA, "status": "not-found", "actions": list(CORE_ACTIONS)})
            return
        try:
            result = seed_sync()
        except Exception as exc:
            self._send(
                503,
                {
                    "schema": SCHEMA,
                    "status": "sync-unavailable",
                    "error_class": type(exc).__name__,
                    "personal_data_exported": False,
                },
            )
            return
        self._send(200, result)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class CoreShareServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(*, bind: str = DEFAULT_BIND, port: int = DEFAULT_PORT) -> None:
    if not 1 <= port <= 65535:
        raise CoreShareError("core share port is invalid")
    server = CoreShareServer((bind, port), CoreShareHandler)
    server.serve_forever(poll_interval=0.25)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aurum open core share")
    parser.add_argument("action", choices=("catalog", "status", "seed-sync", "serve"))
    parser.add_argument("--bind", default=DEFAULT_BIND)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    try:
        if args.action == "catalog":
            result = catalog()
        elif args.action == "status":
            result = status()
        elif args.action == "seed-sync":
            result = seed_sync()
        else:
            serve(bind=args.bind, port=args.port)
            return 0
    except CoreShareError as exc:
        print(json.dumps({"schema": SCHEMA, "status": "failed", "detail": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
