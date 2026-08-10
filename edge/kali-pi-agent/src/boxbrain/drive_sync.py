"""Guarded Google Drive transport for the BoxBrain Pi edge agent."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


MAX_PATCH_BYTES = 512 * 1024 * 1024
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ALLOWED_PATCH_SUFFIXES = (
    ".cab",
    ".deb",
    ".exe",
    ".msi",
    ".msu",
    ".patch",
    ".ps1",
    ".rpm",
    ".sh",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".zip",
)


class DriveSyncError(RuntimeError):
    """Raised when Drive transport configuration or synchronization fails."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_component(value: str, label: str) -> str:
    if not SAFE_COMPONENT.fullmatch(value):
        raise DriveSyncError(f"{label} contains unsupported characters.")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}-",
        suffix=".json",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _load_manifest(path: Path, inbox: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DriveSyncError(f"{path.name}: invalid JSON: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise DriveSyncError(f"{path.name}: schema_version must be 1.")

    patch_id = _safe_component(str(payload.get("patch_id", "")), "patch_id")
    if path.name != f"{patch_id}.json":
        raise DriveSyncError(f"{path.name}: manifest name must match patch_id.")
    target_hostname = _safe_component(
        str(payload.get("target_hostname", "")),
        "target_hostname",
    )
    payload_name = _safe_component(str(payload.get("payload", "")), "payload")
    if not payload_name.lower().endswith(ALLOWED_PATCH_SUFFIXES):
        raise DriveSyncError(f"{path.name}: payload type is not allowlisted.")
    payload_path = inbox / payload_name
    if (
        payload_path.parent != inbox
        or payload_path.is_symlink()
        or not payload_path.is_file()
    ):
        raise DriveSyncError(f"{path.name}: payload is missing.")

    expected_hash = str(payload.get("sha256", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise DriveSyncError(f"{path.name}: sha256 must be 64 lowercase hex characters.")
    size = payload_path.stat().st_size
    if size <= 0 or size > MAX_PATCH_BYTES:
        raise DriveSyncError(f"{path.name}: payload size is outside the allowed range.")
    declared_size = payload.get("size_bytes")
    if declared_size is not None and declared_size != size:
        raise DriveSyncError(f"{path.name}: size_bytes does not match the payload.")
    actual_hash = sha256_file(payload_path)
    if actual_hash != expected_hash:
        raise DriveSyncError(f"{path.name}: SHA-256 verification failed.")

    return {
        "schema_version": 1,
        "patch_id": patch_id,
        "target_hostname": target_hostname,
        "payload": payload_name,
        "sha256": actual_hash,
        "size_bytes": size,
        "source_manifest": path,
        "source_payload": payload_path,
    }


def verify_patch_inbox(inbox: Path, verified: Path) -> dict[str, Any]:
    verified.mkdir(parents=True, exist_ok=True)
    accepted: list[str] = []
    rejected: list[dict[str, str]] = []
    for manifest_path in sorted(inbox.glob("*.json")):
        try:
            manifest = _load_manifest(manifest_path, inbox)
            reference = f"{manifest['patch_id']}-{manifest['sha256'][:12]}"
            destination = verified / reference
            if destination.exists() and (
                destination.is_symlink() or not destination.is_dir()
            ):
                raise DriveSyncError(f"{manifest_path.name}: verified path is unsafe.")
            if not destination.exists():
                temporary = Path(
                    tempfile.mkdtemp(prefix=".verify-", dir=verified)
                )
                try:
                    shutil.copy2(manifest["source_payload"], temporary / manifest["payload"])
                    stored_manifest = {
                        key: value
                        for key, value in manifest.items()
                        if not key.startswith("source_")
                    }
                    stored_manifest["verified_at"] = utc_now()
                    _atomic_json(temporary / "manifest.json", stored_manifest)
                    os.replace(temporary, destination)
                finally:
                    if temporary.exists():
                        shutil.rmtree(temporary)
            accepted.append(reference)
        except (DriveSyncError, OSError) as error:
            rejected.append({"manifest": manifest_path.name, "reason": str(error)[:500]})
    return {"accepted": accepted, "rejected": rejected}


class DriveSync:
    def __init__(
        self,
        *,
        state_directory: str,
        config_file: str,
        remote: str,
        device_id: str,
        rclone_binary: str = "/usr/bin/rclone",
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.state_directory = Path(state_directory)
        self.config_file = Path(config_file)
        self.remote = _safe_component(remote, "Drive remote")
        self.device_id = _safe_component(device_id, "Drive device ID")
        self.rclone_binary = Path(rclone_binary)
        self.runner = runner
        self.drive_directory = self.state_directory / "drive"
        self.patch_directory = self.drive_directory / "patches"

    def _write_service_snapshot(self) -> None:
        port = os.environ.get("BOXBRAIN_PORT", "8787")
        opener = build_opener(ProxyHandler({}))
        snapshot: dict[str, Any] = {
            "schema_version": 1,
            "captured_at": utc_now(),
        }
        for name, path in (("health", "/health"), ("status", "/api/v1/status")):
            try:
                with opener.open(
                    f"http://127.0.0.1:{port}{path}",
                    timeout=5,
                ) as response:
                    snapshot[name] = json.load(response)
            except (OSError, URLError, UnicodeError, json.JSONDecodeError) as error:
                snapshot[name] = {"error": str(error)[:300]}
        _atomic_json(self.state_directory / "logs" / "service-latest.json", snapshot)

    @classmethod
    def from_environment(cls) -> "DriveSync":
        device_id = os.environ.get("BOXBRAIN_DRIVE_DEVICE_ID", "")
        if not device_id:
            raise DriveSyncError("BOXBRAIN_DRIVE_DEVICE_ID is not configured.")
        return cls(
            state_directory=os.environ.get("BOXBRAIN_STATE_DIR", "/var/lib/boxbrain"),
            config_file=os.environ.get(
                "BOXBRAIN_DRIVE_CONFIG",
                "/var/lib/boxbrain/identity/rclone.conf",
            ),
            remote=os.environ.get("BOXBRAIN_DRIVE_REMOTE", "boxbrain-drive"),
            device_id=device_id,
            rclone_binary=os.environ.get("BOXBRAIN_RCLONE_BIN", "/usr/bin/rclone"),
        )

    def _copy(self, source: str, destination: str, *, patch_download: bool = False) -> None:
        command = [
            str(self.rclone_binary),
            "copy",
            source,
            destination,
            "--config",
            str(self.config_file),
            "--checkers=2",
            "--transfers=1",
            "--retries=2",
            "--low-level-retries=2",
            "--contimeout=10s",
            "--timeout=2m",
            "--drive-skip-shortcuts",
        ]
        if patch_download:
            command.extend(["--max-depth=1", "--max-size=512Mi"])
            for suffix in ALLOWED_PATCH_SUFFIXES:
                command.append(f"--include=*{suffix}")
            command.append("--include=*.json")
        try:
            result = self.runner(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=3300,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise DriveSyncError(f"rclone could not start: {error}") from error
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            message = detail[-1] if detail else "unknown rclone failure"
            raise DriveSyncError(f"rclone copy failed: {message[:500]}")

    def run(self) -> dict[str, Any]:
        if not self.rclone_binary.is_file():
            raise DriveSyncError(f"rclone is unavailable at {self.rclone_binary}.")
        if not self.config_file.is_file():
            raise DriveSyncError(f"Drive configuration is missing at {self.config_file}.")

        self.drive_directory.mkdir(parents=True, exist_ok=True)
        self._write_service_snapshot()
        uploads = (
            (self.state_directory / "logs", f"Logs/{self.device_id}"),
            (
                self.state_directory / "reports",
                f"Diagnostics/{self.device_id}/assessments",
            ),
            (
                self.state_directory / "target-reports",
                f"Diagnostics/{self.device_id}/targets",
            ),
            (
                self.patch_directory / "receipts",
                f"Repositories/Patches/receipts/{self.device_id}",
            ),
        )
        uploaded: list[str] = []
        for local, remote_path in uploads:
            if local.is_dir():
                self._copy(str(local), f"{self.remote}:{remote_path}")
                uploaded.append(remote_path)

        inbox = self.patch_directory / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        self._copy(
            f"{self.remote}:Repositories/Patches/inbox/{self.device_id}",
            str(inbox),
            patch_download=True,
        )
        verification = verify_patch_inbox(inbox, self.patch_directory / "verified")
        result = {
            "status": "ok",
            "completed_at": utc_now(),
            "device_id": self.device_id,
            "uploaded": uploaded,
            "patches": verification,
        }
        _atomic_json(self.drive_directory / "sync-state.json", result)
        _atomic_json(self.state_directory / "logs" / "drive-sync-latest.json", result)
        return result


def main() -> int:
    try:
        result = DriveSync.from_environment().run()
    except DriveSyncError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
