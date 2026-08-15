#!/usr/bin/env python3
"""Build a complete, pinned Aurum Pi3 application/runtime release artifact."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from aurum_release_gate import (
    GateValidationError,
    canonical_sha256,
    validate_convergence_proof,
)

NUMERIC_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){0,3}$")
SAFE_RELEASE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_revision(repository: Path, *, short: bool = True) -> str:
    try:
        command = ["git", "rev-parse"]
        if short:
            command.append("--short=12")
        command.append("HEAD")
        result = subprocess.run(
            command,
            cwd=repository,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        value = result.stdout.strip().lower()
    except (OSError, subprocess.SubprocessError):
        value = "local" if short else ""
    fallback = "local" if short else ""
    return value if value.replace("-", "").isalnum() else fallback


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    if info.isdir():
        info.mode = 0o755
    elif info.name.endswith(("aurum_pi3_console.py", "aurum_updater.py")):
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
    convergence_proof: Path,
) -> tuple[Path, Path, Path]:
    pi_dir = repository / "Projects" / "AurumPi3"
    codelation = repository / "Projects" / "Codelation"
    required_runtime = (
        "aurum_pi3_console.py",
        "aurum_updater.py",
        "aurum_release_gate.py",
    )
    if any(not (pi_dir / name).is_file() for name in required_runtime) or not codelation.is_dir():
        raise SystemExit("Aurum Pi3 console or Codelation source is missing")
    if not NUMERIC_VERSION.fullmatch(version):
        raise SystemExit("version must contain one to four numeric components")
    if not SAFE_RELEASE.fullmatch(release_id):
        raise SystemExit("release-id must be 1-96 safe filename characters")

    source_commit = source_revision(repository, short=False)
    try:
        proof_value = json.loads(convergence_proof.read_text(encoding="utf-8"))
        proof = validate_convergence_proof(proof_value, source_commit)
    except (OSError, json.JSONDecodeError, GateValidationError) as exc:
        raise SystemExit(f"A verified same-commit convergence proof is required: {exc}") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    artifact = output_dir / f"Aurum-Pi3-runtime-{release_id}-arm64.tar.gz"
    manifest_path = output_dir / f"Aurum-Pi3-runtime-{release_id}-arm64.manifest.json"
    pin_path = manifest_path.with_suffix(manifest_path.suffix + ".sha256")

    with tempfile.TemporaryDirectory(prefix="aurum-runtime-") as temporary_name:
        temporary = Path(temporary_name)
        payload = temporary / "payload"
        payload.mkdir()
        for name in required_runtime:
            shutil.copy2(pi_dir / name, payload / name)
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
            "source_commit": source_commit,
            "capabilities": [
                "capabilities",
                "observe",
                "rescan",
                "network",
                "storage",
                "usb",
                "processes",
                "health",
                "services",
                "frontier",
                "json",
            ],
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
        "source_commit": source_commit,
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
        "capabilities": release["capabilities"],
        "verification": {
            "convergence": proof,
            "convergence_sha256": canonical_sha256(proof),
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
    parser.add_argument(
        "--version",
        default=(script_dir / "RUNTIME_VERSION").read_text(encoding="ascii").strip(),
    )
    parser.add_argument("--release-id")
    parser.add_argument("--artifact-url")
    parser.add_argument("--convergence-proof", type=Path, required=True)
    args = parser.parse_args()
    revision = source_revision(args.repository)
    release_id = args.release_id or f"{args.version}-{revision}"
    outputs = build_release(
        args.repository,
        args.output_dir,
        args.version,
        release_id,
        args.artifact_url,
        args.convergence_proof,
    )
    print(json.dumps({"artifact": str(outputs[0]), "manifest": str(outputs[1]), "pin": str(outputs[2])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
