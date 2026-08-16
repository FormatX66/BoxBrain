#!/usr/bin/env python3
from __future__ import annotations

import json
import getpass
import os
import platform
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

from aurum_installer import AurumInstaller, InstallError
from aurum_workspace import AurumWorkspace, WorkspaceError

VERSION = "0.01"
ROOT = Path(os.environ.get("AURUM_ROOT", "/opt/aurum"))
CODELATION = ROOT / "codelation"
STATE = CODELATION / "autobuild" / "native_chain_state.json"
WORKSPACE = AurumWorkspace(
    installed_root=CODELATION,
    workspace=Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain")),
    state_dir=Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state")),
)


class SelfBuildController:
    """Keep the console responsive while one bounded self-build runs."""

    def __init__(self, workspace: AurumWorkspace) -> None:
        self.workspace = workspace
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._done = threading.Event()
        self._started = 0.0
        self._latest: dict = {"status": "idle"}

    def _progress(self, payload: dict) -> None:
        with self._lock:
            self._latest = dict(payload)
        fields = [
            f"stage={payload.get('stage')}",
            f"status={payload.get('status')}",
            f"elapsed={payload.get('elapsed_seconds')}s",
        ]
        if payload.get("generation") is not None:
            fields.append(f"generation={payload['generation']}/{payload.get('total_generations', '?')}")
        if payload.get("gap"):
            fields.append(f"gap={payload['gap']}")
        if payload.get("upper_bound_eta_seconds") is not None:
            fields.append(f"upper_bound_eta={payload['upper_bound_eta_seconds']}s")
        print("AURUM_SELF_BUILD_PROGRESS " + " ".join(fields), flush=True)

    def _heartbeat(self) -> None:
        while not self._done.wait(15):
            with self._lock:
                latest = dict(self._latest)
                elapsed = round(time.monotonic() - self._started, 1)
            fields = [
                "status=running",
                f"elapsed={elapsed}s",
                f"stage={latest.get('stage', 'starting')}",
            ]
            if latest.get("generation") is not None:
                fields.append(f"generation={latest['generation']}/{latest.get('total_generations', '?')}")
            if latest.get("upper_bound_eta_seconds") is not None:
                fields.append(f"upper_bound_eta={latest['upper_bound_eta_seconds']}s")
            print("AURUM_SELF_BUILD_HEARTBEAT " + " ".join(fields), flush=True)

    def _run(self) -> None:
        heartbeat = threading.Thread(target=self._heartbeat, name="aurum-self-build-heartbeat", daemon=True)
        heartbeat.start()
        try:
            result = self.workspace.self_build(progress=self._progress, cancel_event=self._cancel)
            with self._lock:
                self._latest = {"status": "passed", "result": result}
            print(json.dumps(result, indent=2, sort_keys=True), flush=True)
            print("AURUM_SELF_BUILD_FINISHED status=passed", flush=True)
        except WorkspaceError as exc:
            status = "cancelled" if self._cancel.is_set() else "failed"
            with self._lock:
                self._latest = {"status": status, "detail": str(exc)}
            print(f"AURUM_SELF_BUILD_FINISHED status={status} detail={exc}", flush=True)
        finally:
            self._done.set()

    def start(self) -> dict:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return {"status": "already-running", **self.status(locked=True)}
            self._cancel = threading.Event()
            self._done = threading.Event()
            self._started = time.monotonic()
            self._latest = {"status": "starting", "stage": "startup"}
            self._thread = threading.Thread(target=self._run, name="aurum-self-build", daemon=True)
            self._thread.start()
            return {"status": "started", "background": True, "commands": ["self-build-status", "self-build-cancel"]}

    def status(self, *, locked: bool = False) -> dict:
        def snapshot() -> dict:
            running = self._thread is not None and self._thread.is_alive()
            elapsed = round(time.monotonic() - self._started, 1) if self._started else 0.0
            return {"running": running, "elapsed_seconds": elapsed, "latest": dict(self._latest)}

        if locked:
            return snapshot()
        with self._lock:
            return snapshot()

    def cancel(self) -> dict:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                return {"status": "not-running"}
            self._cancel.set()
            return {"status": "cancellation-requested", "checkpoint_preserved": True}


