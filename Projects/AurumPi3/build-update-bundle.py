#!/usr/bin/env python3
"""Build a deterministic, integrity-described Aurum Pi3 capability update."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path

SCHEMA = "aurum-pi3-update-v1"
TARGET = "raspberry-pi-3"
SOURCES = (
    ("aurum_pi3_console.py", "/opt/aurum/aurum_pi3_console.py", "755"),
    ("aurum_pi3_update.py", "/opt/aurum/aurum_pi3_update.py", "755"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(script_dir: Path, output_dir: Path) -> tuple[Path, Path, Path]:
    console = (script_dir / "aurum_pi3_console.py").read_text(encoding="utf-8")
    match = re.search(r'^VERSION = "([^"]+)"$', console, re.MULTILINE)
    if not match:
        raise RuntimeError("Aurum Pi3 VERSION not found")
    version = match.group(1)
    stem = f"Aurum-Pi3-v{version}-capability-update"
    bundle_path = output_dir / f"{stem}.tar.gz"
    manifest_path = output_dir / f"{stem}.manifest.json"
    digest_path = output_dir / f"{stem}.manifest.json.sha256"
    output_dir.mkdir(parents=True, exist_ok=True)

    with bundle_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for filename, install_path, mode in SOURCES:
                    source = script_dir / filename
                    data = source.read_bytes()
                    info = tarfile.TarInfo(install_path.lstrip("/"))
                    info.size = len(data)
                    info.mode = int(mode, 8)
                    info.uid = 0
                    info.gid = 0
                    info.uname = "root"
                    info.gname = "root"
                    info.mtime = 0
                    archive.addfile(info, io.BytesIO(data))

    files = []
    for filename, install_path, mode in SOURCES:
        source = script_dir / filename
        files.append(
            {
                "archive_path": install_path.lstrip("/"),
                "install_path": install_path,
                "sha256": sha256(source),
                "mode": mode,
            }
        )
    manifest = {
        "schema": SCHEMA,
        "target": TARGET,
        "version": version,
        "package": {
            "filename": bundle_path.name,
            "sha256": sha256(bundle_path),
            "bytes": bundle_path.stat().st_size,
        },
        "files": files,
        "activation": {"restart_required": True, "command": "reboot confirm"},
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    digest_path.write_text(
        f"{sha256(manifest_path)}  {manifest_path.name}\n", encoding="utf-8"
    )
    return bundle_path, manifest_path, digest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    script_dir = Path(__file__).resolve().parent
    output_dir = args.output or script_dir.parents[1] / "dist"
    for path in build(script_dir, output_dir):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
