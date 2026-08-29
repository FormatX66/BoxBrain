#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SCHEMA = "aurum-pc-runtime-update-seed"
GENERATION_SCHEMA = "aurum.seed-generation-receipt.v1"
LINEAGE_SCHEMA = "aurum.seed-lineage.v1"
LINEAGE_EVENT_SCHEMA = "aurum.seed-lineage-event.v1"
REPOSITORY = "https://github.com/FormatX66/BoxBrain.git"
BRANCH = "aurum/trunk-v0.01"
DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
DEFAULT_TARGET = Path(os.environ.get("AURUM_RUNTIME_ROOT", "/opt/aurum"))
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_MARKER = Path("/etc/aurum-installed.json")
DEFAULT_SYSTEM_ROOT = Path(os.environ.get("AURUM_SYSTEM_ROOT", "/"))
ALLOWLIST = (
    "aurum_arcade.py",
    "aurum_autonomy.py",
    "aurum_boot_screen.py",
    "aurum_bootstrap.py",
    "aurum_console.py",
    "aurum_control_plane.py",
    "aurum_credential_bootstrap.py",
    "aurum_desktop.py",
    "aurum_desktop_runtime.py",
    "aurum_display_runtime.py",
    "aurum_driver_synthesis.py",
    "aurum_echo_native.py",
    "aurum_gpt_trait.py",
    "aurum_gpt_executor.py",
    "aurum_gui_runtime.py",
    "aurum_hardware.py",
    "aurum_hopper_gui.py",
    "aurum_projection_runtime.py",
    "aurum_web_surface.py",
    "aurum_input.py",
    "aurum_installer.py",
    "aurum_network.py",
    "aurum_runtime_update.py",
    "aurum_sync_recovery.py",
    "aurum_self_debug.py",
    "aurum_time.py",
    "aurum_traits.py",
    "aurum_wifi_diag.py",
    "aurum_wifi_recovery.py",
    "aurum_workspace.py",
)
SYSTEM_ASSETS = (
    ("etc/X11/xorg.conf.d/40-aurum-libinput.conf", 0o644),
    ("etc/systemd/system/aurum-input-bootstrap.service", 0o644),
    ("etc/systemd/system/aurum-pc-console.service", 0o644),
    ("usr/lib/systemd/system-sleep/aurum-input-wake", 0o755),
)
FORWARD_ONLY_POLICY = {
    "published_history": "forward-only",
    "generation_rollback": False,
    "branch_rewind": False,
    "recoverable_failure": "heal-current-seed",
    "unrecoverable_candidate": "cull-and-regrow-forward",
    "preserve_culled_evidence": True,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _atomic_text(path: Path, text: str, mode: int = 0o644) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def _append_json_line(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class RuntimeUpdateError(RuntimeError):
    pass


class RuntimeUpdater:
    def __init__(
        self,
        *,
        workspace: Path = DEFAULT_WORKSPACE,
        target: Path = DEFAULT_TARGET,
        state_dir: Path = DEFAULT_STATE,
        installed_marker: Path = DEFAULT_MARKER,
        system_root: Path = DEFAULT_SYSTEM_ROOT,
    ) -> None:
        self.workspace = workspace
        self.source = workspace / "Projects" / "AurumPC"
        self.target = target
        self.state_dir = state_dir
        self.installed_marker = installed_marker
        self.system_root = system_root
        self.asset_source = self.source / "runtime-assets"

    def _git(self, *arguments: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.workspace,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )

    def _lineage_state(self) -> dict[str, Any]:
        state = _json_file(self.state_dir / "seed-lineage.json")
        if state.get("schema") == LINEAGE_SCHEMA:
            return state
        return {
            "schema": LINEAGE_SCHEMA,
            "policy": FORWARD_ONLY_POLICY,
            "status": "uninitialized",
            "observed_head": None,
            "current_seed": None,
            "last_culled": None,
            "culled_count": 0,
            "next_action": "observe-first-authorized-generation",
        }

    @staticmethod
    def _receipt_source(receipt: dict[str, Any]) -> dict[str, Any] | None:
        source = receipt.get("source") if isinstance(receipt.get("source"), dict) else None
        generation = receipt.get("generation") if isinstance(receipt.get("generation"), dict) else {}
        if source and generation.get("become_next_seed") is True:
            return dict(source)
        return None

    def _generation_transition(
        self,
        source_identity: dict[str, Any],
        previous_receipt: dict[str, Any],
    ) -> dict[str, Any]:
        head = str(source_identity.get("head") or "")
        tree = str(source_identity.get("tree") or "")
        lineage = self._lineage_state()
        last_culled = lineage.get("last_culled") if isinstance(lineage.get("last_culled"), dict) else {}
        if not re.fullmatch(r"[0-9a-f]{40}", head) or not re.fullmatch(r"[0-9a-f]{40}", tree):
            return {
                "status": "refused",
                "reason": "invalid-generation-identity",
                "policy": FORWARD_ONLY_POLICY,
                "head": head or None,
                "tree": tree or None,
            }
        if last_culled.get("head") == head:
            return {
                "status": "refused",
                "reason": "culled-generation-awaiting-forward-successor",
                "relation": "same-culled-head",
                "previous_head": head,
                "head": head,
                "tree": tree,
                "policy": FORWARD_ONLY_POLICY,
            }
        previous_source = previous_receipt.get("source") if isinstance(previous_receipt.get("source"), dict) else {}
        previous_head = str(lineage.get("observed_head") or previous_source.get("head") or "")
        if not previous_head:
            return {
                "status": "passed",
                "relation": "first-observed-forward-seed",
                "previous_head": None,
                "head": head,
                "tree": tree,
                "policy": FORWARD_ONLY_POLICY,
            }
        if previous_head == head:
            return {
                "status": "passed",
                "relation": "same-head-heal",
                "previous_head": previous_head,
                "head": head,
                "tree": tree,
                "policy": FORWARD_ONLY_POLICY,
            }
        ancestry = self._git("merge-base", "--is-ancestor", previous_head, head)
        if ancestry.returncode != 0:
            return {
                "status": "refused",
                "reason": "non-forward-generation",
                "relation": "diverged-or-rewound",
                "previous_head": previous_head,
                "head": head,
                "tree": tree,
                "policy": FORWARD_ONLY_POLICY,
            }
        return {
            "status": "passed",
            "relation": "forward-successor",
            "previous_head": previous_head,
            "head": head,
            "tree": tree,
            "policy": FORWARD_ONLY_POLICY,
        }

    def _record_lineage(
        self,
        *,
        status: str,
        source_identity: dict[str, Any],
        transition: dict[str, Any],
        previous_receipt: dict[str, Any],
        reason: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        head = str(source_identity.get("head") or "")
        lineage = self._lineage_state()
        current_seed = lineage.get("current_seed") if isinstance(lineage.get("current_seed"), dict) else None
        current_seed = current_seed or self._receipt_source(previous_receipt)
        culled_count = int(lineage.get("culled_count") or 0)
        if status in {"healed-and-proven", "regrown-and-promoted"}:
            current_seed = dict(source_identity)
            last_culled = lineage.get("last_culled")
            next_action = "continue-growing-forward"
            projection_status = "healthy-forward-seed"
        elif status == "culled-awaiting-forward-regrow":
            culled_count += 1
            last_culled = {
                "head": head,
                "tree": source_identity.get("tree"),
                "reason": reason,
                "culled_at": now,
                "evidence": evidence or {},
            }
            next_action = "publish-forward-successor-from-verified-lkg-genetics"
            projection_status = status
        else:
            last_culled = lineage.get("last_culled")
            next_action = "heal-current-seed-and-reprove"
            projection_status = status
        event = {
            "schema": LINEAGE_EVENT_SCHEMA,
            "event_id": f"seed-{time.time_ns()}-{os.getpid()}-{head[:12] or 'unknown'}",
            "at": now,
            "status": status,
            "reason": reason,
            "source": source_identity,
            "transition": transition,
            "current_seed": current_seed,
            "evidence": evidence or {},
            "policy": FORWARD_ONLY_POLICY,
            "branch_moved_backward": False,
            "generation_erased": False,
        }
        _append_json_line(self.state_dir / "seed-lineage-events.jsonl", event)
        projection = {
            "schema": LINEAGE_SCHEMA,
            "policy": FORWARD_ONLY_POLICY,
            "status": projection_status,
            "observed_head": head,
            "current_seed": current_seed,
            "last_culled": last_culled,
            "culled_count": culled_count,
            "last_event": event,
            "next_action": next_action,
            "updated_at": now,
        }
        _atomic_json(self.state_dir / "seed-lineage.json", projection)
        return projection

    def _refused_transition_receipt(
        self,
        source_identity: dict[str, Any],
        transition: dict[str, Any],
    ) -> dict[str, Any]:
        receipt = {
            "schema": SCHEMA,
            "status": "refused",
            "reason": transition.get("reason"),
            "source": source_identity,
            "lineage": self._lineage_state(),
            "transition": transition,
            "branch_moved_backward": False,
            "next_action": "wait-for-forward-successor",
        }
        _atomic_json(self.state_dir / "seed-lifecycle-last-refusal.json", receipt)
        return receipt

    def _source_identity(self) -> dict[str, Any]:
        if not (self.workspace / ".git").is_dir():
            return {"verified": False, "reason": "git-workspace-unavailable"}
        origin = self._git("remote", "get-url", "origin")
        branch = self._git("branch", "--show-current")
        head = self._git("rev-parse", "HEAD")
        tree = self._git("rev-parse", "HEAD^{tree}")
        dirty = self._git("status", "--porcelain=v1")
        origin_value = origin.stdout.strip()
        branch_value = branch.stdout.strip()
        head_value = head.stdout.strip()
        tree_value = tree.stdout.strip()
        exact_origin = bool(
            origin.returncode == 0
            and origin_value.rstrip("/").removesuffix(".git") == REPOSITORY.removesuffix(".git")
        )
        exact_branch = branch.returncode == 0 and branch_value == BRANCH
        clean = dirty.returncode == 0 and not dirty.stdout.strip()
        verified = bool(
            exact_origin
            and exact_branch
            and clean
            and head.returncode == 0
            and re.fullmatch(r"[0-9a-f]{40}", head_value)
            and tree.returncode == 0
            and re.fullmatch(r"[0-9a-f]{40}", tree_value)
        )
        return {
            "verified": verified,
            "repository": origin_value,
            "branch": branch_value,
            "head": head_value or None,
            "tree": tree_value or None,
            "exact_origin": exact_origin,
            "exact_branch": exact_branch,
            "clean": clean,
            "reason": "verified-authorized-source" if verified else "source-verification-failed",
        }

    def _identity_plan(self) -> dict[str, Any]:
        policy = _json_file(self.source / "pc01_autonomy_policy.json")
        receipt = _json_file(self.installed_marker)
        match = policy.get("machine_match") if isinstance(policy.get("machine_match"), dict) else {}
        target = receipt.get("target") if isinstance(receipt.get("target"), dict) else {}
        expected_serial = str(match.get("installed_target_serial") or "")
        expected_size = int(match.get("installed_target_size_bytes") or 0)
        authorized = bool(
            expected_serial
            and expected_size > 0
            and str(target.get("serial") or "") == expected_serial
            and int(target.get("size_bytes") or 0) == expected_size
        )
        hostname = str(policy.get("hostname") or "").strip().lower()
        display = str(policy.get("machine_display_name") or "").strip()
        if hostname and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", hostname) is None:
            raise RuntimeUpdateError("configured Aurum hostname is invalid")
        if len(display) > 64:
            raise RuntimeUpdateError("configured Aurum display name is too long")
        current_hostname = ""
        try:
            current_hostname = Path("/etc/hostname").read_text(encoding="utf-8").strip()
        except OSError:
            pass
        return {
            "authorized": authorized,
            "hostname": hostname,
            "display_name": display,
            "current_hostname": current_hostname,
            "change_needed": bool(authorized and hostname and current_hostname != hostname),
            "machine_match": {"serial": expected_serial, "size_bytes": expected_size},
        }

    def _apply_identity(self) -> dict[str, Any]:
        plan = self._identity_plan()
        if not plan["authorized"] or not plan["hostname"]:
            return {**plan, "status": "skipped"}
        if os.geteuid() != 0:
            raise RuntimeUpdateError("machine identity update requires root")
        old = plan["current_hostname"]
        identity_dir = self.state_dir / "identity"
        identity_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        backup = identity_dir / "previous-hostname.txt"
        if old and not backup.exists():
            _atomic_text(backup, old + "\n", 0o600)
        if plan["change_needed"]:
            _atomic_text(Path("/etc/hostname"), str(plan["hostname"]) + "\n", 0o644)
            hostnamectl = shutil.which("hostnamectl")
            runtime_command: dict[str, Any] = {"attempted": False}
            if hostnamectl:
                result = subprocess.run(
                    [hostnamectl, "set-hostname", str(plan["hostname"])],
                    check=False,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=20,
                )
                runtime_command = {
                    "attempted": True,
                    "tool": "hostnamectl",
                    "returncode": result.returncode,
                    "detail": result.stdout.strip()[-500:],
                }
        else:
            runtime_command = {"attempted": False, "reason": "already-named"}
        receipt = {
            "schema": "aurum-machine-identity-v1",
            "status": "named",
            "display_name": plan["display_name"],
            "hostname": plan["hostname"],
            "previous_hostname": old,
            "runtime_command": runtime_command,
            "machine_match": plan["machine_match"],
            "updated_at": time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime()),
        }
        _atomic_json(self.state_dir / "machine-identity.json", receipt)
        return receipt

    def _launch_physical_echo(self) -> dict[str, Any]:
        policy_path = self.source / "pc01_autonomy_policy.json"
        policy = _json_file(policy_path)
        identity = self._identity_plan()
        if not identity.get("authorized"):
            return {"status": "skipped", "reason": "machine-not-authorized"}
        if not bool(policy.get("auto_local_echo_display")):
            return {"status": "skipped", "reason": "physical-echo-disabled"}
        display = self.target / "aurum_display_runtime.py"
        game = self.target / "aurum_echo_native.py"
        if not display.is_file() or not game.is_file():
            return {"status": "skipped", "reason": "display-runtime-not-installed"}
        self.state_dir.mkdir(parents=True, exist_ok=True)
        log = (self.state_dir / "hopper-display-bootstrap.log").open("ab", buffering=0)
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(display),
                    "start",
                    "--policy",
                    str(policy_path),
                    "--receipt",
                    str(self.installed_marker),
                    "--state-dir",
                    str(self.state_dir),
                    "--game",
                    str(game),
                ],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                close_fds=True,
                start_new_session=True,
            )
        finally:
            log.close()
        return {
            "status": "launched",
            "pid": process.pid,
            "machine": "Hopper",
            "game": "Echo Rally",
            "physical_display": True,
        }

    def _refresh_input(self) -> dict[str, Any]:
        helper = self.target / "aurum_input.py"
        if not helper.is_file():
            return {"status": "skipped", "reason": "input-helper-not-installed"}
        result = subprocess.run(
            [
                sys.executable,
                str(helper),
                "--apply-wake-policy",
                "--write-state",
                "/run/aurum-input-status.json",
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = {"status": "failed", "detail": result.stdout[-1200:]}
        if not isinstance(payload, dict):
            payload = {"status": "failed", "detail": "input helper returned non-object"}
        payload["returncode"] = result.returncode
        return payload

    def _activate_system_integration(
        self, changed: list[str], system_changed: list[str]
    ) -> dict[str, Any]:
        if self.system_root.resolve() != Path("/"):
            return {"status": "skipped", "reason": "simulated-system-root"}
        systemctl = shutil.which("systemctl")
        if not systemctl:
            return {"status": "skipped", "reason": "systemctl-unavailable"}
        commands: list[dict[str, Any]] = []

        def run(*arguments: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
            result = subprocess.run(
                [systemctl, *arguments],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
            commands.append(
                {
                    "arguments": list(arguments),
                    "returncode": result.returncode,
                    "detail": result.stdout.strip()[-800:],
                }
            )
            return result

        if system_changed:
            run("daemon-reload")
        enable = run("enable", "aurum-input-bootstrap.service", "aurum-pc-console.service")
        active = run("is-active", "--quiet", "aurum-input-bootstrap.service")
        input_changed = bool(
            {"aurum_input.py", "aurum_runtime_update.py", "aurum_self_debug.py"}.intersection(changed)
        ) or any(
            name.endswith("aurum-input-bootstrap.service") or name.endswith("aurum-input-wake")
            for name in system_changed
        )
        restart = run("restart", "aurum-input-bootstrap.service") if input_changed or active.returncode != 0 else None
        failed = enable.returncode != 0 or any(
            item["returncode"] != 0 and item["arguments"] == ["daemon-reload"] for item in commands
        )
        if restart is not None and restart.returncode != 0:
            failed = True
        return {
            "status": "failed" if failed else "ready",
            "commands": commands,
            "console_restart_deferred": True,
            "boot_screen_visible_on_next_boot": True,
        }

    def _restart_gui(
        self, changed: list[str], system_changed: list[str], *, ensure_running: bool = False
    ) -> dict[str, Any]:
        policy = _json_file(self.source / "pc01_autonomy_policy.json")
        if policy.get("auto_gui_start") is not True:
            return {"status": "skipped", "reason": "automatic-gui-disabled"}
        gui_files = {
            "aurum_desktop.py",
            "aurum_desktop_runtime.py",
            "aurum_gui_runtime.py",
            "aurum_gpt_executor.py",
            "aurum_gpt_trait.py",
            "aurum_hopper_gui.py",
            "aurum_input.py",
            "aurum_projection_runtime.py",
            "aurum_web_surface.py",
        }
        libinput_changed = "etc/X11/xorg.conf.d/40-aurum-libinput.conf" in system_changed
        if not ensure_running and not gui_files.intersection(changed) and not libinput_changed:
            return {"status": "skipped", "reason": "gui-runtime-unchanged"}
        runtime = self.target / "aurum_gui_runtime.py"
        if not runtime.is_file():
            return {"status": "skipped", "reason": "gui-runtime-not-installed"}
        stop = None
        if not ensure_running:
            stop = subprocess.run(
                [sys.executable, str(runtime), "stop"],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=15,
            )
        start = subprocess.run(
            [sys.executable, str(runtime), "start"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=390,
        )
        try:
            payload = json.loads(start.stdout.strip().splitlines()[-1]) if start.stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {"status": "failed", "detail": start.stdout[-1600:]}
        if not isinstance(payload, dict):
            payload = {"status": "failed", "detail": "GUI runtime returned non-object"}
        payload["stop_returncode"] = stop.returncode if stop is not None else None
        payload["start_returncode"] = start.returncode
        payload["ensure_running"] = ensure_running
        return payload

    def plan(self) -> dict[str, Any]:
        if not self.installed_marker.is_file():
            return {"schema": SCHEMA, "available": False, "reason": "not-installed-runtime", "files": []}
        if not (self.workspace / ".git").is_dir() or not self.source.is_dir():
            return {"schema": SCHEMA, "available": False, "reason": "git-workspace-unavailable", "files": []}
        files: list[dict[str, Any]] = []
        for name in ALLOWLIST:
            source = self.source / name
            target = self.target / name
            if not source.is_file():
                raise RuntimeUpdateError(f"allowlisted runtime source is missing: {name}")
            source_sha = _sha256(source)
            target_sha = _sha256(target) if target.is_file() else None
            files.append(
                {
                    "name": name,
                    "source_sha256": source_sha,
                    "target_sha256": target_sha,
                    "changed": source_sha != target_sha,
                }
            )
        system_files: list[dict[str, Any]] = []
        for relative, mode in SYSTEM_ASSETS:
            source = self.asset_source / relative
            target = self.system_root / relative
            if not source.is_file():
                raise RuntimeUpdateError(f"allowlisted system asset is missing: {relative}")
            source_sha = _sha256(source)
            target_sha = _sha256(target) if target.is_file() else None
            target_mode = (target.stat().st_mode & 0o777) if target.is_file() else None
            system_files.append(
                {
                    "name": relative,
                    "source_sha256": source_sha,
                    "target_sha256": target_sha,
                    "mode": mode,
                    "target_mode": target_mode,
                    "changed": source_sha != target_sha or target_mode != mode,
                }
            )
        source_identity = self._source_identity()
        return {
            "schema": SCHEMA,
            "available": True,
            "reason": "ready",
            "workspace": str(self.workspace),
            "target": str(self.target),
            "files": files,
            "changed": [item["name"] for item in files if item["changed"]],
            "system_files": system_files,
            "system_changed": [item["name"] for item in system_files if item["changed"]],
            "identity": self._identity_plan(),
            "source": source_identity,
        }

    def _validate_sources(self, source_identity: dict[str, Any]) -> dict[str, Any]:
        if not source_identity.get("verified"):
            raise RuntimeUpdateError("generation source is not the clean authorized Aurum trunk")
        with tempfile.TemporaryDirectory(prefix="aurum-runtime-compile-") as temporary:
            output = Path(temporary)
            for name in ALLOWLIST:
                py_compile.compile(
                    str(self.source / name),
                    cfile=str(output / f"{name}.pyc"),
                    doraise=True,
                )
        for relative, _mode in SYSTEM_ASSETS:
            source = self.asset_source / relative
            if not source.is_file() or source.stat().st_size == 0:
                raise RuntimeUpdateError(f"allowlisted system asset is empty or missing: {relative}")
        return {
            "status": "passed",
            "source_verified": True,
            "compiled_runtime_files": len(ALLOWLIST),
            "verified_system_assets": len(SYSTEM_ASSETS),
        }

    def _stage_generation(
        self,
        *,
        source_identity: dict[str, Any],
        changed: list[str],
        system_changed: list[str],
    ) -> tuple[Path, dict[str, Any]]:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        head = str(source_identity.get("head") or "unknown")
        stage = self.state_dir / "generation-stage" / f"{stamp}-{head[:12]}-{os.getpid()}"
        runtime_stage = stage / "runtime"
        system_stage = stage / "system"
        runtime_stage.mkdir(parents=True, mode=0o700, exist_ok=False)
        staged_runtime: list[dict[str, Any]] = []
        staged_system: list[dict[str, Any]] = []
        for name in changed:
            source = self.source / name
            target = runtime_stage / name
            shutil.copy2(source, target)
            os.chmod(target, 0o700)
            if _sha256(target) != _sha256(source):
                raise RuntimeUpdateError(f"staged runtime hash verification failed for {name}")
            staged_runtime.append({"name": name, "sha256": _sha256(target)})
        for relative, mode in SYSTEM_ASSETS:
            if relative not in system_changed:
                continue
            source = self.asset_source / relative
            target = system_stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            os.chmod(target, mode)
            if _sha256(target) != _sha256(source):
                raise RuntimeUpdateError(f"staged system hash verification failed for {relative}")
            staged_system.append({"name": relative, "sha256": _sha256(target), "mode": mode})
        with tempfile.TemporaryDirectory(prefix="aurum-stage-compile-") as temporary:
            output = Path(temporary)
            for item in staged_runtime:
                name = str(item["name"])
                py_compile.compile(str(runtime_stage / name), cfile=str(output / f"{name}.pyc"), doraise=True)
        manifest = {
            "schema": "aurum.seed-generation-stage.v1",
            "status": "verified",
            "source": source_identity,
            "runtime": staged_runtime,
            "system": staged_system,
            "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _atomic_json(stage / "manifest.json", manifest)
        return stage, manifest

    def _heal_from_displaced_state(
        self,
        *,
        runtime_files: list[str],
        system_files: list[str],
        displaced_state: Path,
    ) -> dict[str, Any]:
        restored_runtime: list[str] = []
        restored_system: list[str] = []
        removed_new_runtime: list[str] = []
        removed_new_system: list[str] = []
        errors: list[str] = []
        for relative in reversed(system_files):
            saved = displaced_state / "system" / relative
            target = self.system_root / relative
            try:
                if saved.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(saved, target)
                    if _sha256(target) != _sha256(saved):
                        raise RuntimeUpdateError(f"healed system hash mismatch: {relative}")
                    restored_system.append(relative)
                else:
                    target.unlink(missing_ok=True)
                    removed_new_system.append(relative)
            except Exception as exc:
                errors.append(f"system:{relative}:{type(exc).__name__}:{exc}")
        for name in reversed(runtime_files):
            saved = displaced_state / name
            target = self.target / name
            try:
                if saved.is_file():
                    shutil.copy2(saved, target)
                    if _sha256(target) != _sha256(saved):
                        raise RuntimeUpdateError(f"healed runtime hash mismatch: {name}")
                    restored_runtime.append(name)
                else:
                    target.unlink(missing_ok=True)
                    removed_new_runtime.append(name)
            except Exception as exc:
                errors.append(f"runtime:{name}:{type(exc).__name__}:{exc}")
        integration = self._activate_system_integration(runtime_files, system_files)
        gui = self._restart_gui(runtime_files, system_files, ensure_running=True)
        healed = bool(not errors and integration.get("status") != "failed" and gui.get("status") != "failed")
        return {
            "schema": "aurum.seed-heal-receipt.v1",
            "status": "passed" if healed else "failed",
            "displaced_state": str(displaced_state),
            "restored_runtime": sorted(restored_runtime),
            "restored_system": sorted(restored_system),
            "removed_new_runtime": sorted(removed_new_runtime),
            "removed_new_system": sorted(removed_new_system),
            "errors": errors,
            "system_activation": integration,
            "gui_activation": gui,
            "branch_moved_backward": False,
            "git_ref_changed": False,
        }

    def _installed_hash_proof(self, plan: dict[str, Any]) -> dict[str, Any]:
        mismatches: list[str] = []
        for item in plan.get("files") or []:
            target = self.target / str(item["name"])
            if not target.is_file() or _sha256(target) != str(item["source_sha256"]):
                mismatches.append(str(item["name"]))
        for item in plan.get("system_files") or []:
            target = self.system_root / str(item["name"])
            if (
                not target.is_file()
                or _sha256(target) != str(item["source_sha256"])
                or (target.stat().st_mode & 0o777) != int(item["mode"])
            ):
                mismatches.append(str(item["name"]))
        return {
            "status": "passed" if not mismatches else "failed",
            "verified_runtime_files": len(plan.get("files") or []) - len([x for x in mismatches if "/" not in x]),
            "verified_system_assets": len(plan.get("system_files") or []) - len([x for x in mismatches if "/" in x]),
            "mismatches": mismatches,
        }

    def _latest_verified_stage(self, source_identity: dict[str, Any]) -> dict[str, Any] | None:
        root = self.state_dir / "generation-stage"
        try:
            manifests = sorted(root.glob("*/manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        except OSError:
            return None
        expected_head = source_identity.get("head")
        for path in manifests:
            manifest = _json_file(path)
            source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
            if (
                manifest.get("schema") == "aurum.seed-generation-stage.v1"
                and manifest.get("status") == "verified"
                and source.get("head") == expected_head
            ):
                return {**manifest, "status": "verified-carried-forward", "path": str(path.parent)}
        return None

    def _gpt_proof(self) -> dict[str, Any]:
        executor_path = self.target / "aurum_gpt_executor.py"
        trait_path = self.target / "aurum_gpt_trait.py"
        if not executor_path.is_file() or not trait_path.is_file():
            return {"status": "failed", "reason": "installed-gpt-runtime-missing"}
        try:
            spec = importlib.util.spec_from_file_location(
                f"aurum_generation_gpt_executor_{os.getpid()}_{time.time_ns()}", executor_path
            )
            if spec is None or spec.loader is None:
                raise RuntimeUpdateError("installed GPT executor could not be loaded")
            executor = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = executor
            spec.loader.exec_module(executor)
            executor.DEFAULT_STATE = self.state_dir
            executor.DEFAULT_WORKSPACE = self.workspace
            executor.DEFAULT_RUNTIME = self.target
            catalog = executor.catalog()
            receipt = executor.execute_control("status", state_dir=self.state_dir)

            trait_spec = importlib.util.spec_from_file_location(
                f"aurum_generation_gpt_trait_{os.getpid()}_{time.time_ns()}", trait_path
            )
            if trait_spec is None or trait_spec.loader is None:
                raise RuntimeUpdateError("installed GPT trait could not be loaded")
            trait = importlib.util.module_from_spec(trait_spec)
            sys.modules[trait_spec.name] = trait
            trait_spec.loader.exec_module(trait)
            trait.DEFAULT_STATE = self.state_dir
            trait.DEFAULT_WORKSPACE = self.workspace
            trait.DEFAULT_RUNTIME = self.target
            trait_status = trait.status()
            model_probe = trait.model_probe() if trait_status.get("status") == "ready" else {
                "status": "unproven",
                "model_call_proven": False,
                "reason": trait_status.get("status"),
            }
        except Exception as exc:
            return {"status": "failed", "detail": f"{type(exc).__name__}:{exc}"}
        passed = bool(
            catalog.get("direct_shell_contract") is False
            and catalog.get("authority") == "aurum-policy-broker"
            and receipt.get("schema") == "aurum.gpt-control-receipt.gen1-direct-control"
            and (receipt.get("result") or {}).get("status") == "observed"
            and trait_status.get("function_tools") is True
            and trait_status.get("raw_shell") is False
        )
        return {
            "status": "passed" if passed else "failed",
            "bounded_executor_receipt": receipt,
            "function_tools": bool(trait_status.get("function_tools")),
            "raw_shell": bool(trait_status.get("raw_shell")),
            "model_status": trait_status.get("status"),
            "model_call_proven": bool(model_probe.get("model_call_proven")),
            "model_probe": model_probe,
        }

    @staticmethod
    def _physical_proof(gui: dict[str, Any]) -> dict[str, Any]:
        desktop = gui.get("desktop") if isinstance(gui.get("desktop"), dict) else {}
        renderer = desktop.get("renderer")
        running = bool(gui.get("physical_desktop") and desktop.get("status") == "running")
        return {
            "status": "passed" if running else "failed",
            "physical_desktop": running,
            "renderer": renderer,
            "html_primary": bool(running and renderer == "html5" and desktop.get("primary") is True),
            "pygame_fallback": bool(running and renderer == "pygame-fallback"),
            "reboot_required": bool(desktop.get("reboot_required")),
            "detail": desktop,
        }

    def _system_proof(self) -> dict[str, Any]:
        if self.system_root.resolve() != Path("/"):
            return {"status": "skipped", "reason": "simulated-system-root"}
        systemctl = shutil.which("systemctl")
        if not systemctl:
            return {"status": "failed", "reason": "systemctl-unavailable"}
        result = subprocess.run(
            [systemctl, "is-active", "--quiet", "aurum-input-bootstrap.service"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
        )
        return {
            "status": "passed" if result.returncode == 0 else "failed",
            "service": "aurum-input-bootstrap.service",
            "returncode": result.returncode,
        }

    def prove_current(self, gui: dict[str, Any]) -> dict[str, Any]:
        plan = self.plan()
        if not plan.get("available"):
            return plan
        previous = _json_file(self.state_dir / "runtime-update.json")
        source_identity = plan.get("source") if isinstance(plan.get("source"), dict) else {}
        transition = self._generation_transition(source_identity, previous)
        if transition.get("status") != "passed":
            return self._refused_transition_receipt(source_identity, transition)
        if plan.get("changed") or plan.get("system_changed"):
            return {"schema": SCHEMA, "status": "pending", "reason": "runtime-apply-required"}
        verification = self._validate_sources(source_identity)
        runtime_proof = self._installed_hash_proof(plan)
        physical_proof = self._physical_proof(gui)
        gpt_proof = self._gpt_proof()
        system_proof = self._system_proof()
        previous_generation = previous.get("generation") if isinstance(previous.get("generation"), dict) else {}
        previous_source = previous_generation.get("source") if isinstance(previous_generation.get("source"), dict) else {}
        stage = None
        if previous_source.get("head") == source_identity.get("head"):
            candidate = previous_generation.get("stage")
            stage = candidate if isinstance(candidate, dict) else None
        stage = stage or self._latest_verified_stage(source_identity) or {
            "status": "not-required",
            "reason": "installed-hashes-current",
        }
        become_next_seed = bool(
            runtime_proof.get("status") == "passed"
            and physical_proof.get("status") == "passed"
            and gpt_proof.get("status") == "passed"
            and system_proof.get("status") == "passed"
        )
        lineage_status = (
            "healed-and-proven"
            if transition.get("relation") == "same-head-heal" and become_next_seed
            else "regrown-and-promoted"
            if become_next_seed
            else "heal-required"
        )
        lineage = self._record_lineage(
            status=lineage_status,
            source_identity=source_identity,
            transition=transition,
            previous_receipt=previous,
            reason=None if become_next_seed else "current-runtime-proof-incomplete",
            evidence={
                "runtime": runtime_proof,
                "physical": physical_proof,
                "gpt": gpt_proof,
                "system": system_proof,
            },
        )
        lifecycle = {
            "schema": GENERATION_SCHEMA,
            "lineage_policy": FORWARD_ONLY_POLICY,
            "transition": transition,
            "disposition": lineage_status,
            "lineage": lineage,
            "source": source_identity,
            "discover_pull": "verified-by-autonomy-receipt",
            "verify": verification,
            "stage": stage,
            "apply": {
                "status": "passed",
                "changed": list(previous.get("changed") or []),
                "system_changed": list(previous.get("system_changed") or []),
                "displaced_state": previous.get("displaced_state") or previous.get("backup"),
                "backup": previous.get("backup"),
                "installed_hashes_current": True,
            },
            "prove": {
                "runtime": runtime_proof,
                "physical": physical_proof,
                "gpt": gpt_proof,
                "system": system_proof,
            },
            "become_next_seed": become_next_seed,
            "proved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        receipt = {
            "schema": SCHEMA,
            "status": "current" if become_next_seed else "applied-not-proven",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "workspace": str(self.workspace),
            "target": str(self.target),
            "changed": list(previous.get("changed") or []),
            "system_changed": list(previous.get("system_changed") or []),
            "displaced_state": previous.get("displaced_state") or previous.get("backup"),
            "backup": previous.get("backup"),
            "reboot_required": bool(physical_proof.get("reboot_required")),
            "source": source_identity,
            "generation": lifecycle,
            "lineage": lineage,
        }
        _atomic_json(self.state_dir / "runtime-update.json", receipt)
        _atomic_json(self.state_dir / "seed-generation.json", lifecycle)
        return receipt

    def apply(self) -> dict[str, Any]:
        plan = self.plan()
        if not plan.get("available"):
            return plan
        if os.geteuid() != 0:
            raise RuntimeUpdateError("installed runtime update requires the root-owned Aurum console")
        source_identity = plan.get("source") if isinstance(plan.get("source"), dict) else {}
        verification = self._validate_sources(source_identity)
        previous = _json_file(self.state_dir / "runtime-update.json")
        transition = self._generation_transition(source_identity, previous)
        if transition.get("status") != "passed":
            return self._refused_transition_receipt(source_identity, transition)
        identity = self._apply_identity()
        changed = list(plan.get("changed") or [])
        system_changed = list(plan.get("system_changed") or [])
        if not changed and not system_changed:
            activation = self._launch_physical_echo()
            input_activation = self._refresh_input()
            system_activation = self._activate_system_integration([], [])
            gui_activation = self._restart_gui([], [], ensure_running=True)
            installed_proof = self._installed_hash_proof(plan)
            gpt_proof = self._gpt_proof()
            physical_proof = self._physical_proof(gui_activation)
            carried_stage = self._latest_verified_stage(source_identity)
            become_next_seed = bool(
                installed_proof.get("status") == "passed"
                and gpt_proof.get("status") == "passed"
                and physical_proof.get("status") == "passed"
                and system_activation.get("status") == "ready"
            )
            lineage_status = (
                "healed-and-proven"
                if transition.get("relation") == "same-head-heal" and become_next_seed
                else "regrown-and-promoted"
                if become_next_seed
                else "heal-required"
            )
            lineage = self._record_lineage(
                status=lineage_status,
                source_identity=source_identity,
                transition=transition,
                previous_receipt=previous,
                reason=None if become_next_seed else "current-runtime-proof-incomplete",
                evidence={
                    "runtime": installed_proof,
                    "physical": physical_proof,
                    "gpt": gpt_proof,
                    "system": system_activation,
                },
            )
            lifecycle = {
                "schema": GENERATION_SCHEMA,
                "lineage_policy": FORWARD_ONLY_POLICY,
                "transition": transition,
                "disposition": lineage_status,
                "lineage": lineage,
                "source": source_identity,
                "discover_pull": "verified-by-autonomy-receipt",
                "verify": verification,
                "stage": carried_stage or {"status": "not-required", "reason": "installed-hashes-current"},
                "apply": {"status": "current", "changed": [], "system_changed": []},
                "prove": {
                    "runtime": installed_proof,
                    "physical": physical_proof,
                    "gpt": gpt_proof,
                },
                "become_next_seed": become_next_seed,
            }
            result = {
                **plan,
                "status": "current" if become_next_seed else "applied-not-proven",
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "reboot_required": bool(physical_proof.get("reboot_required")),
                "identity": identity,
                "physical_echo_activation": activation,
                "input_activation": input_activation,
                "system_activation": system_activation,
                "gui_activation": gui_activation,
                "generation": lifecycle,
                "lineage": lineage,
            }
            _atomic_json(self.state_dir / "runtime-update.json", result)
            _atomic_json(self.state_dir / "seed-generation.json", lifecycle)
            return result
        self.target.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        stage, stage_manifest = self._stage_generation(
            source_identity=source_identity,
            changed=changed,
            system_changed=system_changed,
        )
        displaced_state = self.state_dir / "displaced-state" / f"{stamp}-{os.getpid()}"
        displaced_state.mkdir(parents=True, mode=0o700, exist_ok=False)
        applied: list[str] = []
        applied_system: list[str] = []
        touched_runtime: list[str] = []
        touched_system: list[str] = []
        try:
            for name in changed:
                source = stage / "runtime" / name
                target = self.target / name
                if target.is_file():
                    shutil.copy2(target, displaced_state / name)
                touched_runtime.append(name)
                temporary = target.with_name(f".{name}.{os.getpid()}.next")
                shutil.copy2(source, temporary)
                os.chmod(temporary, 0o755)
                os.replace(temporary, target)
                if _sha256(target) != _sha256(source):
                    raise RuntimeUpdateError(f"runtime hash verification failed after replacing {name}")
                applied.append(name)
            for relative, mode in SYSTEM_ASSETS:
                if relative not in system_changed:
                    continue
                source = stage / "system" / relative
                target = self.system_root / relative
                saved = displaced_state / "system" / relative
                if target.is_file():
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, saved)
                touched_system.append(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(f".{target.name}.{os.getpid()}.next")
                shutil.copy2(source, temporary)
                os.chmod(temporary, mode)
                os.replace(temporary, target)
                if _sha256(target) != _sha256(source) or (target.stat().st_mode & 0o777) != mode:
                    raise RuntimeUpdateError(f"system asset verification failed after replacing {relative}")
                applied_system.append(relative)
        except Exception as exc:
            healing = self._heal_from_displaced_state(
                runtime_files=touched_runtime,
                system_files=touched_system,
                displaced_state=displaced_state,
            )
            lineage = self._record_lineage(
                status="culled-awaiting-forward-regrow",
                source_identity=source_identity,
                transition=transition,
                previous_receipt=previous,
                reason=f"apply-failed:{type(exc).__name__}:{exc}",
                evidence={
                    "stage": {**stage_manifest, "path": str(stage)},
                    "displaced_state": str(displaced_state),
                    "healing": healing,
                },
            )
            _atomic_json(
                self.state_dir / "culled-generation.json",
                {
                    "schema": "aurum.culled-generation.v1",
                    "status": "culled-awaiting-forward-regrow",
                    "source": source_identity,
                    "transition": transition,
                    "reason": f"apply-failed:{type(exc).__name__}:{exc}",
                    "healing": healing,
                    "lineage": lineage,
                    "branch_moved_backward": False,
                    "next_action": "publish-forward-successor-from-verified-lkg-genetics",
                },
            )
            raise
        installed_before_activation = self._installed_hash_proof(plan)
        interim_lifecycle = {
            "schema": GENERATION_SCHEMA,
            "lineage_policy": FORWARD_ONLY_POLICY,
            "transition": transition,
            "disposition": "candidate-awaiting-proof",
            "lineage": self._lineage_state(),
            "source": source_identity,
            "discover_pull": "verified-by-autonomy-receipt",
            "verify": verification,
            "stage": {**stage_manifest, "path": str(stage)},
            "apply": {
                "status": "passed" if installed_before_activation.get("status") == "passed" else "failed",
                "changed": applied,
                "system_changed": applied_system,
                "displaced_state": str(displaced_state),
                "backup": str(displaced_state),
            },
            "prove": {
                "runtime": installed_before_activation,
                "physical": {"status": "pending"},
                "gpt": {"status": "pending"},
                "system": {"status": "pending"},
            },
            "become_next_seed": False,
        }
        _atomic_json(self.state_dir / "seed-generation.json", interim_lifecycle)
        _atomic_json(self.state_dir / "runtime-update.json", {
            "schema": SCHEMA,
            "status": "applied-awaiting-proof",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "workspace": str(self.workspace),
            "target": str(self.target),
            "changed": applied,
            "system_changed": applied_system,
            "displaced_state": str(displaced_state),
            "backup": str(displaced_state),
            "reboot_required": False,
            "source": source_identity,
            "generation": interim_lifecycle,
            "lineage": self._lineage_state(),
        })
        system_activation = self._activate_system_integration(applied, applied_system)
        activation = self._launch_physical_echo()
        input_activation = self._refresh_input()
        gui_activation = self._restart_gui(applied, applied_system)
        installed_proof = self._installed_hash_proof(plan)
        gpt_proof = self._gpt_proof()
        physical_proof = self._physical_proof(gui_activation)
        become_next_seed = bool(
            installed_proof.get("status") == "passed"
            and gpt_proof.get("status") == "passed"
            and physical_proof.get("status") == "passed"
            and system_activation.get("status") == "ready"
        )
        healing: dict[str, Any] | None = None
        if become_next_seed:
            lineage_status = "regrown-and-promoted"
            lineage_reason = None
            lineage_evidence = {
                "stage": {**stage_manifest, "path": str(stage)},
                "runtime": installed_proof,
                "physical": physical_proof,
                "gpt": gpt_proof,
                "system": system_activation,
                "displaced_state": str(displaced_state),
            }
        else:
            failed_proofs = [
                name
                for name, proof in (
                    ("runtime", installed_proof),
                    ("physical", physical_proof),
                    ("gpt", gpt_proof),
                    ("system", system_activation),
                )
                if proof.get("status") not in {"passed", "ready"}
            ]
            healing = self._heal_from_displaced_state(
                runtime_files=applied,
                system_files=applied_system,
                displaced_state=displaced_state,
            )
            lineage_status = "culled-awaiting-forward-regrow"
            lineage_reason = "proof-failed:" + ",".join(failed_proofs or ["unknown"])
            lineage_evidence = {
                "stage": {**stage_manifest, "path": str(stage)},
                "candidate_proof": {
                    "runtime": installed_proof,
                    "physical": physical_proof,
                    "gpt": gpt_proof,
                    "system": system_activation,
                },
                "displaced_state": str(displaced_state),
                "healing": healing,
            }
        lineage = self._record_lineage(
            status=lineage_status,
            source_identity=source_identity,
            transition=transition,
            previous_receipt=previous,
            reason=lineage_reason,
            evidence=lineage_evidence,
        )
        lifecycle = {
            "schema": GENERATION_SCHEMA,
            "lineage_policy": FORWARD_ONLY_POLICY,
            "transition": transition,
            "disposition": lineage_status,
            "lineage": lineage,
            "source": source_identity,
            "discover_pull": "verified-by-autonomy-receipt",
            "verify": verification,
            "stage": {**stage_manifest, "path": str(stage)},
            "apply": {
                "status": "passed" if installed_proof.get("status") == "passed" else "failed",
                "changed": applied,
                "system_changed": applied_system,
                "displaced_state": str(displaced_state),
                "backup": str(displaced_state),
                "healing": healing,
            },
            "prove": {
                "runtime": installed_proof,
                "physical": physical_proof,
                "gpt": gpt_proof,
            },
            "become_next_seed": become_next_seed,
        }
        receipt = {
            "schema": SCHEMA,
            "status": "updated" if become_next_seed else "culled-awaiting-forward-regrow",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "workspace": str(self.workspace),
            "target": str(self.target),
            "changed": applied,
            "system_changed": applied_system,
            "displaced_state": str(displaced_state),
            "backup": str(displaced_state),
            "reboot_required": bool(physical_proof.get("reboot_required")),
            "identity": identity,
            "physical_echo_activation": activation,
            "input_activation": input_activation,
            "system_activation": system_activation,
            "gui_activation": gui_activation,
            "source": source_identity,
            "generation": lifecycle,
            "lineage": lineage,
            "healing": healing,
            "branch_moved_backward": False,
        }
        if not become_next_seed:
            receipt["next_action"] = "publish-forward-successor-from-verified-lkg-genetics"
            _atomic_json(
                self.state_dir / "culled-generation.json",
                {
                    "schema": "aurum.culled-generation.v1",
                    "status": "culled-awaiting-forward-regrow",
                    "source": source_identity,
                    "transition": transition,
                    "reason": lineage_reason,
                    "candidate_proof": lineage_evidence.get("candidate_proof"),
                    "healing": healing,
                    "lineage": lineage,
                    "branch_moved_backward": False,
                    "next_action": "publish-forward-successor-from-verified-lkg-genetics",
                },
            )
        _atomic_json(self.state_dir / "runtime-update.json", receipt)
        _atomic_json(self.state_dir / "seed-generation.json", lifecycle)
        return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guarded Aurum installed-runtime updater")
    parser.add_argument("command", choices=("plan", "apply"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    updater = RuntimeUpdater()
    try:
        result = updater.plan() if args.command == "plan" else updater.apply()
    except (RuntimeUpdateError, py_compile.PyCompileError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "failed", "detail": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