BUILDS = SelfBuildController(WORKSPACE)
INSTALLER = AurumInstaller()


def _read_text(path: Path, default: str = "unknown") -> str:
    try:
        value = path.read_text(encoding="utf-8", errors="replace").strip()
        return value or default
    except OSError:
        return default


def _chain_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def hardware() -> dict:
    memory_kib = "unknown"
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                memory_kib = line.split()[1]
                break
    except OSError:
        pass

    block = []
    try:
        block = sorted(p.name for p in Path("/sys/class/block").iterdir())
    except OSError:
        pass

    net = []
    try:
        net = sorted(p.name for p in Path("/sys/class/net").iterdir())
    except OSError:
        pass

    return {
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "machine": _read_text(Path("/sys/class/dmi/id/product_name")),
        "vendor": _read_text(Path("/sys/class/dmi/id/sys_vendor")),
        "memory_kib": memory_kib,
        "block_devices": block,
        "network_interfaces": net,
    }


def selftest() -> tuple[bool, str]:
    field_dir = CODELATION / "field"
    if not field_dir.is_dir():
        return False, "codelation-field-missing"
    sys.path.insert(0, str(field_dir))
    try:
        from local_capability_verification import verify_local_capability_for_gap
        from native_gap_catalog import get_native_semantic_gap

        gap = get_native_semantic_gap("io_safe_port_choice")
        if gap is None:
            return False, "io-safe-port-gap-missing"
        verification = verify_local_capability_for_gap(gap, "io-plan")
        if not verification.verified:
            return False, "io-plan-verification-failed"
        return True, f"io-plan={verification.invocation_output}"
    except Exception as exc:  # bounded boot diagnostic; no mutation occurs
        return False, f"{type(exc).__name__}:{exc}"


def show_status() -> None:
    state = _chain_state()
    payload = {
        "aurum_pc_version": VERSION,
        "runtime_mode": "installed" if Path("/etc/aurum-installed.json").is_file() else "live",
        "substrate": "linux-hardware-compatibility-layer",
        "hardware": hardware(),
        "aurum": {
            "completed_generations": state.get("completed_generations"),
            "latest_completed_gap": state.get("latest_completed_gap"),
            "next_gap": state.get("next_gap"),
            "blocked_reason": state.get("blocked_reason"),
            "blocked_output": state.get("blocked_output"),
            "trusted_for_continuation": (state.get("workflow_verification") or {}).get("trusted_for_continuation"),
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True), flush=True)


def show_field() -> None:
    state = _chain_state()
    print("AURUM_FIELD", flush=True)
    print("native=" + ",".join(state.get("reusable_native_capabilities") or []), flush=True)
    print("local=" + ",".join(state.get("reusable_local_capabilities") or []), flush=True)


def explicit_power(action: str) -> None:
    print(f"AURUM_PC_{action.upper()} requested=true", flush=True)
    subprocess.run([f"/sbin/{action}"], check=False)


def show_result(operation) -> None:
    try:
        result = operation()
        print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    except WorkspaceError as exc:
        print(f"AURUM_WORKSPACE_REFUSED detail={exc}", flush=True)


def show_install_plan() -> None:
    try:
        plan = INSTALLER.plan()
    except InstallError as exc:
        print(f"AURUM_INSTALL_PLAN status=refused detail={exc}", flush=True)
        return
    print(json.dumps(plan, indent=2, sort_keys=True), flush=True)
    targets = plan.get("targets") or []
    print(
        f"AURUM_INSTALL_PLAN status={'ready' if plan.get('available') else 'unavailable'} "
        f"targets={len(targets)} reason={plan.get('reason')}",
        flush=True,
    )
    for target in targets:
        print(
            "AURUM_INSTALL_TARGET "
            f"device={target['device']} size_gib={target['size_gib']} "
            f"model={json.dumps(target['model'])} confirm={target['confirmation_code']}",
            flush=True,
        )


