#!/usr/bin/env python3
"""Transactional installer for the event-driven Aurum Farmer worker.

This installer never creates a second Slush database. It discovers and validates the
existing Aurum state store, stages Last-Known-Good backups, installs the reviewed
Farmer/Hive pair, and verifies a live event -> drain acknowledgement. A failed
promotion restores the prior files/service unit when possible.
"""
from __future__ import annotations

import argparse
import grp
import json
import os
import pwd
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SERVICE_NAME = "aurum-farmer.service"
DEFAULT_INSTALL_DIR = Path("/opt/aurum/farmer")
DEFAULT_UNIT_PATH = Path("/etc/systemd/system") / SERVICE_NAME


def emit(status: str, **payload: Any) -> None:
    print(json.dumps({"status": status, **payload}, sort_keys=True))


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=check)


def sqlite_tables(path: Path) -> set[str]:
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        rows = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        con.close()
        return {str(row[0]) for row in rows}
    except Exception:
        return set()


def validate_slush(path: Path) -> tuple[bool, int]:
    tables = sqlite_tables(path)
    required = {"objects", "tags"}
    if not required.issubset(tables):
        return False, 0
    score = 10
    score += 4 if "hive_events" in tables else 0
    score += 2 if "hive_nodes" in tables else 0
    score += 2 if "hive_receipts" in tables else 0
    score += 1 if "farmer_events" in tables else 0
    return True, score


def discover_slush(explicit: str | None = None) -> Path:
    candidates: list[Path] = []
    for raw in [explicit, os.environ.get("AURUM_SLUSH_DB")]:
        if raw:
            candidates.append(Path(raw).expanduser())
    candidates.extend([
        Path("/var/lib/aurum/slush.db"),
        Path("/opt/aurum/slush.db"),
        Path("/opt/aurum/codelation/slush.db"),
        Path("/opt/boxbrain/codelation/slush.db"),
        Path("/var/lib/aurum/workspace/BoxBrain/slush.db"),
    ])
    seen: set[Path] = set()
    scored: list[tuple[int, float, Path]] = []
    for candidate in candidates:
        try:
            candidate = candidate.resolve()
        except OSError:
            continue
        if candidate in seen or not candidate.is_file():
            continue
        seen.add(candidate)
        valid, score = validate_slush(candidate)
        if valid:
            scored.append((score, candidate.stat().st_mtime, candidate))
    if not scored:
        for root in [Path("/var/lib/aurum"), Path("/opt/aurum"), Path("/opt/boxbrain")]:
            if not root.exists():
                continue
            for candidate in root.rglob("slush.db"):
                try:
                    candidate = candidate.resolve()
                except OSError:
                    continue
                if candidate in seen or not candidate.is_file():
                    continue
                seen.add(candidate)
                valid, score = validate_slush(candidate)
                if valid:
                    scored.append((score, candidate.stat().st_mtime, candidate))
    if not scored:
        raise RuntimeError("existing_valid_slush_db_not_found")
    scored.sort(key=lambda item: (-item[0], -item[1], str(item[2])))
    return scored[0][2]


def discover_workspace(explicit: str | None, db: Path) -> Path:
    for raw in [explicit, os.environ.get("AURUM_WORKSPACE")]:
        if raw and Path(raw).is_dir():
            return Path(raw).resolve()
    candidates = [
        Path("/var/lib/aurum/workspace/BoxBrain"),
        Path("/opt/aurum/workspace/BoxBrain"),
        Path("/opt/lib/aurum/workspace/BoxBrain"),
        Path("/opt/boxbrain"),
    ]
    for candidate in candidates:
        if (candidate / ".git").exists():
            return candidate.resolve()
    return db.parent.resolve()


def identity_for(path: Path) -> tuple[str | None, str | None]:
    stat = path.stat()
    try:
        user = pwd.getpwuid(stat.st_uid).pw_name
    except KeyError:
        user = None
    try:
        group = grp.getgrgid(stat.st_gid).gr_name
    except KeyError:
        group = None
    return user, group


