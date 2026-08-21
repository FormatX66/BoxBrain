#!/usr/bin/env python3
"""Content identities, evidence records, and fail-closed Aurum promotion gates."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BUILDER_INFRASTRUCTURE_PATHS = (
    ".github/workflows/aurum-builder.yml",
    "Projects/AurumBuild/Dockerfile.builder",
    "Projects/AurumBuild/packages.builder.txt",
    "Projects/AurumBuild/verify-builder.sh",
)
BUILD_CONFIGURATION_PATHS = (
    "Projects/AurumPC/build-iso.sh",
    "Projects/AurumPC/pc01_autonomy_policy.json",
)
DEPENDENCY_DEFINITION_PATHS = (
    "Projects/AurumBuild/Dockerfile.builder",
    "Projects/AurumBuild/packages.builder.txt",
)
MANDATORY_VM_PROFILES = {
    "generic-uefi-install": {
        "architecture": "x86_64",
        "execution_environments": ("qemu-uefi-kvm", "qemu-uefi-tcg"),
    },
    "hopper-hp-topology-twin": {
        "architecture": "x86_64",
        "execution_environments": ("qemu-uefi-kvm", "qemu-uefi-tcg"),
    },
}
OPTIMIZATION_ORDER = (
    "correctness",
    "safety",
    "user_intent",
    "verification_strength",
    "latency_seconds",
    "compute_units",
    "cost_units",
)
_DIGEST_REFERENCE = re.compile(r"^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$")
_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_text(value: Any, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field} must not be empty")
    return text


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _github_outputs(path: Path | None, values: Mapping[str, Any]) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            else:
                rendered = str(value)
            if "\n" in rendered:
                raise ValueError(f"GitHub output {key} contains a newline")
            handle.write(f"{key}={rendered}\n")


def hash_paths(root: Path, relative_paths: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(set(relative_paths)):
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(f"identity input is missing: {relative}")
        payload = path.read_bytes()
        encoded_name = relative.replace("\\", "/").encode("utf-8")
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def builder_revision(root: Path = REPOSITORY_ROOT) -> str:
    command = ["git", "log", "-1", "--format=%H", "--", *BUILDER_INFRASTRUCTURE_PATHS]
    revision = subprocess.check_output(command, cwd=root, text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", revision):
        raise ValueError("builder infrastructure has no valid Git revision")
    return revision


def compute_identities(
    *,
    root: Path,
    source_sha: str,
    architecture: str,
    builder_image: str,
) -> dict[str, Any]:
    source_sha = _require_text(source_sha, "source_sha")
    architecture = _require_text(architecture, "architecture")
    builder_image = _require_text(builder_image, "builder_image").casefold()
    if not re.fullmatch(r"[0-9a-f]{40,64}", source_sha):
        raise ValueError("source_sha must be a full Git object identity")
    if not _DIGEST_REFERENCE.fullmatch(builder_image):
        raise ValueError("builder_image must be an immutable GHCR @sha256 reference")

    build_configuration = hash_paths(root, BUILD_CONFIGURATION_PATHS)
    dependency_definition = hash_paths(root, DEPENDENCY_DEFINITION_PATHS)
    artifact_inputs = {
        "source_sha": source_sha,
        "architecture": architecture,
        "builder_image": builder_image,
        "build_configuration_sha256": build_configuration,
        "dependency_definition_sha256": dependency_definition,
    }
    package_cache_inputs = {
        "architecture": architecture,
        "builder_image": builder_image,
        "build_configuration_sha256": build_configuration,
        "dependency_definition_sha256": dependency_definition,
        "cache_scope": "live-build-bootstrap-and-packages",
    }
    return {
        "schema": "aurum-build-identity-v1",
        **artifact_inputs,
        "artifact_identity": _canonical_digest(artifact_inputs),
        "live_build_cache_identity": _canonical_digest(package_cache_inputs),
        "live_build_cache_inputs": package_cache_inputs,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_artifact_manifest(
    *,
    identity: Mapping[str, Any],
    iso_path: Path,
    cache_hit: bool,
    pipeline_started_epoch: int,
    validation_seconds: float,
    builder_pull_seconds: float,
    container_start_seconds: float,
    iso_build_seconds: float,
) -> dict[str, Any]:
    if identity.get("schema") != "aurum-build-identity-v1":
        raise ValueError("unsupported build identity")
    if not iso_path.is_file() or iso_path.stat().st_size <= 0:
        raise ValueError("Aurum ISO is missing or empty")
    iso_sha256 = _sha256_file(iso_path)
    sidecar = iso_path.with_name(iso_path.name + ".sha256")
    if not sidecar.is_file() or sidecar.read_text(encoding="utf-8").split()[0] != iso_sha256:
        raise ValueError("ISO SHA-256 sidecar does not match the actual image")
    return {
        "schema": "aurum-pc-artifact-v1",
        "artifact_identity": identity["artifact_identity"],
        "source_sha": identity["source_sha"],
        "architecture": identity["architecture"],
        "builder_image": identity["builder_image"],
        "build_configuration_sha256": identity["build_configuration_sha256"],
        "dependency_definition_sha256": identity["dependency_definition_sha256"],
        "live_build_cache_identity": identity["live_build_cache_identity"],
        "iso_name": iso_path.name,
        "iso_sha256": iso_sha256,
        "cache": {
            "kind": "live-build-bootstrap-and-packages",
            "hit": bool(cache_hit),
            "compatibility_proven_by": identity["live_build_cache_identity"],
        },
        "timing": {
            "pipeline_started_epoch": int(pipeline_started_epoch),
            "validation_seconds": round(float(validation_seconds), 3),
            "builder_pull_seconds": round(float(builder_pull_seconds), 3),
            "container_start_seconds": round(float(container_start_seconds), 3),
            "iso_build_seconds": round(float(iso_build_seconds), 3),
        },
        "promotion_state": "unverified",
    }


def create_verification_evidence(
    *,
    artifact: Mapping[str, Any],
    profile: str,
    log_path: Path,
    required_markers: Sequence[str],
    duration_seconds: float,
    execution_environment: str,
) -> dict[str, Any]:
    specification = MANDATORY_VM_PROFILES.get(profile)
    if specification is None:
        raise ValueError(f"unsupported mandatory VM profile: {profile}")
    execution_environment = _require_text(execution_environment, "execution_environment")
    if execution_environment not in specification["execution_environments"]:
        raise ValueError(
            f"unsupported execution environment for {profile}: {execution_environment}"
        )
    log = log_path.read_text(encoding="utf-8", errors="replace")
    missing = [marker for marker in required_markers if marker not in log]
    if missing:
        raise ValueError(f"verification log is missing markers: {missing}")
    return {
        "schema": "aurum-pc-verification-v1",
        "profile": profile,
        "work_type": "vm-topology-verification",
        "architecture": specification["architecture"],
        "execution_environment": execution_environment,
        "source_sha": artifact["source_sha"],
        "artifact_identity": artifact["artifact_identity"],
        "iso_sha256": artifact["iso_sha256"],
        "builder_image": artifact["builder_image"],
        "verified": True,
        "required_markers": list(required_markers),
        "duration_seconds": round(float(duration_seconds), 3),
        "state_authority": "ephemeral-vm",
        "physical_state_mutated": False,
    }


def converge_verification(
    artifact: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if artifact.get("schema") != "aurum-pc-artifact-v1":
        raise ValueError("unsupported Aurum PC artifact manifest")
    if artifact.get("promotion_state") != "unverified":
        raise ValueError("only an unverified artifact may enter convergence")
    if not _HEX_DIGEST.fullmatch(str(artifact.get("iso_sha256", ""))):
        raise ValueError("artifact ISO digest is invalid")

    by_profile: dict[str, Mapping[str, Any]] = {}
    for item in evidence:
        profile = _require_text(item.get("profile"), "verification profile")
        if profile in by_profile:
            raise ValueError(f"duplicate verifier evidence: {profile}")
        by_profile[profile] = item
    missing = sorted(set(MANDATORY_VM_PROFILES) - set(by_profile))
    if missing:
        raise ValueError(f"mandatory verification is missing: {missing}")

    for profile, item in by_profile.items():
        expected = MANDATORY_VM_PROFILES.get(profile)
        if expected is None:
            raise ValueError(f"unregistered verifier evidence: {profile}")
        if item.get("schema") != "aurum-pc-verification-v1" or not item.get("verified"):
            raise ValueError(f"verifier did not pass: {profile}")
        for field in ("source_sha", "artifact_identity", "iso_sha256", "builder_image"):
            if item.get(field) != artifact.get(field):
                raise ValueError(f"{profile} does not match artifact {field}")
        if item.get("architecture") != expected["architecture"]:
            raise ValueError(f"{profile} architecture evidence is incorrect")
        if item.get("execution_environment") not in expected["execution_environments"]:
            raise ValueError(f"{profile} execution environment is incorrect")
        if item.get("work_type") != "vm-topology-verification":
            raise ValueError(f"{profile} is not VM-topology verification")
        if item.get("state_authority") != "ephemeral-vm" or item.get("physical_state_mutated"):
            raise ValueError(f"{profile} crossed the trusted physical-state boundary")

    return {
        "schema": "aurum-pc-promotion-v1",
        "artifact_identity": artifact["artifact_identity"],
        "source_sha": artifact["source_sha"],
        "architecture": artifact["architecture"],
        "iso_sha256": artifact["iso_sha256"],
        "builder_image": artifact["builder_image"],
        "mandatory_profiles": sorted(MANDATORY_VM_PROFILES),
        "verified_profiles": sorted(by_profile),
        "verifier_durations_seconds": {
            name: float(by_profile[name]["duration_seconds"]) for name in sorted(by_profile)
        },
        "promotion_state": "verified",
        "promotion_path": "single-verified-path-only",
        "physical_state_mutated": False,
    }


def timing_evidence(
    *,
    artifact: Mapping[str, Any],
    promotion: Mapping[str, Any],
    baseline: Mapping[str, Any],
    pipeline_finished_epoch: int,
) -> dict[str, Any]:
    if promotion.get("promotion_state") != "verified":
        raise ValueError("timing cannot finalize an unverified promotion")
    if promotion.get("artifact_identity") != artifact.get("artifact_identity"):
        raise ValueError("timing inputs refer to different artifacts")
    start = int(artifact["timing"]["pipeline_started_epoch"])
    current = max(0, int(pipeline_finished_epoch) - start)
    old = int(baseline["measurement"]["critical_path_seconds"])
    saved = old - current
    ratio = (old / current) if current else None
    return {
        "schema": "aurum-pc-pipeline-timing-v1",
        "artifact_identity": artifact["artifact_identity"],
        "iso_sha256": artifact["iso_sha256"],
        "measurement_boundary": "validation-step-start-through-verified-publication-step-complete",
        "pipeline_started_epoch": start,
        "pipeline_finished_epoch": int(pipeline_finished_epoch),
        "critical_path_seconds": current,
        "baseline_run_id": baseline["source"]["run_id"],
        "baseline_run_url": baseline["source"]["run_url"],
        "baseline_critical_path_seconds": old,
        "time_saved_seconds": saved,
        "speedup_ratio": round(ratio, 4) if ratio is not None else None,
        "cache_hit": bool(artifact["cache"]["hit"]),
        "stage_seconds": {
            "validation": artifact["timing"]["validation_seconds"],
            "builder_pull": artifact["timing"]["builder_pull_seconds"],
            "container_start": artifact["timing"]["container_start_seconds"],
            "iso_build": artifact["timing"]["iso_build_seconds"],
            "verifiers": promotion["verifier_durations_seconds"],
        },
        "provenance": "Recorded by GitHub Actions from observed epoch stage clocks; negative time_saved_seconds means the new run was slower.",
    }


def select_proven_route(
    routes: Sequence[Mapping[str, Any]],
    *,
    requested_route: str | None = None,
) -> Mapping[str, Any]:
    """Choose the fastest proven route only after higher-priority constraints pass."""
    if requested_route is not None:
        requested = [route for route in routes if route.get("name") == requested_route]
        if len(requested) != 1:
            raise ValueError("requested route is unavailable or ambiguous")
        candidates = requested
    else:
        candidates = list(routes)
    eligible = [
        route
        for route in candidates
        if route.get("proven")
        and route.get("correctness")
        and route.get("safety")
        and route.get("user_intent")
        and route.get("mandatory_verification")
    ]
    if not eligible:
        raise ValueError("no route satisfies correctness, safety, intent, and verification")
    return min(
        eligible,
        key=lambda route: (
            -int(route.get("verification_strength", 0)),
            float(route.get("latency_seconds", float("inf"))),
            float(route.get("compute_units", float("inf"))),
            float(route.get("cost_units", float("inf"))),
            str(route.get("name")),
        ),
    )


def _boolean(value: str) -> bool:
    return value.casefold() in {"1", "true", "yes", "hit"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    revision = subparsers.add_parser("builder-revision")
    revision.add_argument("--repo-root", type=Path, default=REPOSITORY_ROOT)

    identity = subparsers.add_parser("identity")
    identity.add_argument("--repo-root", type=Path, default=REPOSITORY_ROOT)
    identity.add_argument("--source-sha", required=True)
    identity.add_argument("--architecture", required=True)
    identity.add_argument("--builder-image", required=True)
    identity.add_argument("--output", type=Path, required=True)
    identity.add_argument("--github-output", type=Path)

    artifact = subparsers.add_parser("artifact")
    artifact.add_argument("--identity", type=Path, required=True)
    artifact.add_argument("--iso", type=Path, required=True)
    artifact.add_argument("--cache-hit", default="false")
    artifact.add_argument("--pipeline-started-epoch", type=int, required=True)
    artifact.add_argument("--validation-seconds", type=float, required=True)
    artifact.add_argument("--builder-pull-seconds", type=float, required=True)
    artifact.add_argument("--container-start-seconds", type=float, required=True)
    artifact.add_argument("--iso-build-seconds", type=float, required=True)
    artifact.add_argument("--output", type=Path, required=True)
    artifact.add_argument("--github-output", type=Path)

    verification = subparsers.add_parser("verification")
    verification.add_argument("--artifact", type=Path, required=True)
    verification.add_argument("--profile", required=True)
    verification.add_argument("--log", type=Path, required=True)
    verification.add_argument("--required-marker", action="append", default=[])
    verification.add_argument("--duration-seconds", type=float, required=True)
    verification.add_argument("--execution-environment", required=True)
    verification.add_argument("--output", type=Path, required=True)

    promote = subparsers.add_parser("promote")
    promote.add_argument("--artifact", type=Path, required=True)
    promote.add_argument("--evidence", type=Path, action="append", required=True)
    promote.add_argument("--output", type=Path, required=True)

    timing = subparsers.add_parser("timing")
    timing.add_argument("--artifact", type=Path, required=True)
    timing.add_argument("--promotion", type=Path, required=True)
    timing.add_argument("--baseline", type=Path, required=True)
    timing.add_argument("--pipeline-finished-epoch", type=int, default=0)
    timing.add_argument("--output", type=Path, required=True)
    timing.add_argument("--github-output", type=Path)

    stage = subparsers.add_parser("stage")
    stage.add_argument("--name", required=True)
    stage.add_argument("--started-epoch", type=int, required=True)
    stage.add_argument("--finished-epoch", type=int, required=True)
    stage.add_argument("--source-sha", required=True)
    stage.add_argument("--output", type=Path, required=True)

    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "builder-revision":
        print(builder_revision(args.repo_root))
        return 0
    if args.command == "identity":
        value = compute_identities(
            root=args.repo_root,
            source_sha=args.source_sha,
            architecture=args.architecture,
            builder_image=args.builder_image,
        )
        _write_json(args.output, value)
        _github_outputs(
            args.github_output,
            {
                "artifact_identity": value["artifact_identity"],
                "live_build_cache_identity": value["live_build_cache_identity"],
            },
        )
        print(json.dumps(value, sort_keys=True))
        return 0
    if args.command == "artifact":
        value = create_artifact_manifest(
            identity=_load_json(args.identity),
            iso_path=args.iso,
            cache_hit=_boolean(args.cache_hit),
            pipeline_started_epoch=args.pipeline_started_epoch,
            validation_seconds=args.validation_seconds,
            builder_pull_seconds=args.builder_pull_seconds,
            container_start_seconds=args.container_start_seconds,
            iso_build_seconds=args.iso_build_seconds,
        )
        _write_json(args.output, value)
        _github_outputs(
            args.github_output,
            {"iso_sha256": value["iso_sha256"], "artifact_identity": value["artifact_identity"]},
        )
        print(json.dumps(value, sort_keys=True))
        return 0
    if args.command == "verification":
        value = create_verification_evidence(
            artifact=_load_json(args.artifact),
            profile=args.profile,
            log_path=args.log,
            required_markers=args.required_marker,
            duration_seconds=args.duration_seconds,
            execution_environment=args.execution_environment,
        )
        _write_json(args.output, value)
        print(json.dumps(value, sort_keys=True))
        return 0
    if args.command == "promote":
        value = converge_verification(
            _load_json(args.artifact),
            [_load_json(path) for path in args.evidence],
        )
        _write_json(args.output, value)
        print(json.dumps(value, sort_keys=True))
        return 0
    if args.command == "timing":
        finished = args.pipeline_finished_epoch or int(time.time())
        value = timing_evidence(
            artifact=_load_json(args.artifact),
            promotion=_load_json(args.promotion),
            baseline=_load_json(args.baseline),
            pipeline_finished_epoch=finished,
        )
        _write_json(args.output, value)
        _github_outputs(
            args.github_output,
            {
                "critical_path_seconds": value["critical_path_seconds"],
                "time_saved_seconds": value["time_saved_seconds"],
                "speedup_ratio": value["speedup_ratio"],
            },
        )
        print(json.dumps(value, sort_keys=True))
        return 0
    if args.command == "stage":
        value = {
            "schema": "aurum-pc-stage-timing-v1",
            "stage": args.name,
            "source_sha": args.source_sha,
            "started_epoch": args.started_epoch,
            "finished_epoch": args.finished_epoch,
            "duration_seconds": max(0, args.finished_epoch - args.started_epoch),
        }
        _write_json(args.output, value)
        print(json.dumps(value, sort_keys=True))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
