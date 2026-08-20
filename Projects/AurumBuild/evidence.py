#!/usr/bin/env python3
"""Record and converge exact cross-provider Aurum build evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "aurum-distributed-build-evidence-v1"
SHA_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
AUTHORITIES = frozenset({"BUILD-ONLY", "VERIFY-ONLY", "PHYSICAL-EVIDENCE", "PROMOTION"})
EXTERNAL_PROVIDERS = frozenset({"circleci-verifier", "gcp-burst", "oci-arm", "contributor-fork"})


class EvidenceError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_evidence(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("schema") != SCHEMA:
        raise EvidenceError("unsupported evidence schema")
    source_sha = str(value.get("source_sha", "")).lower()
    if not SHA_RE.fullmatch(source_sha):
        raise EvidenceError("source_sha must be an exact 40- or 64-character commit identity")
    artifact_sha = str(value.get("artifact_sha256", "")).lower()
    config_hash = str(value.get("build_config_hash", "")).lower()
    builder_digest = str(value.get("builder_image_digest", "")).lower()
    if not SHA256_RE.fullmatch(artifact_sha):
        raise EvidenceError("artifact_sha256 is invalid")
    if not SHA256_RE.fullmatch(config_hash):
        raise EvidenceError("build_config_hash is invalid")
    if not DIGEST_RE.fullmatch(builder_digest):
        raise EvidenceError("builder_image_digest must be immutable sha256 evidence")
    authority = str(value.get("authority_level", ""))
    provider = str(value.get("provider", ""))
    if authority not in AUTHORITIES:
        raise EvidenceError("authority_level is invalid")
    if authority == "PROMOTION" and provider != "aurum-convergence":
        raise EvidenceError("only Aurum convergence may hold PROMOTION authority")
    if provider in EXTERNAL_PROVIDERS and authority == "PROMOTION":
        raise EvidenceError("external providers cannot promote")
    if value.get("verification_result") not in {"passed", "failed"}:
        raise EvidenceError("verification_result must be passed or failed")
    for field in ("architecture", "provider", "lane_identity", "timestamp"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise EvidenceError(f"{field} is required")
    return value


def evidence_document(
    *,
    source_sha: str,
    architecture: str,
    builder_image_digest: str,
    build_config_hash: str,
    artifact_sha256: str,
    provider: str,
    lane_identity: str,
    verification_result: str,
    authority_level: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    value = {
        "schema": SCHEMA,
        "source_sha": source_sha.lower(),
        "architecture": architecture,
        "builder_image_digest": builder_image_digest.lower(),
        "build_config_hash": build_config_hash.lower(),
        "artifact_sha256": artifact_sha256.lower(),
        "provider": provider,
        "lane_identity": lane_identity,
        "verification_result": verification_result,
        "timestamp": timestamp or _timestamp(),
        "authority_level": authority_level,
    }
    return validate_evidence(value)


def converge_evidence(
    evidence: Iterable[dict[str, Any]],
    *,
    expected_source_sha: str,
    expected_artifact_sha256: str,
    minimum_verifiers: int = 2,
) -> dict[str, Any]:
    items = [validate_evidence(dict(item)) for item in evidence]
    if not items:
        raise EvidenceError("convergence requires evidence")
    if not SHA_RE.fullmatch(expected_source_sha.lower()):
        raise EvidenceError("expected source identity is invalid")
    if not SHA256_RE.fullmatch(expected_artifact_sha256.lower()):
        raise EvidenceError("expected artifact identity is invalid")
    for item in items:
        if item["source_sha"] != expected_source_sha.lower():
            raise EvidenceError("source SHA mismatch")
        if item["artifact_sha256"] != expected_artifact_sha256.lower():
            raise EvidenceError("artifact hash mismatch")
        if item["verification_result"] != "passed":
            raise EvidenceError("failed evidence cannot converge")
        if item["authority_level"] == "PROMOTION":
            raise EvidenceError("promotion evidence cannot be an input to convergence")
    builders = [item for item in items if item["authority_level"] == "BUILD-ONLY"]
    verifiers = [item for item in items if item["authority_level"] == "VERIFY-ONLY"]
    if not builders:
        raise EvidenceError("convergence requires BUILD-ONLY artifact evidence")
    verifier_lanes = {(item["provider"], item["lane_identity"]) for item in verifiers}
    if len(verifier_lanes) < minimum_verifiers:
        raise EvidenceError("mandatory independent verifier lanes are missing")
    builder_digests = {item["builder_image_digest"] for item in items}
    config_hashes = {item["build_config_hash"] for item in items}
    architectures = {item["architecture"] for item in items}
    if len(builder_digests) != 1 or len(config_hashes) != 1 or len(architectures) != 1:
        raise EvidenceError("build identity diverged across evidence")
    output = evidence_document(
        source_sha=expected_source_sha,
        architecture=architectures.pop(),
        builder_image_digest=builder_digests.pop(),
        build_config_hash=config_hashes.pop(),
        artifact_sha256=expected_artifact_sha256,
        provider="aurum-convergence",
        lane_identity="single-verified-promotion-path",
        verification_result="passed",
        authority_level="PROMOTION",
    )
    output["verified_lanes"] = sorted(f"{provider}:{lane}" for provider, lane in verifier_lanes)
    return output


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"could not read evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"evidence {path} is not an object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record")
    record.add_argument("--source-sha", required=True)
    record.add_argument("--architecture", required=True)
    record.add_argument("--builder-image-digest", required=True)
    record.add_argument("--build-config-hash", required=True)
    record.add_argument("--artifact", type=Path, required=True)
    record.add_argument("--provider", required=True)
    record.add_argument("--lane", required=True)
    record.add_argument("--result", choices=("passed", "failed"), required=True)
    record.add_argument("--authority", choices=sorted(AUTHORITIES), required=True)
    record.add_argument("--output", type=Path, required=True)
    converge = commands.add_parser("converge")
    converge.add_argument("--expected-source", required=True)
    converge.add_argument("--expected-artifact-sha256", required=True)
    converge.add_argument("--minimum-verifiers", type=int, default=2)
    converge.add_argument("--output", type=Path, required=True)
    converge.add_argument("evidence", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        if args.command == "record":
            value = evidence_document(
                source_sha=args.source_sha,
                architecture=args.architecture,
                builder_image_digest=args.builder_image_digest,
                build_config_hash=args.build_config_hash,
                artifact_sha256=sha256_file(args.artifact),
                provider=args.provider,
                lane_identity=args.lane,
                verification_result=args.result,
                authority_level=args.authority,
            )
        else:
            value = converge_evidence(
                (_read(path) for path in args.evidence),
                expected_source_sha=args.expected_source,
                expected_artifact_sha256=args.expected_artifact_sha256,
                minimum_verifiers=args.minimum_verifiers,
            )
        _write(args.output, value)
        print(
            "AURUM_DISTRIBUTED_EVIDENCE_OK "
            f"provider={value['provider']} authority={value['authority_level']} "
            f"source_sha={value['source_sha']} artifact_sha256={value['artifact_sha256']}"
        )
        return 0
    except EvidenceError as exc:
        print(f"AURUM_DISTRIBUTED_EVIDENCE_FAILED reason={exc}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
