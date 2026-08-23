#!/usr/bin/env python3
"""Bounded direct-control executor for GPT inside Aurum on Hopper.

GPT may inspect Aurum source, but the running machine never edits the tracked
seed workspace for an appearance experiment. Live appearance changes are
written to reboot-ephemeral runtime state instead. Every action is a named
capability with bounded arguments, local authorization, and a durable receipt.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

SCHEMA = "aurum.gpt-executor.gen1-direct-control"
RECEIPT_SCHEMA = "aurum.gpt-control-receipt.gen1-direct-control"
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
DEFAULT_RUNTIME = Path(os.environ.get("AURUM_RUNTIME_ROOT", "/opt/aurum"))
DEFAULT_APPEARANCE = Path(os.environ.get("AURUM_APPEARANCE_STATE", "/run/aurum/appearance.json"))

CONTROL_ACTIONS = (
    "status",
    "time-sync",
    "network-reconnect",
    "input-status",
    "input-recover",
    "runtime-plan",
    "runtime-sync",
    "gui-status",
    "gui-restart",
)

EDITABLE_ROOTS = (
    Path("Projects/AurumPC"),
    Path("Projects/Codelation"),
)
EDITABLE_SUFFIXES = {".py", ".json", ".md"}
MAX_READ_LINES = 500

APPEARANCE_THEMES = {
    "default": {"background_start": "#050706", "background_end": "#070b09"},
    "midnight": {"background_start": "#050711", "background_end": "#090d1b"},
    "forest": {"background_start": "#06110c", "background_end": "#0a1a12"},
    "ocean": {"background_start": "#050f18", "background_end": "#071a26"},
    "ember": {"background_start": "#160b07", "background_end": "#241108"},
    "violet": {"background_start": "#100819", "background_end": "#1b0d29"},
    "aurum": {"background_start": "#151006", "background_end": "#211807"},
}


class GptExecutorError(RuntimeError):
    pass


def catalog() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "machine": "Hopper",
        "authority": "aurum-policy-broker",
        "direct_shell_contract": False,
        "control_actions": list(CONTROL_ACTIONS),
        "appearance": {
            "preview": True,
            "themes": list(APPEARANCE_THEMES),
            "tracked_source_modified": False,
            "resets_on_reboot": True,
        },
        "workspace": {
            "read": True,
            "exact_replace": False,
            "mutation": False,
            "editable_roots": [str(path) for path in EDITABLE_ROOTS],
            "editable_suffixes": sorted(EDITABLE_SUFFIXES),
            "promotion": "verified-next-seed-only",
            "git_push": False,
        },
    }


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _module(name: str):
    candidates = (
        DEFAULT_RUNTIME / f"{name}.py",
        DEFAULT_WORKSPACE / "Projects" / "AurumPC" / f"{name}.py",
        Path(__file__).with_name(f"{name}.py"),
    )
    for path in candidates:
        if not path.is_file():
            continue
        spec = importlib.util.spec_from_file_location(
            f"{name}_{os.getpid()}_{time.time_ns()}", path
        )
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    raise GptExecutorError(f"Aurum module unavailable: {name}")


def _safe_workspace_path(relative_path: str) -> tuple[Path, Path]:
    raw = Path(str(relative_path or "").strip())
    if raw.is_absolute() or ".." in raw.parts:
        raise GptExecutorError("workspace path must be relative and traversal-free")
    if raw.suffix.lower() not in EDITABLE_SUFFIXES:
        raise GptExecutorError(f"workspace suffix is not editable: {raw.suffix or '<none>'}")
    allowed = any(raw == root or root in raw.parents for root in EDITABLE_ROOTS)
    if not allowed:
        raise GptExecutorError("workspace path is outside the GPT edit envelope")
    workspace = DEFAULT_WORKSPACE.resolve()
    target = (workspace / raw).resolve()
    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise GptExecutorError("workspace path escaped the repository") from exc
    return raw, target


def _receipt(operation: str, result: dict[str, Any], *, state_dir: Path = DEFAULT_STATE) -> dict[str, Any]:
    payload = {
        "schema": RECEIPT_SCHEMA,
        "operation": operation,
        "machine": "Hopper",
        "result": result,
        "direct_shell_contract": False,
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    root = state_dir / "gpt-control"
    root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    unique = f"{stamp}-{time.time_ns() % 1_000_000_000:09d}"
    path = root / f"{unique}-{operation.replace('/', '-')}.json"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    latest = root / "latest.json"
    latest_temp = latest.with_name(f".{latest.name}.{os.getpid()}.tmp")
    latest_temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(latest_temp, latest)
    payload["receipt_path"] = str(path)
    return payload


def status_snapshot(state: Path = DEFAULT_STATE) -> dict[str, Any]:
    identity = _json_file(state / "machine-identity.json")
    runtime = _json_file(state / "runtime-update.json")
    desktop = _json_file(state / "desktop-ui.json")
    autonomy = _json_file(state / "autonomy.json")
    input_state = _json_file(Path("/run/aurum-input-status.json"))
    return {
        "machine": identity.get("display_name") or "Hopper",
        "hostname": identity.get("hostname") or "hopper",
        "runtime": runtime.get("status") or "unknown",
        "desktop": desktop.get("status") or "unknown",
        "desktop_generation": desktop.get("generation_name") or "unknown",
        "autonomy": autonomy.get("status") or "unknown",
        "input": input_state.get("status") or "unknown",
    }


def appearance_snapshot(*, appearance_path: Path | None = None) -> dict[str, Any]:
    """Return only a valid reboot-ephemeral appearance preview."""
    path = appearance_path or DEFAULT_APPEARANCE
    value = _json_file(path)
    theme = str(value.get("theme") or "default")
    if value.get("schema") != "aurum.appearance-preview.v1" or theme not in APPEARANCE_THEMES:
        theme = "default"
        active = False
    else:
        active = theme != "default"
    return {
        "schema": "aurum.appearance-preview.v1",
        "status": "active" if active else "default",
        "theme": theme,
        **APPEARANCE_THEMES[theme],
        "temporary": True,
        "resets_on_reboot": True,
        "tracked_source_modified": False,
    }


def set_appearance(
    theme: str,
    *,
    appearance_path: Path | None = None,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """Apply a bounded live theme without touching the Git workspace."""
    selected = str(theme or "").strip().lower()
    if selected not in APPEARANCE_THEMES:
        raise GptExecutorError(f"unsupported appearance theme: {selected or '<empty>'}")
    path = appearance_path or DEFAULT_APPEARANCE
    if selected == "default":
        path.unlink(missing_ok=True)
    else:
        payload = {
            "schema": "aurum.appearance-preview.v1",
            "theme": selected,
            **APPEARANCE_THEMES[selected],
            "temporary": True,
            "resets_on_reboot": True,
            "tracked_source_modified": False,
            "applied_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    result = appearance_snapshot(appearance_path=path)
    result["status"] = "reset" if selected == "default" else "previewing"
    return _receipt("appearance-preview", result, state_dir=state_dir or DEFAULT_STATE)


def execute_control(action: str, *, state_dir: Path | None = None) -> dict[str, Any]:
    action = str(action or "").strip().lower()
    receipt_state = state_dir or DEFAULT_STATE
    if action not in CONTROL_ACTIONS:
        raise GptExecutorError(f"unsupported GPT control action: {action or '<empty>'}")

    if action == "status":
        result = {"status": "observed", "state": status_snapshot(receipt_state)}
    elif action == "time-sync":
        module = _module("aurum_time")
        result = module.synchronize_clock(timeout_seconds=20)
    elif action == "network-reconnect":
        module = _module("aurum_network")
        result = module.ensure_online(interactive=False)
    elif action in {"input-status", "input-recover"}:
        module = _module("aurum_input")
        result = module.status(apply_wake=action == "input-recover")
    elif action in {"runtime-plan", "runtime-sync"}:
        module = _module("aurum_runtime_update")
        updater = module.RuntimeUpdater(
            workspace=DEFAULT_WORKSPACE,
            state_dir=DEFAULT_STATE,
        )
        result = updater.plan() if action == "runtime-plan" else updater.apply()
    elif action in {"gui-status", "gui-restart"}:
        module = _module("aurum_gui_runtime")
        gui = module.GuiRuntime(
            workspace=DEFAULT_WORKSPACE,
            state_dir=DEFAULT_STATE,
            runtime_root=DEFAULT_RUNTIME,
        )
        if action == "gui-status":
            result = gui.status()
        else:
            stopped = None
            try:
                stopped = gui.stop()
            except Exception as exc:  # recovery action remains bounded even if stop state is stale
                stopped = {"status": "stop-failed", "detail": f"{type(exc).__name__}:{exc}"}
            started = gui.start()
            result = {"status": started.get("status") or "unknown", "stop": stopped, "start": started}
    else:  # pragma: no cover - CONTROL_ACTIONS keeps this unreachable
        raise GptExecutorError(f"unimplemented GPT action: {action}")

    if not isinstance(result, dict):
        result = {"status": "completed", "value": result}
    return _receipt(action, result, state_dir=receipt_state)


def read_workspace(relative_path: str, *, start_line: int = 1, end_line: int = 240) -> dict[str, Any]:
    raw, target = _safe_workspace_path(relative_path)
    if not target.is_file():
        raise GptExecutorError(f"workspace file does not exist: {raw}")
    start = max(1, int(start_line))
    end = max(start, int(end_line))
    if end - start + 1 > MAX_READ_LINES:
        end = start + MAX_READ_LINES - 1
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    selected = lines[start - 1 : end]
    result = {
        "status": "read",
        "path": str(raw),
        "start_line": start,
        "end_line": start + len(selected) - 1 if selected else start - 1,
        "line_count": len(lines),
        "content": "\n".join(selected),
    }
    return _receipt("workspace-read", result, state_dir=DEFAULT_STATE)


def replace_workspace(relative_path: str, before: str, after: str) -> dict[str, Any]:
    del relative_path, before, after
    raise GptExecutorError(
        "tracked seed source is immutable at runtime; use a temporary bounded control "
        "or promote a verified next seed"
    )


def main() -> int:
    print(json.dumps(catalog(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
