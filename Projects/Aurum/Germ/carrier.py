#!/usr/bin/env python3
"""Verified offline phenotype carrier for Aurum Tiny Seed.

The carrier is a secondary recovery source for the exact failure where the
protected germ is healthy but GitHub cannot be reached.  It contains one
immutable genetics snapshot and one pinned platform snapshot.  Every regular
file is covered by a deterministic tree digest before the carrier may grow an
inactive slot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA = "aurum-offline-phenotype-carrier-v1"
MANIFEST_RELATIVE = Path("Projects/Aurum/Germ/GENETICS.json")
SHA40 = re.compile(r"[0-9a-f]{40}")


class CarrierError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CarrierError(f"carrier metadata is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise CarrierError("carrier metadata must be a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        raise CarrierError(f"carrier tree is missing: {root}")
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise CarrierError(f"carrier tree contains a symlink: {path.relative_to(root)}")
        if path.is_file():
            yield path


def tree_digest(root: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    size = 0
    for path in _files(root):
        relative = path.relative_to(root).as_posix()
        file_digest = _sha256(path)
        file_size = path.stat().st_size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(file_size).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\n")
        count += 1
        size += file_size
    if count == 0:
        raise CarrierError(f"carrier tree is empty: {root}")
    return {"sha256": digest.hexdigest(), "files": count, "bytes": size}


def _copy_path(source_root: Path, relative: str, destination_root: Path) -> None:
    source = source_root / relative
    destination = destination_root / relative
    if source.is_symlink() or not source.exists():
        raise CarrierError(f"required carrier source is missing or unsafe: {relative}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(
            source,
            destination,
            dirs_exist_ok=True,
            symlinks=False,
            ignore=shutil.ignore_patterns(".git", ".build*", "__pycache__", "*.pyc"),
        )
    elif source.is_file():
        shutil.copy2(source, destination)
    else:
        raise CarrierError(f"required carrier source is not a regular path: {relative}")


def prepare(
    *,
    genetics_root: Path,
    platform_root: Path,
    output: Path,
    genetics_commit: str,
    platform_commit: str,
    architecture: str = "x86_64",
) -> dict[str, Any]:
    genetics_commit = genetics_commit.lower()
    platform_commit = platform_commit.lower()
    if not SHA40.fullmatch(genetics_commit) or not SHA40.fullmatch(platform_commit):
        raise CarrierError("carrier commits must be immutable 40-character SHA values")

    manifest = _json(genetics_root / MANIFEST_RELATIVE)
    if manifest.get("schema") != "aurum-genetics-v1":
        raise CarrierError("offline carrier requires aurum-genetics-v1")
    required = manifest.get("required_paths")
    if not isinstance(required, list) or not required or not all(isinstance(item, str) and item for item in required):
        raise CarrierError("genetics required_paths are invalid")
    adapter = (manifest.get("platforms") or {}).get(architecture)
    if not isinstance(adapter, dict):
        raise CarrierError(f"genetics do not declare the {architecture} platform")
    offline = adapter.get("offline_carrier")
    if not isinstance(offline, dict) or offline.get("enabled") is not True:
        raise CarrierError("offline carrier is not enabled by genetics policy")
    if offline.get("pinned_commit") != platform_commit:
        raise CarrierError("platform source does not match the pinned offline carrier commit")

    if output.exists():
        shutil.rmtree(output)
    genetics_destination = output / "genetics"
    platform_destination = output / "platform"
    genetics_destination.mkdir(parents=True)
    platform_destination.mkdir(parents=True)

    for relative in required:
        _copy_path(genetics_root, relative, genetics_destination)
    for relative in (str(adapter.get("runtime_root") or ""), str(adapter.get("codelation_root") or "")):
        if not relative:
            raise CarrierError("platform runtime source paths are missing")
        _copy_path(platform_root, relative, platform_destination)

    genetics_tree = tree_digest(genetics_destination)
    platform_tree = tree_digest(platform_destination)
    payload = {
        "schema": SCHEMA,
        "architecture": architecture,
        "repository": manifest.get("repository"),
        "genetics_commit": genetics_commit,
        "genetics_ref": manifest.get("default_trusted_ref"),
        "platform_commit": platform_commit,
        "platform_source_ref": adapter.get("source_ref"),
        "genetics_manifest_sha256": _sha256(genetics_destination / MANIFEST_RELATIVE),
        "genetics_tree": genetics_tree,
        "platform_tree": platform_tree,
        "purpose": "offline-emergency-inactive-slot-candidate",
        "live_overwrite_allowed": False,
        "promotion_requires_guardian_health": True,
    }
    metadata = output / "carrier.json"
    metadata.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(metadata, 0o644)
    return verify(output)


def verify(root: Path, *, architecture: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    payload = _json(root / "carrier.json")
    if payload.get("schema") != SCHEMA:
        raise CarrierError(f"unsupported offline carrier schema: {payload.get('schema')!r}")
    carrier_architecture = str(payload.get("architecture") or "")
    if architecture and carrier_architecture != architecture:
        raise CarrierError(
            f"offline carrier architecture {carrier_architecture!r} does not match {architecture!r}"
        )
    for key in ("genetics_commit", "platform_commit"):
        if not SHA40.fullmatch(str(payload.get(key) or "")):
            raise CarrierError(f"offline carrier has an invalid {key}")
    if payload.get("live_overwrite_allowed") is not False:
        raise CarrierError("offline carrier does not prohibit live overwrite")
    if payload.get("promotion_requires_guardian_health") is not True:
        raise CarrierError("offline carrier does not require Guardian health promotion")

    genetics_root = root / "genetics"
    platform_root = root / "platform"
    manifest_path = genetics_root / MANIFEST_RELATIVE
    manifest = _json(manifest_path)
    if manifest.get("schema") != "aurum-genetics-v1":
        raise CarrierError("offline carrier genetics manifest is incompatible")
    if manifest.get("repository") != payload.get("repository"):
        raise CarrierError("offline carrier repository identity is inconsistent")
    if _sha256(manifest_path) != payload.get("genetics_manifest_sha256"):
        raise CarrierError("offline carrier genetics manifest digest does not match")
    required = manifest.get("required_paths") or []
    missing = [str(relative) for relative in required if not (genetics_root / str(relative)).exists()]
    if missing:
        raise CarrierError("offline carrier genetics are incomplete: " + ", ".join(missing))
    adapter = (manifest.get("platforms") or {}).get(carrier_architecture)
    if not isinstance(adapter, dict):
        raise CarrierError("offline carrier platform adapter is missing")
    offline = adapter.get("offline_carrier")
    if not isinstance(offline, dict) or offline.get("pinned_commit") != payload.get("platform_commit"):
        raise CarrierError("offline carrier platform commit is outside genetics policy")
    if adapter.get("source_ref") != payload.get("platform_source_ref"):
        raise CarrierError("offline carrier platform ref is inconsistent")
    for relative in (str(adapter.get("runtime_root") or ""), str(adapter.get("codelation_root") or "")):
        if not relative or not (platform_root / relative).is_dir():
            raise CarrierError(f"offline carrier platform source is incomplete: {relative!r}")

    genetics_tree = tree_digest(genetics_root)
    platform_tree = tree_digest(platform_root)
    if genetics_tree != payload.get("genetics_tree"):
        raise CarrierError("offline carrier genetics tree digest does not match")
    if platform_tree != payload.get("platform_tree"):
        raise CarrierError("offline carrier platform tree digest does not match")
    return {
        **payload,
        "status": "verified",
        "root": str(root),
        "genetics_root": str(genetics_root),
        "platform_root": str(platform_root),
        "manifest": manifest,
    }


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Build or verify an Aurum offline phenotype carrier")
    subparsers = command.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--genetics-root", type=Path, required=True)
    build.add_argument("--platform-root", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--genetics-commit", required=True)
    build.add_argument("--platform-commit", required=True)
    build.add_argument("--architecture", default="x86_64")
    check = subparsers.add_parser("verify")
    check.add_argument("--root", type=Path, required=True)
    check.add_argument("--architecture")
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "build":
            result = prepare(
                genetics_root=args.genetics_root,
                platform_root=args.platform_root,
                output=args.output,
                genetics_commit=args.genetics_commit,
                platform_commit=args.platform_commit,
                architecture=args.architecture,
            )
        else:
            result = verify(args.root, architecture=args.architecture)
    except CarrierError as exc:
        print(json.dumps({"status": "refused", "detail": str(exc)}, indent=2, sort_keys=True))
        return 2
    result = {key: value for key, value in result.items() if key != "manifest"}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
