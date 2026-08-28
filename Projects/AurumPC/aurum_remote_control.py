#!/usr/bin/env python3
"""Restricted remote sync and desktop transport for Hopper.

The only network-facing identity is a key-only OpenSSH account with a forced
command.  The desktop server itself binds to loopback and is reachable only
through that authenticated SSH tunnel.  No arbitrary shell or command string
is accepted anywhere in this module.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # Windows source tests; Hopper runtime is Linux.
    fcntl = None
try:
    import pwd
except ImportError:  # Windows source tests; Hopper runtime is Linux.
    pwd = None

SCHEMA = "aurum.remote-control.v1"
RECEIPT_SCHEMA = "aurum.remote-control-receipt.v1"
REMOTE_USER = "aurum-remote"
REMOTE_HOME = Path("/var/lib/aurum/remote")
AUTHORIZED_KEYS = REMOTE_HOME / ".ssh" / "authorized_keys"
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_RUN = Path(os.environ.get("AURUM_RUN_DIR", "/run/aurum"))
DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
DEFAULT_RUNTIME = Path(os.environ.get("AURUM_RUNTIME_ROOT", "/opt/aurum"))
DESKTOP_PORT = 5900
DESKTOP_UNIT = "aurum-remote-desktop.service"
WEBSOCKET_PORT = 6080
WEBSOCKET_UNIT = "aurum-remote-websocket.service"
MAX_DESKTOP_SECONDS = 4 * 60 * 60
DEPENDENCIES = ("openssh-server", "novnc", "websockify", "x11vnc")
EXACT_REMOTE_COMMANDS = ("status", "seed-sync", "desktop-start", "desktop-stop", "desktop-tunnel")


class RemoteControlError(RuntimeError):
    pass


def _boot_id() -> str | None:
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def catalog() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "machine": "Hopper",
        "transport": "vnc-over-key-only-ssh-loopback-tunnel",
        "commands": list(EXACT_REMOTE_COMMANDS),
        "remote_seed_sync": {
            "repository": "https://github.com/FormatX66/BoxBrain.git",
            "branch": "aurum/trunk-v0.01",
            "fast_forward_only": True,
            "runtime_gate": "become_next_seed",
        },
        "remote_desktop": {
            "listener": "127.0.0.1",
            "port": DESKTOP_PORT,
            "browser_port": WEBSOCKET_PORT,
            "browser_path": "/vnc.html",
            "on_demand": True,
            "max_session_seconds": MAX_DESKTOP_SECONDS,
            "direct_lan_listener": False,
        },
        "authentication": "ssh-ed25519-public-key",
        "raw_shell": False,
        "arbitrary_command": False,
        "password_authentication": False,
        "git_push": False,
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _receipt(operation: str, result: dict[str, Any], *, state_dir: Path = DEFAULT_STATE) -> dict[str, Any]:
    payload = {
        "schema": RECEIPT_SCHEMA,
        "operation": operation,
        "machine": "Hopper",
        "result": result,
        "raw_shell": False,
        "boot_id": _boot_id(),
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    root = state_dir / "remote-control" / "receipts"
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = root / f"{stamp}-{time.time_ns() % 1_000_000_000:09d}-{operation}.json"
    _atomic_json(path, payload)
    _atomic_json(state_dir / "remote-control" / "latest.json", payload)
    payload["receipt_path"] = str(path)
    return payload


def _read_ssh_string(blob: bytes, offset: int) -> tuple[bytes, int]:
    if len(blob) < offset + 4:
        raise RemoteControlError("SSH public key blob is truncated")
    length = int.from_bytes(blob[offset : offset + 4], "big")
    offset += 4
    if length < 1 or len(blob) < offset + length:
        raise RemoteControlError("SSH public key field is invalid")
    return blob[offset : offset + length], offset + length


def normalize_public_key(value: str) -> tuple[str, str]:
    """Accept exactly one ordinary Ed25519 public key, without SSH options."""
    clean = " ".join(str(value or "").strip().split())
    if not clean or "\n" in str(value) or "\r" in str(value) or len(clean) > 900:
        raise RemoteControlError("enter one bounded SSH Ed25519 public key")
    fields = clean.split(" ", 2)
    if len(fields) < 2 or fields[0] != "ssh-ed25519":
        raise RemoteControlError("Hopper remote pairing requires an ssh-ed25519 public key")
    try:
        blob = base64.b64decode(fields[1], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RemoteControlError("SSH public key encoding is invalid") from exc
    key_type, offset = _read_ssh_string(blob, 0)
    key_bytes, offset = _read_ssh_string(blob, offset)
    if key_type != b"ssh-ed25519" or len(key_bytes) != 32 or offset != len(blob):
        raise RemoteControlError("SSH public key blob is not a canonical Ed25519 key")
    comment = fields[2] if len(fields) == 3 else "hopper-remote"
    comment = re.sub(r"[^A-Za-z0-9_.@+-]", "-", comment)[:80] or "hopper-remote"
    normalized = f"ssh-ed25519 {fields[1]} {comment}"
    fingerprint = base64.b64encode(hashlib.sha256(blob).digest()).decode("ascii").rstrip("=")
    return normalized, f"SHA256:{fingerprint}"


def enroll_public_key(
    value: str,
    *,
    authorized_keys: Path = AUTHORIZED_KEYS,
    state_dir: Path = DEFAULT_STATE,
) -> dict[str, Any]:
    normalized, fingerprint = normalize_public_key(value)
    if authorized_keys == AUTHORIZED_KEYS and os.geteuid() != 0:
        raise RemoteControlError("remote pairing requires the root-owned Aurum GUI")
    authorized_keys.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    temporary = authorized_keys.with_name(f".{authorized_keys.name}.{os.getpid()}.tmp")
    temporary.write_text(normalized + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, authorized_keys)
    try:
        account = pwd.getpwnam(REMOTE_USER) if pwd is not None else None
    except KeyError:
        account = None
    if account is not None and authorized_keys == AUTHORIZED_KEYS:
        os.chown(authorized_keys.parent, account.pw_uid, account.pw_gid)
        os.chown(authorized_keys, account.pw_uid, account.pw_gid)
    result = {
        "status": "paired",
        "user": REMOTE_USER,
        "fingerprint": fingerprint,
        "ssh_host_key_fingerprint": _host_key_fingerprint(),
        "commands": list(EXACT_REMOTE_COMMANDS),
        "private_key_stored_on_hopper": False,
        "raw_shell": False,
    }
    return _receipt("pair", result, state_dir=state_dir)


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
    raise RemoteControlError(f"required Aurum module is unavailable: {filename}")


def _run(arguments: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            arguments,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RemoteControlError(f"bounded command failed to start: {type(exc).__name__}:{exc}") from exc


def _service_state(unit: str) -> str:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return "unavailable"
    result = _run([systemctl, "is-active", unit], timeout=15)
    return result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ("active" if result.returncode == 0 else "inactive")


def _listener_addresses(port: int = DESKTOP_PORT) -> list[str]:
    wanted = f"{port:04X}"
    found: set[str] = set()
    tables = ((Path("/proc/net/tcp"), 4), (Path("/proc/net/tcp6"), 6))
    for table, family in tables:
        try:
            lines = table.read_text(encoding="utf-8", errors="replace").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 4 or fields[3] != "0A" or ":" not in fields[1]:
                continue
            address_hex, port_hex = fields[1].rsplit(":", 1)
            if port_hex.upper() != wanted:
                continue
            if family == 4:
                octets = [str(int(address_hex[index : index + 2], 16)) for index in range(6, -1, -2)]
                found.add(".".join(octets))
            elif address_hex == "00000000000000000000000001000000":
                found.add("::1")
            else:
                found.add(f"ipv6:{address_hex.lower()}")
    return sorted(found)


def paired_status(*, authorized_keys: Path = AUTHORIZED_KEYS) -> dict[str, Any]:
    try:
        line = authorized_keys.read_text(encoding="utf-8").strip()
        _normalized, fingerprint = normalize_public_key(line)
    except (OSError, RemoteControlError):
        return {"paired": False, "fingerprint": None}
    return {"paired": True, "fingerprint": fingerprint}


def _host_key_fingerprint() -> str | None:
    try:
        _normalized, fingerprint = normalize_public_key(
            Path("/etc/ssh/ssh_host_ed25519_key.pub").read_text(encoding="utf-8")
        )
    except (OSError, RemoteControlError):
        return None
    return fingerprint


def status(*, authorized_keys: Path = AUTHORIZED_KEYS) -> dict[str, Any]:
    addresses = _listener_addresses()
    websocket_addresses = _listener_addresses(WEBSOCKET_PORT)
    paired = paired_status(authorized_keys=authorized_keys)
    desktop_active = _service_state(DESKTOP_UNIT) == "active"
    websocket_active = _service_state(WEBSOCKET_UNIT) == "active"
    loopback_only = bool(addresses) and set(addresses).issubset({"127.0.0.1", "::1"})
    websocket_loopback_only = bool(websocket_addresses) and set(websocket_addresses).issubset({"127.0.0.1", "::1"})
    session_proof = _json_file(DEFAULT_STATE / "remote-control" / "desktop-session-proof.json")
    session_current = bool(
        session_proof.get("status") == "passed"
        and session_proof.get("boot_id") is not None
        and session_proof.get("boot_id") == _boot_id()
    )
    return {
        "schema": SCHEMA,
        "status": "ready" if paired["paired"] else "pairing-required",
        **paired,
        "ssh_host_key_fingerprint": _host_key_fingerprint(),
        "ssh_service": _service_state("ssh.service"),
        "remote_seed_sync": "available" if paired["paired"] else "pairing-required",
        "desktop": {
            "status": "running" if desktop_active and websocket_active and loopback_only and websocket_loopback_only else "stopped",
            "unit": DESKTOP_UNIT,
            "port": DESKTOP_PORT,
            "listeners": addresses,
            "websocket_unit": WEBSOCKET_UNIT,
            "websocket_port": WEBSOCKET_PORT,
            "websocket_listeners": websocket_addresses,
            "browser_url": "http://127.0.0.1:6080/vnc.html?host=127.0.0.1&port=6080&autoconnect=1&resize=scale",
            "loopback_only": loopback_only and websocket_loopback_only,
            "direct_lan_listener": False,
            "on_demand": True,
            "session_proved_this_boot": session_current,
        },
        "commands": list(EXACT_REMOTE_COMMANDS),
        "raw_shell": False,
    }


def _desktop_command(x11vnc: str) -> list[str]:
    return [
        x11vnc,
        "-display", ":0",
        "-localhost",
        "-rfbport", str(DESKTOP_PORT),
        "-forever",
        "-shared",
        "-repeat",
        "-noxdamage",
        "-nopw",
        "-o", str(DEFAULT_RUN / "remote-desktop.log"),
    ]


def _desktop_failure_detail(unit: str = DESKTOP_UNIT) -> str:
    details: list[str] = []
    log_path = DEFAULT_RUN / "remote-desktop.log"
    try:
        log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-1800:].strip()
    except OSError:
        log_tail = ""
    if log_tail:
        details.append(f"x11vnc={log_tail}")
    systemctl = shutil.which("systemctl")
    if systemctl:
        status_result = _run([systemctl, "status", "--no-pager", "--full", unit], timeout=15)
        status_tail = status_result.stdout[-1800:].strip()
        if status_tail:
            details.append(f"systemd={status_tail}")
    return " | ".join(details)[-3000:]


def _wait_for_loopback(port: int, unit: str, *, seconds: float = 12) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        addresses = _listener_addresses(port)
        if (
            _service_state(unit) == "active"
            and bool(addresses)
            and set(addresses).issubset({"127.0.0.1", "::1"})
        ):
            return True
        time.sleep(0.2)
    return False


def desktop_start(*, state_dir: Path = DEFAULT_STATE) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise RemoteControlError("remote desktop control requires the root-owned policy broker")
    x11vnc = shutil.which("x11vnc")
    websockify = shutil.which("websockify")
    systemd_run = shutil.which("systemd-run")
    novnc_root = Path("/usr/share/novnc")
    if not x11vnc or not websockify or not systemd_run or not (novnc_root / "vnc.html").is_file():
        raise RemoteControlError("remote desktop dependencies are unavailable")
    if not Path("/tmp/.X11-unix/X0").exists():
        raise RemoteControlError("Hopper physical display :0 is not ready")
    current = status()
    if current["desktop"]["status"] == "running":
        return _receipt("desktop-start", {**current["desktop"], "status": "already-running"}, state_dir=state_dir)
    DEFAULT_RUN.mkdir(parents=True, mode=0o700, exist_ok=True)
    (DEFAULT_RUN / "remote-desktop.log").unlink(missing_ok=True)
    systemctl = shutil.which("systemctl")
    if systemctl:
        _run([systemctl, "stop", WEBSOCKET_UNIT], timeout=20)
        _run([systemctl, "reset-failed", WEBSOCKET_UNIT], timeout=20)
        _run([systemctl, "stop", DESKTOP_UNIT], timeout=20)
        _run([systemctl, "reset-failed", DESKTOP_UNIT], timeout=20)
    command = [
        systemd_run,
        f"--unit={DESKTOP_UNIT}",
        "--collect",
        f"--property=RuntimeMaxSec={MAX_DESKTOP_SECONDS}",
        "--property=Restart=no",
        "--property=NoNewPrivileges=yes",
        "--",
        *_desktop_command(x11vnc),
    ]
    started = _run(command, timeout=30)
    if started.returncode != 0:
        raise RemoteControlError(f"remote desktop failed to start: {started.stdout[-1200:]}")
    if not _wait_for_loopback(DESKTOP_PORT, DESKTOP_UNIT):
        detail = _desktop_failure_detail()
        if systemctl:
            _run([systemctl, "stop", DESKTOP_UNIT], timeout=20)
            _run([systemctl, "reset-failed", DESKTOP_UNIT], timeout=20)
        raise RemoteControlError(
            "remote desktop VNC listener was not verified on loopback"
            + (f": {detail}" if detail else "")
        )
    websocket = _run(
        [
            systemd_run,
            f"--unit={WEBSOCKET_UNIT}",
            "--collect",
            f"--property=RuntimeMaxSec={MAX_DESKTOP_SECONDS}",
            "--property=Restart=no",
            "--property=NoNewPrivileges=yes",
            "--",
            websockify,
            f"--web={novnc_root}",
            f"127.0.0.1:{WEBSOCKET_PORT}",
            f"127.0.0.1:{DESKTOP_PORT}",
        ],
        timeout=30,
    )
    if websocket.returncode != 0:
        if systemctl:
            _run([systemctl, "stop", DESKTOP_UNIT], timeout=20)
        raise RemoteControlError(f"remote desktop web viewer failed to start: {websocket.stdout[-1200:]}")
    if _wait_for_loopback(WEBSOCKET_PORT, WEBSOCKET_UNIT):
        observed = status()
        if observed["desktop"]["status"] == "running":
            return _receipt("desktop-start", observed["desktop"], state_dir=state_dir)
    observed = status()
    raise RemoteControlError(f"remote desktop loopback listener was not verified: {observed.get('desktop')}")


def desktop_stop(*, state_dir: Path = DEFAULT_STATE) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise RemoteControlError("remote desktop control requires the root-owned policy broker")
    systemctl = shutil.which("systemctl")
    if not systemctl:
        raise RemoteControlError("systemd is unavailable")
    start_receipt = _json_file(state_dir / "remote-control" / "latest.json")
    websocket_stopped = _run([systemctl, "stop", WEBSOCKET_UNIT], timeout=25)
    _run([systemctl, "reset-failed", WEBSOCKET_UNIT], timeout=20)
    stopped = _run([systemctl, "stop", DESKTOP_UNIT], timeout=25)
    _run([systemctl, "reset-failed", DESKTOP_UNIT], timeout=20)
    addresses = _listener_addresses()
    websocket_addresses = _listener_addresses(WEBSOCKET_PORT)
    result = {
        "status": "stopped" if stopped.returncode == 0 and websocket_stopped.returncode == 0 and not addresses and not websocket_addresses else "failed",
        "unit": DESKTOP_UNIT,
        "listeners": addresses,
        "websocket_unit": WEBSOCKET_UNIT,
        "websocket_listeners": websocket_addresses,
        "loopback_only": not addresses and not websocket_addresses,
    }
    if result["status"] != "stopped":
        raise RemoteControlError(f"remote desktop did not stop cleanly: {result}")
    stop_receipt = _receipt("desktop-stop", result, state_dir=state_dir)
    start_result = start_receipt.get("result") if isinstance(start_receipt.get("result"), dict) else {}
    if (
        start_receipt.get("operation") == "desktop-start"
        and start_receipt.get("boot_id") is not None
        and start_receipt.get("boot_id") == _boot_id()
        and start_result.get("status") in {"running", "already-running"}
        and start_result.get("loopback_only") is True
    ):
        _atomic_json(
            state_dir / "remote-control" / "desktop-session-proof.json",
            {
                "schema": "aurum.remote-desktop-proof.v1",
                "status": "passed",
                "boot_id": _boot_id(),
                "listener": "127.0.0.1",
                "vnc_port": DESKTOP_PORT,
                "browser_port": WEBSOCKET_PORT,
                "loopback_only": True,
                "direct_lan_listener": False,
                "raw_shell": False,
                "started_at": start_receipt.get("observed_at"),
                "stopped_at": stop_receipt.get("observed_at"),
            },
        )
    return stop_receipt


def seed_sync(*, state_dir: Path = DEFAULT_STATE) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise RemoteControlError("remote seed sync requires the root-owned policy broker")
    DEFAULT_RUN.mkdir(parents=True, mode=0o700, exist_ok=True)
    lock_path = DEFAULT_RUN / "remote-seed-sync.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        if fcntl is not None:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RemoteControlError("another verified seed sync is already running") from exc
        network = _load_module("aurum_network.py", "aurum_remote_network")
        online = network.ensure_online(interactive=False)
        if online.get("online") is not True:
            raise RemoteControlError("Hopper is offline; saved Wi-Fi state was not changed")
        workspace_module = _load_module("aurum_workspace.py", "aurum_remote_workspace")
        workspace = workspace_module.AurumWorkspace(
            installed_root=DEFAULT_RUNTIME / "codelation",
            workspace=DEFAULT_WORKSPACE,
            state_dir=state_dir,
        )
        git = workspace.git_sync(authorize_network=True)
        # AurumWorkspace overlays its verified git_status() projection, whose
        # status is "ready", after a clean clone/fast-forward. The method has
        # already enforced the fixed origin/branch and --ff-only merge.
        if git.get("status") not in {"ready", "cloned", "fast-forwarded", "fast-forwarded-with-checkpoint"}:
            raise RemoteControlError(f"Git sync did not reach a verified state: {git.get('status')}")
        if (
            str(git.get("repository") or "").rstrip("/").removesuffix(".git")
            != "https://github.com/FormatX66/BoxBrain"
            or git.get("branch") != "aurum/trunk-v0.01"
            or git.get("dirty") is True
        ):
            raise RemoteControlError("Git sync result did not preserve the fixed clean Aurum trunk")
        runtime_module = _load_module("aurum_runtime_update.py", "aurum_remote_runtime")
        runtime = runtime_module.RuntimeUpdater(
            workspace=DEFAULT_WORKSPACE,
            target=DEFAULT_RUNTIME,
            state_dir=state_dir,
        ).apply()
        generation = runtime.get("generation") if isinstance(runtime.get("generation"), dict) else {}
        result = {
            "status": "verified" if generation.get("become_next_seed") is True else "not-promoted",
            "git": git,
            "runtime": runtime,
            "become_next_seed": bool(generation.get("become_next_seed")),
            "repository": "https://github.com/FormatX66/BoxBrain.git",
            "branch": "aurum/trunk-v0.01",
            "wifi_configuration_mutated": False,
            "raw_shell": False,
        }
        return _receipt("seed-sync", result, state_dir=state_dir)


def _ensure_remote_user() -> dict[str, Any]:
    if pwd is None:
        raise RemoteControlError("POSIX account management is unavailable")
    try:
        account = pwd.getpwnam(REMOTE_USER)
        created = False
    except KeyError:
        useradd = shutil.which("useradd")
        if not useradd:
            raise RemoteControlError("useradd is unavailable")
        result = _run(
            [
                useradd,
                "--system",
                "--create-home",
                "--home-dir", str(REMOTE_HOME),
                "--shell", "/bin/sh",
                "--comment", "Aurum restricted remote transport",
                REMOTE_USER,
            ],
            timeout=30,
        )
        if result.returncode != 0:
            raise RemoteControlError(f"restricted remote user creation failed: {result.stdout[-1000:]}")
        account = pwd.getpwnam(REMOTE_USER)
        created = True
    REMOTE_HOME.mkdir(parents=True, mode=0o750, exist_ok=True)
    AUTHORIZED_KEYS.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if not AUTHORIZED_KEYS.exists():
        AUTHORIZED_KEYS.write_text("", encoding="utf-8")
    os.chmod(AUTHORIZED_KEYS.parent, 0o700)
    os.chmod(AUTHORIZED_KEYS, 0o600)
    os.chown(REMOTE_HOME, account.pw_uid, account.pw_gid)
    os.chown(AUTHORIZED_KEYS.parent, account.pw_uid, account.pw_gid)
    os.chown(AUTHORIZED_KEYS, account.pw_uid, account.pw_gid)
    usermod = shutil.which("usermod")
    if not usermod:
        raise RemoteControlError("usermod is unavailable")
    # OpenSSH rejects a shadow entry beginning with ! even for a valid public
    # key.  Use an intentionally invalid, non-locking crypt string instead: it
    # cannot authenticate as a password, while public-key auth can proceed.
    # sshd also forbids password/interactive auth and forces the named adapter.
    activated = _run([usermod, "--password", "AURUM-REMOTE-KEY-ONLY", REMOTE_USER], timeout=20)
    if activated.returncode != 0:
        raise RemoteControlError(f"restricted remote account activation failed: {activated.stdout[-1000:]}")
    return {"status": "ready", "created": created, "user": REMOTE_USER, "uid": account.pw_uid}


def bootstrap(
    *,
    install_dependencies: bool = False,
    activate_services: bool = True,
    state_dir: Path = DEFAULT_STATE,
) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise RemoteControlError("remote bootstrap requires root")
    missing = [name for name in ("sshd", "websockify", "x11vnc") if shutil.which(name) is None]
    if not Path("/usr/share/novnc/vnc.html").is_file():
        missing.append("novnc-assets")
    install_result: dict[str, Any] = {"status": "not-required", "missing": missing}
    if missing and install_dependencies:
        apt = shutil.which("apt-get")
        if not apt:
            raise RemoteControlError("remote dependencies are missing and apt-get is unavailable")
        environment = dict(os.environ)
        environment["DEBIAN_FRONTEND"] = "noninteractive"
        try:
            installed = subprocess.run(
                [apt, "install", "-y", "--no-install-recommends", *DEPENDENCIES],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=360,
                env=environment,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RemoteControlError(f"remote dependency install failed: {type(exc).__name__}:{exc}") from exc
        if installed.returncode != 0:
            raise RemoteControlError(f"remote dependency install failed: {installed.stdout[-1500:]}")
        install_result = {"status": "installed", "packages": list(DEPENDENCIES)}
    if (
        shutil.which("sshd") is None
        or shutil.which("websockify") is None
        or shutil.which("x11vnc") is None
        or not Path("/usr/share/novnc/vnc.html").is_file()
    ):
        raise RemoteControlError("remote dependencies are unavailable")
    account = _ensure_remote_user()
    config = Path("/etc/ssh/sshd_config.d/60-aurum-remote.conf")
    sudoers = Path("/etc/sudoers.d/aurum-remote")
    if not config.is_file() or not sudoers.is_file():
        raise RemoteControlError("verified remote-control system assets are missing")
    Path("/run/sshd").mkdir(parents=True, mode=0o755, exist_ok=True)
    ssh_keygen = shutil.which("ssh-keygen")
    if not ssh_keygen:
        raise RemoteControlError("ssh-keygen is unavailable")
    host_keys = _run([ssh_keygen, "-A"], timeout=60)
    if host_keys.returncode != 0 or not Path("/etc/ssh/ssh_host_ed25519_key.pub").is_file():
        raise RemoteControlError(f"Hopper SSH host-key preparation failed: {host_keys.stdout[-1200:]}")
    sshd = shutil.which("sshd")
    validation = _run([sshd, "-t"], timeout=30)
    if validation.returncode != 0:
        raise RemoteControlError(f"OpenSSH rejected the restricted configuration: {validation.stdout[-1200:]}")
    systemctl = shutil.which("systemctl")
    activation: dict[str, Any] = {"status": "skipped"}
    if systemctl and activate_services:
        enabled = _run([systemctl, "enable", "ssh.service"], timeout=30)
        restarted = _run([systemctl, "restart", "ssh.service"], timeout=30)
        activation = {
            "status": "ready" if enabled.returncode == 0 and restarted.returncode == 0 else "failed",
            "enable_returncode": enabled.returncode,
            "restart_returncode": restarted.returncode,
        }
        if activation["status"] != "ready":
            raise RemoteControlError(f"restricted OpenSSH activation failed: {activation}")
    result = {
        "status": "ready",
        "account": account,
        "dependencies": install_result,
        "activation": activation,
        "paired": paired_status()["paired"],
        "raw_shell": False,
    }
    _atomic_json(state_dir / "remote-control" / "bootstrap.json", {"schema": SCHEMA, **result})
    return result


def dispatch(command: str, *, state_dir: Path = DEFAULT_STATE) -> dict[str, Any]:
    selected = str(command or "").strip().lower()
    if selected == "status":
        return _receipt("status", status(), state_dir=state_dir)
    if selected == "seed-sync":
        return seed_sync(state_dir=state_dir)
    if selected == "desktop-start":
        return desktop_start(state_dir=state_dir)
    if selected == "desktop-stop":
        return desktop_stop(state_dir=state_dir)
    raise RemoteControlError(f"unsupported remote control action: {selected or '<empty>'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Aurum restricted remote control broker")
    parser.add_argument("command", choices=("catalog", "status", "seed-sync", "desktop-start", "desktop-stop", "bootstrap"))
    parser.add_argument("--install-dependencies", action="store_true")
    parser.add_argument("--no-activate", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "catalog":
            result = catalog()
        elif args.command == "bootstrap":
            result = bootstrap(
                install_dependencies=args.install_dependencies,
                activate_services=not args.no_activate,
            )
        else:
            result = dispatch(args.command)
    except RemoteControlError as exc:
        result = {"schema": SCHEMA, "status": "failed", "detail": str(exc), "raw_shell": False}
        print(json.dumps(result, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
