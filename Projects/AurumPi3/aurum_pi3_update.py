#!/usr/bin/env python3
"""Integrity-checked, explicit updater for the Aurum Pi3 capability layer."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "aurum-pi3-update-v1"
TARGET = "raspberry-pi-3"
MAX_MANIFEST_BYTES = 1_048_576
MAX_BUNDLE_BYTES = 20 * 1_048_576
MAX_EXPANDED_BYTES = 40 * 1_048_576
SHA256 = re.compile(r"^[0-9a-f]{64}$")
INSTALL_PREFIX = PurePosixPath("/opt/aurum")


class UpdateBarrier(RuntimeError):
    """A safe stop scoped only to the requested update."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_limited(response: Any, limit: int) -> bytes:
    data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateBarrier(f"download-exceeds-{limit}-bytes")
    return data


def _read_source(source: str, limit: int) -> bytes:
    parsed = urllib.parse.urlparse(source)
    windows_path = bool(re.match(r"^[A-Za-z]:[\\/]", source))
    if parsed.scheme == "https":
        request = urllib.request.Request(
            source, headers={"User-Agent": "Aurum-Pi3-Updater/0.01"}
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                if urllib.parse.urlparse(response.geturl()).scheme != "https":
                    raise UpdateBarrier("https-redirect-downgrade-rejected")
                return _read_limited(response, limit)
        except Exception as exc:
            raise UpdateBarrier(f"https-fetch-failed:{type(exc).__name__}") from exc
    if parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path))
    elif parsed.scheme == "" or windows_path:
        path = Path(source)
    else:
        raise UpdateBarrier("manifest-source-must-be-local-file-or-https")
    try:
        if path.stat().st_size > limit:
            raise UpdateBarrier(f"file-exceeds-{limit}-bytes")
        return path.read_bytes()
    except OSError as exc:
        raise UpdateBarrier(f"local-file-read-failed:{type(exc).__name__}") from exc


def _resolve_package_source(manifest_source: str, filename: str) -> str:
    if Path(filename).name != filename or filename in {"", ".", ".."}:
        raise UpdateBarrier("package-filename-must-be-a-basename")
    parsed = urllib.parse.urlparse(manifest_source)
    windows_path = bool(re.match(r"^[A-Za-z]:[\\/]", manifest_source))
    if parsed.scheme == "https":
        return urllib.parse.urljoin(manifest_source, urllib.parse.quote(filename))
    if parsed.scheme == "file":
        manifest_path = Path(urllib.request.url2pathname(parsed.path))
        return str(manifest_path.parent / filename)
    if parsed.scheme == "" or windows_path:
        return str(Path(manifest_source).parent / filename)
    raise UpdateBarrier("manifest-source-must-be-local-file-or-https")


def _validated_install_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts:
        raise UpdateBarrier(f"unsafe-install-path:{value}")
    if path == INSTALL_PREFIX or INSTALL_PREFIX not in path.parents:
        raise UpdateBarrier(f"install-path-outside-aurum-root:{value}")
    return path


def _validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise UpdateBarrier("unsupported-update-schema")
    if value.get("target") != TARGET:
        raise UpdateBarrier("update-target-mismatch")
    package = value.get("package")
    files = value.get("files")
    if not isinstance(package, dict) or not isinstance(files, list) or not files:
        raise UpdateBarrier("update-manifest-incomplete")
    if not SHA256.fullmatch(str(package.get("sha256", ""))):
        raise UpdateBarrier("invalid-package-sha256")
    _resolve_package_source("manifest.json", str(package.get("filename", "")))
    try:
        package_bytes = int(package.get("bytes"))
    except (TypeError, ValueError) as exc:
        raise UpdateBarrier("invalid-package-size") from exc
    if package_bytes <= 0 or package_bytes > MAX_BUNDLE_BYTES:
        raise UpdateBarrier("invalid-package-size")
    seen_archive: set[str] = set()
    seen_install: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise UpdateBarrier("invalid-file-entry")
        archive_path = PurePosixPath(str(entry.get("archive_path", "")))
        if (
            archive_path.is_absolute()
            or ".." in archive_path.parts
            or str(archive_path) in {"", "."}
        ):
            raise UpdateBarrier("unsafe-archive-path")
        install_path = _validated_install_path(str(entry.get("install_path", "")))
        digest = str(entry.get("sha256", ""))
        if not SHA256.fullmatch(digest):
            raise UpdateBarrier("invalid-file-sha256")
        try:
            mode = int(str(entry.get("mode", "")), 8)
        except ValueError as exc:
            raise UpdateBarrier("invalid-install-mode") from exc
        if mode < 0o400 or mode > 0o777 or mode & 0o022:
            raise UpdateBarrier("unsafe-install-mode")
        if str(archive_path) in seen_archive or str(install_path) in seen_install:
            raise UpdateBarrier("duplicate-update-file")
        seen_archive.add(str(archive_path))
        seen_install.add(str(install_path))
    return value