def run_install(confirmation_code: str) -> None:
    if BUILDS.status()["running"]:
        print("AURUM_INSTALL_FINISHED status=refused detail=self-build-is-running", flush=True)
        return

    def progress(event: dict) -> None:
        fields = [f"phase={event.get('phase')}"]
        if event.get("device"):
            fields.append(f"device={event['device']}")
        print("AURUM_INSTALL_PROGRESS " + " ".join(fields), flush=True)

    try:
        result = INSTALLER.install(confirmation_code, progress=progress)
        print(json.dumps(result, indent=2, sort_keys=True), flush=True)
        print(
            f"AURUM_INSTALL_FINISHED status=passed device={result['device']} "
            "next=poweroff-remove-usb-start-pc",
            flush=True,
        )
    except InstallError as exc:
        print(f"AURUM_INSTALL_FINISHED status=refused detail={exc}", flush=True)


def command_help() -> None:
    print(
        "status | hardware | field | selftest | seed | seed-status | self-build | "
        "self-build-status | self-build-cancel | "
        "git-status | git-sync authorize-network | git-auth | "
        "git-promote authorize-network confirm-push | install | "
        "install confirm ERASE-CODE | reboot | poweroff | help",
        flush=True,
    )


def main() -> int:
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    ok, detail = selftest()
    hw = hardware()
    print(
        "AURUM_PC_READY "
        f"version={VERSION} arch={hw['architecture']} kernel={hw['kernel']} "
        f"mode={'installed' if Path('/etc/aurum-installed.json').is_file() else 'live'} "
        f"selftest={'ok' if ok else 'failed'} detail={detail}",
        flush=True,
    )
    command_help()

    while True:
        try:
            raw_command = input("aurum> ").strip()
        except EOFError:
            return 0
        except KeyboardInterrupt:
            print("", flush=True)
            continue

        try:
            tokens = shlex.split(raw_command)
        except ValueError as exc:
            print(f"AURUM_COMMAND_INVALID detail={exc}", flush=True)
            continue
        command = tokens[0].lower() if tokens else "help"
        if command in {"help", "?"} and len(tokens) <= 1:
            command_help()
        elif command == "status" and len(tokens) == 1:
            show_status()
        elif command == "hardware" and len(tokens) == 1:
            print(json.dumps(hardware(), indent=2, sort_keys=True), flush=True)
        elif command == "field" and len(tokens) == 1:
            show_field()
        elif command == "selftest" and len(tokens) == 1:
            test_ok, test_detail = selftest()
            print(f"AURUM_SELFTEST status={'ok' if test_ok else 'failed'} detail={test_detail}", flush=True)
        elif command == "seed" and len(tokens) == 1:
            show_result(WORKSPACE.seed)
        elif command == "seed-status" and len(tokens) == 1:
            show_result(WORKSPACE.seed_status)
        elif command == "self-build" and len(tokens) == 1:
            print(json.dumps(BUILDS.start(), indent=2, sort_keys=True), flush=True)
        elif command == "self-build-status" and len(tokens) == 1:
            print(json.dumps(BUILDS.status(), indent=2, sort_keys=True), flush=True)
        elif command == "self-build-cancel" and len(tokens) == 1:
            print(json.dumps(BUILDS.cancel(), indent=2, sort_keys=True), flush=True)
        elif command == "git-status" and len(tokens) == 1:
            show_result(WORKSPACE.git_status)
        elif command == "git-sync" and len(tokens) == 2:
            show_result(lambda: WORKSPACE.git_sync(authorize_network=tokens[1].lower() == "authorize-network"))
        elif command == "git-auth" and len(tokens) == 1:
            token = getpass.getpass("GitHub token (kept in memory for one hour): ")
            try:
                show_result(lambda: WORKSPACE.git_auth(token))
            finally:
                token = ""
        elif command == "git-promote" and len(tokens) == 3:
            show_result(
                lambda: WORKSPACE.git_promote(
                    authorize_network=tokens[1].lower() == "authorize-network",
                    confirm_push=tokens[2].lower() == "confirm-push",
                )
            )
        elif command == "install" and len(tokens) == 1:
            show_install_plan()
        elif command == "install" and len(tokens) == 3 and tokens[1].lower() == "confirm":
            run_install(tokens[2])
        elif command == "reboot" and len(tokens) == 1:
            explicit_power("reboot")
        elif command == "poweroff" and len(tokens) == 1:
            explicit_power("poweroff")
        else:
            print("AURUM_UNKNOWN_COMMAND", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
