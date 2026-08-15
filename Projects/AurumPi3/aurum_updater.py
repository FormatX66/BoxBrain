#!/usr/bin/env python3
"""Fail-closed application/runtime updater for Aurum Pi3.

The updater deliberately does not touch boot firmware, kernels, partitions, or
the base operating system.  Every install is a complete, immutable runtime
release selected through the /opt/aurum/current symlink.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Iterator

from aurum_release_gate import GateValidationError, validate_update_manifest_gate

try:
    import fcntl
except ImportError:  # pragma: no cover - target runtime is Linux; keeps host tests portable
    fcntl = None  # type: ignore[assignment]


UPDATER_VERSION = "1.1.0"
MANIFEST_SCHEMA = "aurum-application-update-v1"
TARGET = "raspberry-pi-3"
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_RELEASE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
HISTORY_LIMIT = 50


class UpdateError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def as_dict(self) -> dict[str, str]:
        return {"status": "error", "code": self.code, "message": str(self)}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_architecture(value: str) -> str:
    aliases = {
        "aarch64": "arm64",
        "arm64": "arm64",
        "armv7l": "armhf",
        "armv6l": "armhf",
        "x86_64": "amd64",
        "amd64": "amd64",
    }
    return aliases.get(value.lower(), value.lower())


def _version_key(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,3}", value):
        raise UpdateError("invalid-version", f"Unsupported numeric version: {value!r}")
    return tuple(int(part) for part in value.split("."))


def _atomic_json(path: Path, payload: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, mode)
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _fsync_directory(path: Path) -> None:
    flags = getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UpdateError("invalid-json", f"Could not read valid JSON from {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise UpdateError("invalid-json", f"Expected a JSON object in {path}")
    return payload


def _is_remote(value: str) -> bool:
    return urllib.parse.urlparse(value).scheme.lower() in {"http", "https"}


def _local_path(value: str) -> Path:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme == "file":
        if parsed.netloc not in {"", "localhost"}:
            raise UpdateError("unsupported-source", "Remote file:// authorities are not allowed")
        return Path(urllib.request.url2pathname(parsed.path))
    if parsed.scheme:
        raise UpdateError("unsupported-source", f"Unsupported update source scheme: {parsed.scheme}")
    return Path(value).expanduser()


def _fetch_bytes(source: str, *, authorize_network: bool, maximum: int = 1024 * 1024) -> bytes:
    if _is_remote(source):
        parsed = urllib.parse.urlparse(source)
        if parsed.scheme.lower() != "https":
            raise UpdateError("insecure-network", "Remote updates require HTTPS")
        if not authorize_network:
            raise UpdateError("network-not-authorized", "Remote update access requires explicit authorization")
        request = urllib.request.Request(source, headers={"User-Agent": f"AurumUpdater/{UPDATER_VERSION}"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read(maximum + 1)
        except OSError as exc:
            raise UpdateError("network-failed", f"Could not fetch {source}: {exc}") from exc
        if len(data) > maximum:
            raise UpdateError("source-too-large", f"Update metadata exceeds {maximum} bytes")
        return data
    path = _local_path(source)
    try:
        if path.stat().st_size > maximum:
            raise UpdateError("source-too-large", f"Update metadata exceeds {maximum} bytes")
        return path.read_bytes()
    except OSError as exc:
        raise UpdateError("source-unavailable", f"Could not read {path}: {exc}") from exc


def _copy_artifact(source: str, destination: Path, *, authorize_network: bool) -> None:
    partial = destination.with_suffix(destination.suffix + ".partial")
    partial.parent.mkdir(parents=True, exist_ok=True)
    try:
        if _is_remote(source):
            parsed = urllib.parse.urlparse(source)
            if parsed.scheme.lower() != "https":
                raise UpdateError("insecure-network", "Remote artifacts require HTTPS")
            if not authorize_network:
                raise UpdateError("network-not-authorized", "Remote artifact access requires explicit authorization")
            request = urllib.request.Request(source, headers={"User-Agent": f"AurumUpdater/{UPDATER_VERSION}"})
            try:
                with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as output:
                    shutil.copyfileobj(response, output, 1024 * 1024)
            except OSError as exc:
                raise UpdateError("download-failed", f"Could not download {source}: {exc}") from exc
        else:
            local = _local_path(source)
            try:
                with local.open("rb") as input_stream, partial.open("wb") as output:
                    shutil.copyfileobj(input_stream, output, 1024 * 1024)
            except OSError as exc:
                raise UpdateError("artifact-unavailable", f"Could not copy {local}: {exc}") from exc
        with partial.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(partial, destination)
    finally:
        partial.unlink(missing_ok=True)


def _resolve_artifact_source(manifest_source: str, artifact_source: str) -> str:
    if _is_remote(artifact_source) or urllib.parse.urlparse(artifact_source).scheme == "file":
        return artifact_source
    if _is_remote(manifest_source):
        return urllib.parse.urljoin(manifest_source, artifact_source)
    return str((_local_path(manifest_source).resolve().parent / artifact_source).resolve())


def _safe_extract(archive: Path, destination: Path) -> None:
    try:
        source = tarfile.open(archive, "r:gz")
    except (OSError, tarfile.TarError) as exc:
        raise UpdateError("invalid-artifact", f"Artifact is not a valid tar.gz archive: {exc}") from exc
    with source:
        members = source.getmembers()
        if not members:
            raise UpdateError("invalid-artifact", "Artifact archive is empty")
        root = destination.resolve()
        for member in members:
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise UpdateError("unsafe-artifact", f"Unsupported archive entry: {member.name}")
            if not (member.isdir() or member.isfile()):
                raise UpdateError("unsafe-artifact", f"Unsupported archive entry type: {member.name}")
            member_path = (destination / member.name).resolve()
            try:
                member_path.relative_to(root)
            except ValueError as exc:
                raise UpdateError("unsafe-artifact", f"Archive path escapes staging: {member.name}") from exc
        # Every member and resolved destination was validated above. Avoid the
        # newer tarfile filter argument so the stable updater also runs on the
        # original Pi image's Python version.
        # Every member type and resolved destination was checked above.
        source.extractall(destination, members=members, filter="fully_trusted")


class SystemdController:
    def __init__(self, readiness_file: Path = Path("/run/aurum-pi3/console-ready.json")):
        self.readiness_file = readiness_file

    @staticmethod
    def _systemctl(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["/usr/bin/systemctl", *arguments],
                check=check,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=45,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise UpdateError("systemd-failed", f"systemd operation failed: {exc}") from exc

    def schedule_apply(self) -> None:
        self._systemctl("start", "--no-block", "aurum-pi3-update.service")

    def restart_runtime(self) -> None:
        self.readiness_file.unlink(missing_ok=True)
        self._systemctl("restart", "aurum-pi3-console.service", "aurum-pi3-serial.service")

    def wait_ready(self, release_id: str, timeout: float = 45.0) -> tuple[bool, str]:
        deadline = time.monotonic() + timeout
        last = "readiness-not-observed"
        while time.monotonic() < deadline:
            try:
                payload = json.loads(self.readiness_file.read_text(encoding="utf-8"))
                last = str(payload)
                if payload.get("release_id") == release_id and payload.get("selftest") == "ok":
                    active = self._systemctl("is-active", "aurum-pi3-console.service", check=False)
                    if active.returncode == 0:
                        return True, "selftest=ok service=active"
                    last = "primary-console-not-active"
            except (OSError, json.JSONDecodeError):
                pass
            time.sleep(0.5)
        return False, last


SelftestRunner = Callable[[Path, str], tuple[bool, str]]


def _default_selftest(release: Path, release_id: str) -> tuple[bool, str]:
    console = release / "aurum_pi3_console.py"
    environment = dict(os.environ)
    environment["AURUM_ROOT"] = str(release)
    environment["AURUM_RELEASE_ID"] = release_id
    environment.pop("AURUM_READINESS_FILE", None)
    try:
        result = subprocess.run(
            [sys.executable, str(console), "--selftest-json"],
            cwd=str(release),
            env=environment,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=90,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"selftest-execution-failed:{exc}"
    if result.returncode != 0:
        return False, result.stdout.strip()[-1000:]
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False, "selftest-output-invalid"
    return payload.get("selftest") == "ok", str(payload.get("detail", "missing-detail"))


class AurumUpdater:
    def __init__(
        self,
        *,
        base_dir: Path = Path("/opt/aurum"),
        state_dir: Path = Path("/var/lib/aurum-updater"),
        target: str = TARGET,
        architecture: str | None = None,
        controller: Any | None = None,
        selftest_runner: SelftestRunner | None = None,
    ):
        self.base_dir = base_dir
        self.releases_dir = base_dir / "releases"
        self.staging_dir = base_dir / ".staging"
        self.current_link = base_dir / "current"
        self.state_dir = state_dir
        self.state_file = state_dir / "state.json"
        self.lock_file = state_dir / "update.lock"
        self.target = target
        self.architecture = _normalized_architecture(architecture or platform.machine())
        self.controller = controller or SystemdController()
        self.selftest_runner = selftest_runner or _default_selftest

    @contextlib.contextmanager
    def _lock(self) -> Iterator[None]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_file.open("a+") as stream:
            if fcntl is not None:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _active_path(self) -> Path | None:
        if not self.current_link.is_symlink():
            return None
        return self.current_link.resolve(strict=False)

    def _release_id(self, path: Path | None) -> str | None:
        if path is None:
            return None
        try:
            path.resolve(strict=False).relative_to(self.releases_dir.resolve())
        except ValueError as exc:
            raise UpdateError("invalid-activation", "Active release is outside the release store") from exc
        return path.name

    def _default_state(self) -> dict[str, Any]:
        active_path = self._active_path()
        return {
            "schema": "aurum-updater-state-v1",
            "updater_version": UPDATER_VERSION,
            "active_release": self._release_id(active_path),
            "previous_release": None,
            "pending": None,
            "history": [],
        }

    def _load_state(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return self._default_state()
        state = _read_json(self.state_file)
        if state.get("schema") != "aurum-updater-state-v1":
            raise UpdateError("invalid-state", "Unsupported updater state schema")
        state.setdefault("history", [])
        state.setdefault("pending", None)
        return state

    def _save_state(self, state: dict[str, Any]) -> None:
        state["updater_version"] = UPDATER_VERSION
        state["history"] = list(state.get("history", []))[-HISTORY_LIMIT:]
        _atomic_json(self.state_file, state)

    @staticmethod
    def _event(state: dict[str, Any], action: str, **details: Any) -> None:
        state.setdefault("history", []).append(
            {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "action": action, **details}
        )

    def _manifest(self, source: str, expected_sha256: str, authorize_network: bool) -> dict[str, Any]:
        expected = expected_sha256.lower()
        if not HEX_SHA256.fullmatch(expected):
            raise UpdateError("invalid-manifest-pin", "Manifest SHA-256 pin must be 64 lowercase hex characters")
        raw = _fetch_bytes(source, authorize_network=authorize_network)
        actual = sha256_bytes(raw)
        if actual != expected:
            raise UpdateError("manifest-integrity-failed", f"Manifest SHA-256 mismatch: expected {expected}, got {actual}")
        try:
            manifest = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UpdateError("invalid-manifest", f"Manifest JSON is invalid: {exc}") from exc
        if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
            raise UpdateError("invalid-manifest", "Unsupported update manifest schema")
        version = manifest.get("version")
        release_id = manifest.get("release_id")
        target = manifest.get("target")
        architecture = manifest.get("architecture")
        artifact = manifest.get("artifact")
        if not isinstance(version, str):
            raise UpdateError("invalid-manifest", "Manifest version is missing")
        _version_key(version)
        if not isinstance(release_id, str) or not SAFE_RELEASE.fullmatch(release_id):
            raise UpdateError("invalid-manifest", "Manifest release identity is invalid")
        if target != self.target:
            raise UpdateError("wrong-target", f"Update targets {target!r}, expected {self.target!r}")
        architectures = [architecture] if isinstance(architecture, str) else architecture
        if not isinstance(architectures, list) or self.architecture not in {
            _normalized_architecture(str(value)) for value in architectures
        }:
            raise UpdateError(
                "wrong-architecture",
                f"Update architectures {architectures!r} do not include {self.architecture!r}",
            )
        if not isinstance(artifact, dict):
            raise UpdateError("invalid-manifest", "Manifest artifact is missing")
        if artifact.get("format") != "tar.gz":
            raise UpdateError("invalid-manifest", "Only tar.gz application artifacts are supported")
        if not isinstance(artifact.get("url"), str) or not artifact["url"]:
            raise UpdateError("invalid-manifest", "Artifact URL/path is missing")
        artifact_sha = str(artifact.get("sha256", "")).lower()
        if not HEX_SHA256.fullmatch(artifact_sha):
            raise UpdateError("invalid-manifest", "Artifact SHA-256 is invalid")
        minimum = str(manifest.get("minimum_updater_version", "1.0.0"))
        if _version_key(minimum) > _version_key(UPDATER_VERSION):
            raise UpdateError("updater-too-old", f"Update requires updater {minimum} or newer")
        expected_scope = {
            "application_runtime": True,
            "boot_firmware": False,
            "kernel": False,
            "operating_system": False,
        }
        if manifest.get("scope") != expected_scope:
            raise UpdateError("forbidden-scope", "Updater accepts application/runtime-only releases")
        try:
            manifest["_convergence"] = validate_update_manifest_gate(manifest)
        except GateValidationError as exc:
            raise UpdateError("convergence-gate-failed", str(exc)) from exc
        manifest["_source"] = source
        manifest["_sha256"] = actual
        manifest["_artifact_source"] = _resolve_artifact_source(source, artifact["url"])
        return manifest

    def _current_version(self) -> str | None:
        active = self._active_path()
        if active is None:
            return None
        release_file = active / "RELEASE.json"
        if not release_file.exists():
            return None
        version = _read_json(release_file).get("version")
        return str(version) if version is not None else None

    def check(self, source: str, expected_sha256: str, *, authorize_network: bool = False) -> dict[str, Any]:
        manifest = self._manifest(source, expected_sha256, authorize_network)
        current = self._current_version()
        update_available = current is None or _version_key(manifest["version"]) > _version_key(current)
        return {
            "status": "ok",
            "target": self.target,
            "architecture": self.architecture,
            "current_version": current,
            "available_version": manifest["version"],
            "update_available": update_available,
            "manifest_sha256": manifest["_sha256"],
            "artifact_sha256": manifest["artifact"]["sha256"],
            "source_commit": manifest["source_commit"],
            "convergence_verified": manifest["_convergence"]["status"] == "verified",
            "network_authorized": bool(authorize_network),
        }

    def _validate_candidate(self, candidate: Path, manifest: dict[str, Any]) -> str:
        release_file = candidate / "RELEASE.json"
        console = candidate / "aurum_pi3_console.py"
        updater = candidate / "aurum_updater.py"
        release_gate = candidate / "aurum_release_gate.py"
        field = candidate / "codelation" / "field"
        if not all(path.is_file() for path in (release_file, console, updater, release_gate)) or not field.is_dir():
            raise UpdateError(
                "invalid-payload",
                "Runtime payload is missing RELEASE.json, console, updater, release gate, or Codelation Field",
            )
        release = _read_json(release_file)
        if release.get("version") != manifest["version"] or release.get("target") != self.target:
            raise UpdateError("payload-mismatch", "Runtime release metadata does not match its manifest")
        if _normalized_architecture(str(release.get("architecture", ""))) != self.architecture:
            raise UpdateError("payload-mismatch", "Runtime payload architecture does not match this machine")
        if release.get("source_commit") != manifest["source_commit"]:
            raise UpdateError("payload-mismatch", "Runtime payload commit does not match its manifest")
        if (
            release.get("application_layer_only") is not True
            or release.get("includes_boot_firmware") is not False
            or release.get("includes_kernel") is not False
        ):
            raise UpdateError("payload-mismatch", "Runtime payload is not application-layer-only")
        release_id = str(release.get("release_id", ""))
        if release_id != manifest["release_id"] or not SAFE_RELEASE.fullmatch(release_id):
            raise UpdateError("payload-mismatch", "Runtime release identity is invalid")
        return release_id

    def stage(self, source: str, expected_sha256: str, *, authorize_network: bool = False) -> dict[str, Any]:
        with self._lock():
            state = self._load_state()
            if state.get("pending"):
                raise UpdateError("update-pending", "An update or rollback is already pending")
            manifest = self._manifest(source, expected_sha256, authorize_network)
            current_version = self._current_version()
            if current_version is not None and _version_key(manifest["version"]) <= _version_key(current_version):
                raise UpdateError("not-newer", f"Update {manifest['version']} is not newer than {current_version}")

            request_id = uuid.uuid4().hex
            work = self.staging_dir / request_id
            archive = work / "runtime.tar.gz"
            extracted = work / "extracted"
            work.mkdir(parents=True, exist_ok=False)
            try:
                _copy_artifact(manifest["_artifact_source"], archive, authorize_network=authorize_network)
                actual = sha256_file(archive)
                expected = manifest["artifact"]["sha256"]
                if actual != expected:
                    raise UpdateError("artifact-integrity-failed", f"Artifact SHA-256 mismatch: expected {expected}, got {actual}")
                expected_bytes = manifest["artifact"].get("bytes")
                if expected_bytes is not None and archive.stat().st_size != int(expected_bytes):
                    raise UpdateError("artifact-size-failed", "Artifact size does not match its manifest")
                extracted.mkdir()
                _safe_extract(archive, extracted)
                payload_root = str(manifest["artifact"].get("root", "payload"))
                if not SAFE_RELEASE.fullmatch(payload_root):
                    raise UpdateError("invalid-manifest", "Artifact root is invalid")
                candidate = extracted / payload_root
                release_id = self._validate_candidate(candidate, manifest)
                ok, detail = self.selftest_runner(candidate, release_id)
                if not ok:
                    raise UpdateError("preactivation-selftest-failed", detail)
                self.releases_dir.mkdir(parents=True, exist_ok=True)
                destination = self.releases_dir / release_id
                if destination.exists():
                    existing = _read_json(destination / "RELEASE.json")
                    marker = destination / ".artifact-sha256"
                    if (
                        existing.get("release_id") != release_id
                        or not marker.is_file()
                        or marker.read_text(encoding="ascii").strip() != expected
                    ):
                        raise UpdateError("release-collision", f"Release directory collision: {release_id}")
                else:
                    (candidate / ".artifact-sha256").write_text(expected + "\n", encoding="ascii")
                    os.replace(candidate, destination)
                    _fsync_directory(self.releases_dir)
                active_path = self._active_path()
                previous = self._release_id(active_path)
                pending = {
                    "request_id": request_id,
                    "operation": "update",
                    "phase": "staged",
                    "candidate_release": release_id,
                    "previous_release": previous,
                    "manifest_sha256": manifest["_sha256"],
                    "artifact_sha256": expected,
                    "source_commit": manifest["source_commit"],
                    "convergence_sha256": manifest["verification"]["convergence_sha256"],
                    "version": manifest["version"],
                    "network_authorized": bool(authorize_network),
                }
                state["pending"] = pending
                self._event(state, "update-staged", release=release_id, previous=previous)
                self._save_state(state)
                return {"status": "staged", **pending, "preactivation_selftest": detail}
            finally:
                shutil.rmtree(work, ignore_errors=True)

    def _release_path(self, release_id: str) -> Path:
        if not SAFE_RELEASE.fullmatch(release_id):
            raise UpdateError("invalid-release", "Release identity is invalid")
        path = (self.releases_dir / release_id).resolve(strict=False)
        try:
            path.relative_to(self.releases_dir.resolve())
        except ValueError as exc:
            raise UpdateError("invalid-release", "Release path escapes the release store") from exc
        if not path.is_dir():
            raise UpdateError("missing-release", f"Release is unavailable: {release_id}")
        return path

    def _activate(self, release_id: str) -> None:
        release = self._release_path(release_id)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.base_dir / f".current.{os.getpid()}.{uuid.uuid4().hex}"
        try:
            os.symlink(str(release), temporary, target_is_directory=True)
            os.replace(temporary, self.current_link)
            _fsync_directory(self.base_dir)
        finally:
            temporary.unlink(missing_ok=True)

    def schedule(self) -> None:
        self.controller.schedule_apply()

    def schedule_rollback(self) -> dict[str, Any]:
        with self._lock():
            state = self._load_state()
            if state.get("pending"):
                raise UpdateError("update-pending", "An update or rollback is already pending")
            active = self._release_id(self._active_path())
            previous = state.get("previous_release")
            if not active or not isinstance(previous, str):
                raise UpdateError("rollback-unavailable", "No previous healthy release is available")
            self._release_path(previous)
            state["pending"] = {
                "request_id": uuid.uuid4().hex,
                "operation": "rollback",
                "phase": "staged",
                "candidate_release": previous,
                "previous_release": active,
                "version": _read_json(self.releases_dir / previous / "RELEASE.json").get("version"),
                "network_authorized": False,
            }
            self._event(state, "rollback-staged", release=previous, previous=active)
            self._save_state(state)
            return {"status": "staged", **state["pending"]}

    def apply_pending(self) -> dict[str, Any]:
        with self._lock():
            state = self._load_state()
            pending = state.get("pending")
            if not isinstance(pending, dict):
                raise UpdateError("nothing-pending", "No update or rollback is pending")
            candidate = str(pending.get("candidate_release", ""))
            previous = pending.get("previous_release")
            operation = str(pending.get("operation", "update"))
            self._release_path(candidate)
            if previous is not None:
                self._release_path(str(previous))
            pending["phase"] = "activating"
            self._save_state(state)
            self._activate(candidate)
            pending["phase"] = "health-check"
            self._save_state(state)
            try:
                self.controller.restart_runtime()
                healthy, detail = self.controller.wait_ready(candidate)
                if not healthy:
                    raise UpdateError("postactivation-selftest-failed", detail)
            except Exception as exc:
                rollback_detail = "no-previous-release"
                if isinstance(previous, str):
                    self._activate(previous)
                    try:
                        self.controller.restart_runtime()
                        restored, rollback_detail = self.controller.wait_ready(previous)
                        if not restored:
                            rollback_detail = f"rollback-readiness-failed:{rollback_detail}"
                    except Exception as rollback_exc:  # preserve the original failure
                        rollback_detail = f"rollback-restart-failed:{rollback_exc}"
                state["active_release"] = previous
                state["pending"] = None
                self._event(
                    state,
                    "automatic-rollback",
                    failed_release=candidate,
                    restored_release=previous,
                    reason=str(exc),
                    rollback_detail=rollback_detail,
                )
                self._save_state(state)
                if isinstance(exc, UpdateError):
                    raise
                raise UpdateError("activation-failed", str(exc)) from exc

            state["active_release"] = candidate
            state["previous_release"] = previous
            state["pending"] = None
            self._event(state, f"{operation}-activated", release=candidate, previous=previous, readiness=detail)
            self._save_state(state)
            return {"status": "activated", "operation": operation, "release": candidate, "previous": previous}

    def recover(self) -> dict[str, Any]:
        """Fail back to the last release if power was lost during activation."""
        with self._lock():
            state = self._load_state()
            pending = state.get("pending")
            if not isinstance(pending, dict):
                return {"status": "clean", "active_release": self._release_id(self._active_path())}
            phase = str(pending.get("phase", "unknown"))
            candidate = pending.get("candidate_release")
            previous = pending.get("previous_release")
            active = self._release_id(self._active_path())
            if phase in {"activating", "health-check"} and isinstance(previous, str):
                self._activate(previous)
                active = previous
            state["active_release"] = active
            state["pending"] = None
            self._event(
                state,
                "interrupted-update-recovered",
                interrupted_phase=phase,
                candidate_release=candidate,
                restored_release=active,
            )
            self._save_state(state)
            return {"status": "recovered", "interrupted_phase": phase, "active_release": active}

    def status(self) -> dict[str, Any]:
        with self._lock():
            state = self._load_state()
            active = self._release_id(self._active_path())
            return {
                "status": "ok",
                "updater_version": UPDATER_VERSION,
                "target": self.target,
                "architecture": self.architecture,
                "active_release": active,
                "previous_release": state.get("previous_release"),
                "pending": state.get("pending"),
                "history": state.get("history", []),
            }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aurum Pi3 pinned application updater")
    parser.add_argument("--base-dir", type=Path, default=Path("/opt/aurum"))
    parser.add_argument("--state-dir", type=Path, default=Path("/var/lib/aurum-updater"))
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "request"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", required=True)
        command.add_argument("--manifest-sha256", required=True)
        command.add_argument("--authorize-network", action="store_true")
    commands.add_parser("status")
    commands.add_parser("request-rollback")
    commands.add_parser("apply-pending")
    commands.add_parser("recover")
    return parser


def main() -> int:
    args = _parser().parse_args()
    updater = AurumUpdater(base_dir=args.base_dir, state_dir=args.state_dir)
    try:
        if args.command == "check":
            result = updater.check(args.manifest, args.manifest_sha256, authorize_network=args.authorize_network)
        elif args.command == "request":
            result = updater.stage(args.manifest, args.manifest_sha256, authorize_network=args.authorize_network)
            updater.schedule()
            result["activation"] = "scheduled"
        elif args.command == "status":
            result = updater.status()
        elif args.command == "request-rollback":
            result = updater.schedule_rollback()
            updater.schedule()
            result["activation"] = "scheduled"
        elif args.command == "apply-pending":
            result = updater.apply_pending()
        else:
            result = updater.recover()
    except UpdateError as exc:
        print(json.dumps(exc.as_dict(), indent=2, sort_keys=True), flush=True)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
