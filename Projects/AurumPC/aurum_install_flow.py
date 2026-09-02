#!/usr/bin/env python3
"""One-confirmation installation flow for the Aurum live desktop.

The browser and Pygame surfaces never receive a device path or the installer's
device-bound ERASE code.  They can only confirm the single target selected by
the guarded installer.  The installer then performs its own fresh discovery
before writing anything.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
from typing import Any, Callable, Mapping

from aurum_installer import AurumInstaller, InstallError


FLOW_SCHEMA = "aurum.install-flow.v1"
DEFAULT_STATUS_PATH = Path("/run/aurum/install-status.json")
PHASE_PROGRESS = {
    "discovery": 0,
    "preflight": 5,
    "partition": 15,
    "format": 25,
    "copy": 45,
    "bootloader": 80,
    "verify": 92,
    "complete": 100,
    "failed": 0,
}
PowerRunner = Callable[..., subprocess.CompletedProcess[str]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: object, maximum: int = 300) -> str:
    return " ".join(str(value or "").split())[:maximum]


def _public_target(target: Mapping[str, Any]) -> dict[str, Any]:
    partitions = target.get("existing_partitions")
    partition_count = len(partitions) if isinstance(partitions, (list, tuple)) else 0
    return {
        "model": _clean(target.get("model"), 128) or "Internal drive",
        "size_gib": target.get("size_gib"),
        "existing_partition_count": partition_count,
        "contains_existing_data": partition_count > 0,
    }


def _default_power_runner(arguments: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, **kwargs)


class InstallCoordinator:
    """Own the asynchronous, exact-one-target install lifecycle."""

    def __init__(
        self,
        *,
        installer: AurumInstaller | None = None,
        status_path: Path = DEFAULT_STATUS_PATH,
        power_runner: PowerRunner = _default_power_runner,
    ) -> None:
        self.installer = installer or AurumInstaller()
        self.status_path = status_path
        self.power_runner = power_runner
        self._lock = threading.RLock()
        self._worker: threading.Thread | None = None
        self._state: dict[str, Any] = {
            "schema": FLOW_SCHEMA,
            "status": "idle",
            "phase": "discovery",
            "progress_percent": 0,
            "updated_at": _now(),
        }
        self._restore_status()

    def _restore_status(self) -> None:
        try:
            value = json.loads(self.status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(value, dict) or value.get("schema") != FLOW_SCHEMA:
            return
        status = value.get("status")
        if status in {"complete", "failed", "powering-off"}:
            self._state = value
        elif status == "running":
            self._state = {
                "schema": FLOW_SCHEMA,
                "status": "failed",
                "phase": "failed",
                "progress_percent": 0,
                "target": value.get("target") if isinstance(value.get("target"), dict) else {},
                "reason": "installer-interface-restarted",
                "message": "The installer screen restarted. Retry is safe; the disk lock prevents overlap with any surviving installer.",
                "updated_at": _now(),
            }
            self._write_status()

    def _write_status(self) -> None:
        try:
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.status_path.with_name(
                f".{self.status_path.name}.{os.getpid()}.tmp"
            )
            temporary.write_text(
                json.dumps(self._state, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.status_path)
        except OSError:
            # A read-only or early live runtime must not make safe discovery fail.
            pass

    def _snapshot(self) -> dict[str, Any]:
        return deepcopy(self._state)

    def _plan(self) -> tuple[dict[str, Any], list[Mapping[str, Any]]]:
        plan = self.installer.plan()
        if not isinstance(plan, dict):
            raise InstallError("installer plan was not an object")
        targets = plan.get("targets")
        if not isinstance(targets, list):
            targets = []
        return plan, [target for target in targets if isinstance(target, Mapping)]

    def status(self) -> dict[str, Any]:
        with self._lock:
            if self._state.get("status") in {"running", "complete", "failed", "powering-off"}:
                return self._snapshot()
            try:
                plan, targets = self._plan()
                if not plan.get("available"):
                    state = {
                        "schema": FLOW_SCHEMA,
                        "status": "unavailable",
                        "phase": "discovery",
                        "progress_percent": 0,
                        "reason": _clean(plan.get("reason")) or "installer-unavailable",
                        "target_count": len(targets),
                        "updated_at": _now(),
                    }
                elif len(targets) != 1:
                    state = {
                        "schema": FLOW_SCHEMA,
                        "status": "blocked",
                        "phase": "discovery",
                        "progress_percent": 0,
                        "reason": "multiple-eligible-internal-disks-found",
                        "target_count": len(targets),
                        "updated_at": _now(),
                    }
                else:
                    state = {
                        "schema": FLOW_SCHEMA,
                        "status": "ready",
                        "phase": "discovery",
                        "progress_percent": 0,
                        "reason": "ready",
                        "target_count": 1,
                        "target": _public_target(targets[0]),
                        "warning": "The internal drive will be completely erased. The USB seed and other drives are never modified.",
                        "updated_at": _now(),
                    }
            except Exception as exc:
                state = {
                    "schema": FLOW_SCHEMA,
                    "status": "unavailable",
                    "phase": "discovery",
                    "progress_percent": 0,
                    "reason": f"{type(exc).__name__}:{_clean(exc)}",
                    "target_count": 0,
                    "updated_at": _now(),
                }
            self._state = state
            self._write_status()
            return self._snapshot()

    def start(self, *, confirmed: bool) -> dict[str, Any]:
        if confirmed is not True:
            raise InstallError("installation requires the visible erase confirmation")
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                raise InstallError("an Aurum installation is already running")
            if self._state.get("status") in {"complete", "powering-off"}:
                raise InstallError("Aurum is already installed; shut down and remove the USB seed")
            plan, targets = self._plan()
            if not plan.get("available") or len(targets) != 1:
                raise InstallError("installation requires exactly one eligible internal drive")
            confirmation_code = targets[0].get("confirmation_code")
            if not isinstance(confirmation_code, str):
                raise InstallError("the guarded installer did not produce a target confirmation")
            target = _public_target(targets[0])
            self._state = {
                "schema": FLOW_SCHEMA,
                "status": "running",
                "phase": "preflight",
                "progress_percent": PHASE_PROGRESS["preflight"],
                "target": target,
                "message": "Checking the internal drive again before installation.",
                "started_at": _now(),
                "updated_at": _now(),
            }
            self._write_status()
            self._worker = threading.Thread(
                target=self._run_install,
                args=(confirmation_code, target),
                name="aurum-guarded-install",
                daemon=False,
            )
            self._worker.start()
            return self._snapshot()

    def _run_install(self, confirmation_code: str, target: Mapping[str, Any]) -> None:
        def progress(event: Mapping[str, Any]) -> None:
            phase = str(event.get("phase") or "preflight")
            with self._lock:
                self._state.update(
                    {
                        "status": "running",
                        "phase": phase,
                        "progress_percent": PHASE_PROGRESS.get(phase, 5),
                        "updated_at": _now(),
                    }
                )
                self._write_status()

        try:
            result = self.installer.install(confirmation_code, progress=progress)
            if not isinstance(result, dict) or result.get("status") != "installed":
                raise InstallError("installer did not return a verified installed result")
            public_result = {
                key: result.get(key)
                for key in (
                    "status",
                    "model",
                    "size_gib",
                    "boot_mode",
                    "other_disks_modified",
                    "next_action",
                )
            }
            with self._lock:
                self._state = {
                    "schema": FLOW_SCHEMA,
                    "status": "complete",
                    "phase": "complete",
                    "progress_percent": 100,
                    "target": dict(target),
                    "result": public_result,
                    "message": "Installation verified. Shut down, remove the USB seed, then start Hopper.",
                    "completed_at": _now(),
                    "updated_at": _now(),
                }
                self._write_status()
        except Exception as exc:
            with self._lock:
                self._state = {
                    "schema": FLOW_SCHEMA,
                    "status": "failed",
                    "phase": "failed",
                    "progress_percent": 0,
                    "target": dict(target),
                    "reason": f"{type(exc).__name__}:{_clean(exc)}",
                    "message": "Installation stopped safely before verification completed. Nothing else will run automatically.",
                    "updated_at": _now(),
                }
                self._write_status()

    def poweroff(self) -> dict[str, Any]:
        with self._lock:
            if self._state.get("status") != "complete":
                raise InstallError("shutdown-to-finish is available only after a verified installation")
        tool = shutil.which("systemctl")
        if not tool:
            raise InstallError("safe system shutdown is unavailable")
        result = self.power_runner(
            [tool, "poweroff"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=8,
        )
        if result.returncode != 0:
            raise InstallError("safe system shutdown was refused")
        with self._lock:
            self._state.update(
                {
                    "status": "powering-off",
                    "message": "Hopper is shutting down. Remove the USB seed when power is off.",
                    "updated_at": _now(),
                }
            )
            self._write_status()
            return self._snapshot()


__all__ = ["FLOW_SCHEMA", "InstallCoordinator", "PHASE_PROGRESS"]