def _load_verified(
    manifest_source: str, expected_manifest_sha256: str
) -> tuple[dict[str, Any], bytes, str]:
    expected = expected_manifest_sha256.lower()
    if not SHA256.fullmatch(expected):
        raise UpdateBarrier("expected-manifest-sha256-required")
    manifest_bytes = _read_source(manifest_source, MAX_MANIFEST_BYTES)
    actual_manifest_sha = _sha256(manifest_bytes)
    if actual_manifest_sha != expected:
        raise UpdateBarrier("manifest-sha256-mismatch")
    try:
        manifest = _validate_manifest(json.loads(manifest_bytes.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateBarrier(f"manifest-json-invalid:{type(exc).__name__}") from exc
    package = manifest["package"]
    package_source = _resolve_package_source(manifest_source, package["filename"])
    bundle = _read_source(package_source, MAX_BUNDLE_BYTES)
    if _sha256(bundle) != package["sha256"]:
        raise UpdateBarrier("package-sha256-mismatch")
    if package.get("bytes") is not None and int(package["bytes"]) != len(bundle):
        raise UpdateBarrier("package-size-mismatch")
    return manifest, bundle, actual_manifest_sha


def _validated_files(manifest: dict[str, Any], bundle: bytes) -> dict[str, bytes]:
    expected = {entry["archive_path"]: entry for entry in manifest["files"]}
    result: dict[str, bytes] = {}
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    raise UpdateBarrier(f"archive-entry-not-regular-file:{member.name}")
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts or member.name not in expected:
                    raise UpdateBarrier(f"unexpected-archive-entry:{member.name}")
                if member.name in result:
                    raise UpdateBarrier(f"duplicate-archive-entry:{member.name}")
                total += member.size
                if total > MAX_EXPANDED_BYTES:
                    raise UpdateBarrier("expanded-update-too-large")
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise UpdateBarrier(f"archive-entry-unreadable:{member.name}")
                data = extracted.read(member.size + 1)
                if len(data) != member.size:
                    raise UpdateBarrier(f"archive-entry-size-mismatch:{member.name}")
                if _sha256(data) != expected[member.name]["sha256"]:
                    raise UpdateBarrier(f"file-sha256-mismatch:{member.name}")
                if member.name.endswith(".py"):
                    compile(data.decode("utf-8"), member.name, "exec")
                result[member.name] = data
    except (tarfile.TarError, UnicodeDecodeError, SyntaxError) as exc:
        raise UpdateBarrier(f"update-package-invalid:{type(exc).__name__}:{exc}") from exc
    if set(result) != set(expected):
        missing = sorted(set(expected) - set(result))
        raise UpdateBarrier("package-files-missing:" + ",".join(missing))
    return result


def inspect_update(manifest_source: str, expected_manifest_sha256: str) -> dict[str, Any]:
    manifest, bundle, manifest_sha = _load_verified(
        manifest_source, expected_manifest_sha256
    )
    files = _validated_files(manifest, bundle)
    return {
        "ok": True,
        "capability": "upgrade.inspect",
        "authorized": True,
        "verified": True,
        "target": manifest["target"],
        "version": manifest.get("version"),
        "manifest_sha256": manifest_sha,
        "package_sha256": manifest["package"]["sha256"],
        "files": sorted(files),
        "installed": False,
    }


def _target_path(root: Path, install_path: str) -> Path:
    safe = _validated_install_path(install_path)
    relative = Path(*safe.parts[1:])
    target = (root / relative).resolve()
    resolved_root = root.resolve()
    try:
        target.relative_to(resolved_root)
    except ValueError as exc:
        raise UpdateBarrier("resolved-install-path-outside-root") from exc
    return target


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.aurum-update")
    try:
        temporary.write_bytes(data)
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def apply_update(
    manifest_source: str,
    expected_manifest_sha256: str,
    *,
    confirmed: bool,
    install_root: Path | None = None,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    if not confirmed:
        raise UpdateBarrier("explicit-confirmation-required")
    root = install_root or Path(os.environ.get("AURUM_UPDATE_ROOT", "/"))
    update_state = state_dir or Path(
        os.environ.get("AURUM_UPDATE_STATE", "/var/lib/aurum-pi3/updates")
    )
    if (
        root.resolve() == Path("/").resolve()
        and hasattr(os, "geteuid")
        and os.geteuid() != 0
    ):
        raise UpdateBarrier("root-privileges-required")
    manifest, bundle, manifest_sha = _load_verified(
        manifest_source, expected_manifest_sha256
    )
    files = _validated_files(manifest, bundle)
    update_state.mkdir(parents=True, exist_ok=True)
    lock = update_state / "apply.lock"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as exc:
        try:
            if time.time() - lock.stat().st_mtime > 600:
                lock.rmdir()
                lock.mkdir(mode=0o700)
            else:
                raise UpdateBarrier("another-update-is-in-progress") from exc
        except OSError as lock_exc:
            raise UpdateBarrier("another-update-is-in-progress") from lock_exc
    backup_dir = update_state / "backups" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + manifest_sha[:12]
    )
    installed: list[tuple[Path, Path | None]] = []
    try:
        backup_dir.mkdir(parents=True, exist_ok=False)
        entries = {entry["archive_path"]: entry for entry in manifest["files"]}
        for archive_path, data in files.items():
            entry = entries[archive_path]
            target = _target_path(root, entry["install_path"])
            backup: Path | None = None
            if target.exists():
                backup = backup_dir / Path(*PurePosixPath(entry["install_path"]).parts[1:])
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
            mode = int(str(entry.get("mode", "755")), 8)
            _atomic_write(target, data, mode)
            installed.append((target, backup))
        record = {
            "schema": "aurum-pi3-update-state-v1",
            "applied_at": _utc_now(),
            "manifest_source": manifest_source,
            "manifest_sha256": manifest_sha,
            "package_sha256": manifest["package"]["sha256"],
            "version": manifest.get("version"),
            "files": [entry["install_path"] for entry in manifest["files"]],
            "backup": str(backup_dir),
        }
        _atomic_write(
            update_state / "last-applied.json",
            (json.dumps(record, indent=2, sort_keys=True) + "\n").encode(),
            0o600,
        )
    except Exception:
        for target, backup in reversed(installed):
            try:
                if backup is None:
                    target.unlink(missing_ok=True)
                else:
                    _atomic_write(target, backup.read_bytes(), backup.stat().st_mode & 0o777)
            except OSError:
                pass
        raise
    finally:
        try:
            lock.rmdir()
        except OSError:
            pass
    return {
        "ok": True,
        "capability": "upgrade.apply",
        "authorized": True,
        "verified": True,
        "installed": True,
        "version": manifest.get("version"),
        "manifest_sha256": manifest_sha,
        "backup": str(backup_dir),
        "restart_required": True,
        "next_command": "reboot confirm",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    for name in ("inspect", "apply"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("manifest_source")
        subparser.add_argument("manifest_sha256")
        if name == "apply":
            subparser.add_argument("confirmation", choices=["confirm"])
    args = parser.parse_args(argv)
    try:
        if args.operation == "inspect":
            result = inspect_update(args.manifest_source, args.manifest_sha256)
        else:
            result = apply_update(
                args.manifest_source, args.manifest_sha256, confirmed=True
            )
    except Exception as exc:
        result = {
            "ok": False,
            "capability": f"upgrade.{args.operation}",
            "barrier": {
                "scope": f"upgrade.{args.operation}",
                "reason": f"{type(exc).__name__}:{exc}",
            },
            "continuation_allowed": True,
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
