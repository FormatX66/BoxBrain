#!/usr/bin/env python3
"""Build a byte-for-byte deterministic selected-source verification bundle."""

from __future__ import annotations

import argparse
import gzip
import io
import tarfile
from pathlib import Path


def build_bundle(output: Path, roots: list[Path]) -> None:
    repository = Path.cwd().resolve()
    files: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved.is_file():
            files.append(resolved)
        elif resolved.is_dir():
            files.extend(
                path
                for path in sorted(resolved.rglob("*"))
                if path.is_file() and not any(part.startswith(".") for part in path.parts)
            )
        else:
            raise ValueError(f"bundle input does not exist: {root}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for path in sorted(set(files)):
                    relative = path.relative_to(repository).as_posix()
                    data = path.read_bytes()
                    info = tarfile.TarInfo(relative)
                    info.size = len(data)
                    info.mtime = 0
                    info.uid = 0
                    info.gid = 0
                    info.uname = "root"
                    info.gname = "root"
                    info.mode = 0o755 if path.suffix in {".sh", ".py"} else 0o644
                    archive.addfile(info, io.BytesIO(data))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("roots", type=Path, nargs="+")
    args = parser.parse_args()
    build_bundle(args.output, args.roots)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
