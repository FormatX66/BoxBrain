#!/usr/bin/env python3
"""Create and verify an exact tracked-file manifest for remote source transfer."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


SCHEMA = "aurum-source-identity-v1"


def create_manifest(repository: Path, source_sha: str) -> dict:
    repository = repository.resolve()
    exact = subprocess.check_output(
        ["git", "rev-parse", "--verify", f"{source_sha}^{{commit}}"], cwd=repository, text=True
    ).strip()
    if exact != source_sha:
        raise ValueError(f"source SHA is not exact: expected={source_sha} observed={exact}")
    if subprocess.run(["git", "diff", "--quiet", source_sha, "--"], cwd=repository).returncode:
        raise ValueError("tracked working tree differs from the exact source SHA")
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=repository).split(b"\0")
    files = {}
    for raw in paths:
        if not raw:
            continue
        relative = raw.decode("utf-8")
        path = repository / relative
        if not path.is_file():
            raise ValueError(f"tracked source is missing: {relative}")
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"schema": SCHEMA, "source_sha": source_sha, "files": files}


def verify_manifest(repository: Path, manifest: dict, expected_source_sha: str) -> None:
    if manifest.get("schema") != SCHEMA:
        raise ValueError("unsupported source identity schema")
    if manifest.get("source_sha") != expected_source_sha:
        raise ValueError("transferred source SHA mismatch")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("source identity contains no tracked files")
    repository = repository.resolve()
    for relative, expected in sorted(files.items()):
        path = (repository / relative).resolve()
        if repository not in path.parents or not path.is_file():
            raise ValueError(f"source identity path is missing or unsafe: {relative}")
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != expected:
            raise ValueError(f"transferred source content mismatch: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--repository", type=Path, default=Path.cwd())
    create.add_argument("--source-sha", required=True)
    create.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--repository", type=Path, default=Path.cwd())
    verify.add_argument("--expected-source-sha", required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "create":
        value = create_manifest(args.repository, args.source_sha)
        args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        value = json.loads(args.manifest.read_text(encoding="utf-8"))
        verify_manifest(args.repository, value, args.expected_source_sha)
    print("AURUM_SOURCE_IDENTITY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
