#!/usr/bin/env python3
"""Build a complete, pinned Aurum Pi3 application/runtime release artifact."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_revision(repository: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=repository,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        value = result.stdout.strip().lower()
    except (OSError, subprocess.SubprocessError):
        value = "local"
    return value if value.replace("-", "").isalnum() else "local"


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    if info.isdir():
        info.mode = 0o755
    elif info.name.endswith("aurum_pi3_console.py"):
        info.mode = 0o755
    else:
        info.mode = 0o644
    return info


def build_release(
    repository: Path,
    output_dir: Path,
    version: str,
    release_id: str,
    artifact_url: str | None,
) -> tuple[Path, Path, Path]:
    pi_dir = repository / "Projects" / "AurumPi3"
    codelation = repository / "Projects" / "Codelation"
    if not (pi_dir / "aurum_pi3_console.py").is_file() or not codelation.is_dir():
        raise SystemExit("Aurum Pi3 console or Codelation source is missing")
    if not release_id or not all(character.isalnum() or character in "._-" for character in release_id):
        raise SystemExit("release-id must contain only letters, digits, dot, underscore, and hyphen")

    output_dir.mkdir(parents=True, exist_ok=True)
    artifact = output_dir / f"Aurum-Pi3-runtime-{release_id}-arm64.tar.gz"
    manifest_path = output_dir / f"Aurum-Pi3-runtime-{release_id}-arm64.manifest.json"
    pin_path = manifest_path.with_suffix(manifest_path.suffix + ".sha256")

    with tempfile.TemporaryDirectory(prefix="aurum-runtime-") as temporary_name:
        temporary = Path(temporary_name)
        payload = temporary / "payload"
        payload.mkdir()
        shutil.copy2(pi_dir / "aurum_pi3_console.py", payload / "aurum_pi3_console.py")
        shutil.copytree(
            codelation,
            payload / "codelation",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )
        release = {
            "schema": "aurum-runtime-release-v1",
            "version": version,
            "release_id": release_id,
            "target": "raspberry-pi-3",
            "architecture": "arm64",
            "application_layer_only": True,
            "includes_boot_firmware": False,
            "includes_kernel": False,
        }
        (payload / "RELEASE.json").write_text(
            json.dumps(release, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        with artifact.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                    archive.add(payload, arcname="payload", recursive=True, filter=_tar_filter)

    artifact_sha = sha256_file(artifact)
    manifest = {
        "schema": "aurum-application-update-v1",
        "version": version,
        "release_id": release_id,
        "target": "raspberry-pi-3",
        "architecture": "arm64",
        "minimum_updater_version": "1.0.0",
        "artifact": {
            "url": artifact_url or artifact.name,
            "sha256": artifact_sha,
            "bytes": artifact.stat().st_size,
            "format": "tar.gz",
            "root": "payload",
        },
        "scope": {
            "application_runtime": True,
            "boot_firmware": False,
            "kernel": False,
            "operating_system": False,
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pin_path.write_text(f"{sha256_file(manifest_path)}  {manifest_path.name}\n", encoding="ascii")
    return artifact, manifest_path, pin_path


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    repository = script_dir.parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=repository)
    parser.add_argument("--output-dir", type=Path, default=repository / "dist")
    parser.add_argument("--version", default="0.02")
    parser.add_argument("--release-id")
    parser.add_argument("--artifact-url")
    args = parser.parse_args()
    revision = source_revision(args.repository)
    release_id = args.release_id or f"{args.version}-{revision}"
    outputs = build_release(args.repository, args.output_dir, args.version, release_id, args.artifact_url)
    print(json.dumps({"artifact": str(outputs[0]), "manifest": str(outputs[1]), "pin": str(outputs[2])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