def systemd_escape(value: Path | str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def render_unit(*, python: str, worker: Path, db: Path, socket_path: Path, workspace: Path) -> str:
    user, group = identity_for(db)
    identity_lines = []
    if user:
        identity_lines.append(f"User={user}")
    if group:
        identity_lines.append(f"Group={group}")
    return "\n".join([
        "[Unit]",
        "Description=Aurum Farmer event-driven completion worker",
        "After=local-fs.target",
        f"ConditionPathExists={systemd_escape(db)}",
        "",
        "[Service]",
        "Type=simple",
        *identity_lines,
        f"WorkingDirectory={systemd_escape(workspace)}",
        f'Environment="AURUM_SLUSH_DB={systemd_escape(db)}"',
        f'Environment="AURUM_FARMER_SOCKET={systemd_escape(socket_path)}"',
        f'Environment="AURUM_WORKSPACE={systemd_escape(workspace)}"',
        f"ExecStart={systemd_escape(python)} {systemd_escape(worker)}",
        "Restart=on-failure",
        "UMask=0007",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "ProtectSystem=full",
        f"ReadWritePaths={systemd_escape(db.parent)} {systemd_escape(workspace)}",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "",
    ])


def atomic_copy(source: Path, destination: Path, backups: list[tuple[Path, Path]]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        backup = destination.with_name(destination.name + f".lkg-{int(time.time())}")
        shutil.copy2(destination, backup)
        backups.append((destination, backup))
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=destination.name + ".", delete=False) as handle:
        temp = Path(handle.name)
    try:
        shutil.copy2(source, temp)
        os.chmod(temp, 0o755 if destination.suffix == ".py" else 0o644)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def atomic_text(text: str, destination: Path, backups: list[tuple[Path, Path]]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        backup = destination.with_name(destination.name + f".lkg-{int(time.time())}")
        shutil.copy2(destination, backup)
        backups.append((destination, backup))
    with tempfile.NamedTemporaryFile("w", dir=destination.parent, prefix=destination.name + ".", delete=False) as handle:
        handle.write(text)
        temp = Path(handle.name)
    try:
        os.chmod(temp, 0o644)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def restore(backups: list[tuple[Path, Path]], created: list[Path]) -> None:
    for path in reversed(created):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    for destination, backup in reversed(backups):
        try:
            shutil.copy2(backup, destination)
        except OSError:
            pass


def live_ack(socket_path: Path) -> dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5.0)
        client.connect(str(socket_path))
        client.sendall(json.dumps({"event": "installer_verify"}, separators=(",", ":")).encode())
        raw = client.recv(4096)
    decoded = json.loads(raw.decode())
    if not isinstance(decoded, dict) or decoded.get("status") != "drained":
        raise RuntimeError("farmer_worker_did_not_acknowledge_drain")
    return decoded


def decision_engine_source(source_dir: Path) -> Path:
    bundled = source_dir / "decision_engine.py"
    if bundled.is_file():
        return bundled
    return source_dir.parents[2] / "AurumFarmer" / "aurum_farmer" / "decision_engine.py"


def operation_gate_source(source_dir: Path) -> Path:
    return decision_engine_source(source_dir).with_name("operation_gate.py")


def preflight(source_dir: Path) -> None:
    worker = source_dir / "aurum_worker.py"
    hive = source_dir / "aurum_hive.py"
    tests = source_dir / "test_aurum_farmer_core.py"
    for path in [worker, hive, decision_engine_source(source_dir), operation_gate_source(source_dir)]:
        if not path.is_file():
            raise RuntimeError(f"missing_source:{path.name}")
    result = run([sys.executable, "-m", "py_compile", str(worker), str(hive)], check=False)
    if result.returncode:
        raise RuntimeError("python_compile_failed:" + (result.stderr or result.stdout)[-1000:])
    if tests.is_file():
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "-q", tests.name],
            cwd=source_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError("farmer_tests_failed:" + (result.stdout + result.stderr)[-2000:])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--install-dir", default=str(DEFAULT_INSTALL_DIR))
    parser.add_argument("--unit-path", default=str(DEFAULT_UNIT_PATH))
    parser.add_argument("--slush-db")
    parser.add_argument("--workspace")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source_dir = Path(args.source_dir).resolve()
    try:
        preflight(source_dir)
        db = discover_slush(args.slush_db)
        workspace = discover_workspace(args.workspace, db)
    except Exception as exc:
        emit("machine_blocked", human_required=False, blocker={"kind": "preflight_failed", "message": str(exc)})
        return 3

    install_dir = Path(args.install_dir)
    unit_path = Path(args.unit_path)
    socket_path = Path(os.environ.get("AURUM_FARMER_SOCKET", str(db.parent / "aurum-farmer.sock")))
    worker_dest = install_dir / "aurum_worker.py"
    hive_dest = install_dir / "aurum_hive.py"
    engine_dest = install_dir / "decision_engine.py"
    gate_dest = install_dir / "operation_gate.py"
    unit = render_unit(
        python=sys.executable,
        worker=worker_dest,
        db=db,
        socket_path=socket_path,
        workspace=workspace,
    )

    if args.dry_run:
        emit(
            "preflight_verified",
            human_required=False,
            slush_db=str(db),
            workspace=str(workspace),
            install_dir=str(install_dir),
            wake_socket=str(socket_path),
            continuation="event_driven_no_polling",
            unit_has_timer="Timer" in unit or "OnUnit" in unit,
        )
        return 0

    if os.name != "posix" or not hasattr(socket, "AF_UNIX"):
        emit("machine_blocked", human_required=False, blocker={"kind": "unsupported_runtime", "os": os.name})
        return 4
    if os.geteuid() != 0:
        emit("machine_blocked", human_required=False, blocker={"kind": "elevated_executor_required"})
        return 5

    backups: list[tuple[Path, Path]] = []
    created: list[Path] = []
    for target in [worker_dest, hive_dest, engine_dest, gate_dest, unit_path]:
        if not target.exists():
            created.append(target)
    try:
        atomic_copy(source_dir / "aurum_worker.py", worker_dest, backups)
        atomic_copy(source_dir / "aurum_hive.py", hive_dest, backups)
        atomic_copy(decision_engine_source(source_dir), engine_dest, backups)
        atomic_copy(operation_gate_source(source_dir), gate_dest, backups)
        atomic_text(unit, unit_path, backups)
        run(["systemctl", "daemon-reload"])
        run(["systemctl", "enable", "--now", SERVICE_NAME])
        active = run(["systemctl", "is-active", SERVICE_NAME], check=False)
        if active.returncode != 0 or active.stdout.strip() != "active":
            raise RuntimeError("service_not_active:" + (active.stdout + active.stderr).strip())
        ack = live_ack(socket_path)
        emit(
            "running_verified",
            human_required=False,
            service=SERVICE_NAME,
            slush_db=str(db),
            workspace=str(workspace),
            wake_socket=str(socket_path),
            wake_ack=ack,
            last_known_good_backups=[str(backup) for _, backup in backups],
            continuation="event_driven_no_polling",
        )
        return 0
    except Exception as exc:
        try:
            run(["systemctl", "stop", SERVICE_NAME], check=False)
        except Exception:
            pass
        restore(backups, created)
        try:
            run(["systemctl", "daemon-reload"], check=False)
            if unit_path.exists():
                run(["systemctl", "start", SERVICE_NAME], check=False)
        except Exception:
            pass
        emit(
            "machine_blocked",
            human_required=False,
            blocker={"kind": "promotion_failed_rolled_back", "message": str(exc)[:1000]},
            last_known_good_restored=True,
        )
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
