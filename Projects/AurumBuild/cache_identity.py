#!/usr/bin/env python3
"""Create fail-closed Aurum configuration and compiler-cache identities."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping


SCHEMA = "aurum-cache-identity-v1"


def hash_files(paths: Iterable[Path], *, root: Path | None = None) -> str:
    root = (root or Path.cwd()).resolve()
    digest = hashlib.sha256(b"AURUM-FILE-SET-V1\0")
    resolved: list[Path] = []
    for supplied in paths:
        path = supplied.resolve()
        if path.is_dir():
            resolved.extend(
                child
                for child in sorted(path.rglob("*"))
                if child.is_file() and not any(part.startswith(".") for part in child.parts)
            )
        elif path.is_file():
            resolved.append(path)
        else:
            raise ValueError(f"cache identity path does not exist: {supplied}")
    for path in sorted(set(resolved)):
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = path.as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
        digest.update(b"\0")
    return digest.hexdigest()


def cache_identity(
    *,
    source_hash: str,
    architecture: str,
    toolchain: str,
    build_config_hash: str,
    dependency_manifest_hash: str,
    builder_image_digest: str,
) -> dict[str, str]:
    values = {
        "schema": SCHEMA,
        "source_hash": source_hash,
        "architecture": architecture,
        "toolchain": toolchain,
        "build_config_hash": build_config_hash,
        "dependency_manifest_hash": dependency_manifest_hash,
        "builder_image_digest": builder_image_digest,
    }
    payload = json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")
    values["key"] = "aurum-ccache-v1-" + hashlib.sha256(payload).hexdigest()
    return values


def cache_matches(expected: Mapping[str, str], observed: Mapping[str, str]) -> bool:
    required = {
        "schema",
        "source_hash",
        "architecture",
        "toolchain",
        "build_config_hash",
        "dependency_manifest_hash",
        "builder_image_digest",
        "key",
    }
    return required.issubset(expected) and all(expected[name] == observed.get(name) for name in required)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    file_hash = commands.add_parser("hash-files")
    file_hash.add_argument("paths", type=Path, nargs="+")
    identity = commands.add_parser("cache-key")
    identity.add_argument("--source-hash", required=True)
    identity.add_argument("--architecture", required=True)
    identity.add_argument("--toolchain", required=True)
    identity.add_argument("--build-config-hash", required=True)
    identity.add_argument("--dependency-manifest-hash", required=True)
    identity.add_argument("--builder-image-digest", required=True)
    args = parser.parse_args()
    if args.command == "hash-files":
        print(hash_files(args.paths))
        return 0
    print(
        json.dumps(
            cache_identity(
                source_hash=args.source_hash,
                architecture=args.architecture,
                toolchain=args.toolchain,
                build_config_hash=args.build_config_hash,
                dependency_manifest_hash=args.dependency_manifest_hash,
                builder_image_digest=args.builder_image_digest,
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
