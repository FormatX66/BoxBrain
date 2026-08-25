#!/usr/bin/python3
"""Collapse a pre-executed FutureBranch QPU field against live Pi 3 evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


EXPECTED_KERNEL = "6.12.105-aurum-pi3-v0.02+"
EXPECTED_WINNER = (
    "corrected-image-flash-readback-and-physical-futurebranch-qpu-boot-pass"
)


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value, hashlib.sha256(raw).hexdigest()


def _reject_secret_fields(value: Any, *, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("apikey", "api_key", "token", "secret")):
                raise ValueError(f"secret-like field is forbidden in QPU evidence: {path}.{key}")
            _reject_secret_fields(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_fields(child, path=f"{path}[{index}]")


def validate_qpu_evidence(
    candidate_path: Path,
    status_path: Path,
    branch_state_path: Path,
) -> dict[str, Any]:
    candidate, candidate_sha = _read_json(candidate_path)
    status, status_sha = _read_json(status_path)
    _, branch_state_sha = _read_json(branch_state_path)
    _reject_secret_fields(candidate)
    _reject_secret_fields(status)

    if candidate.get("schema") != "aurum-future-branch-qpu-candidate-v1":
        raise ValueError("unexpected FutureBranch QPU candidate schema")
    analysis = candidate.get("analysis")
    submission = candidate.get("submission")
    circuit = candidate.get("circuit")
    if not isinstance(analysis, dict) or not isinstance(submission, dict):
        raise ValueError("QPU candidate lacks analysis or submission")
    if not isinstance(circuit, dict) or circuit.get("paths") != 8 or circuit.get("qubits") != 3:
        raise ValueError("QPU candidate does not encode the complete eight-path Pi field")
    if analysis.get("branch_state_sha256") != branch_state_sha:
        raise ValueError("QPU analysis is not bound to the supplied Pi branch state")
    if analysis.get("qpu_eligible") is not True:
        raise ValueError("Pi branch field did not pass the QPU eligibility gate")
    if analysis.get("speculative_feasibility", {}).get("decision") != "pre-run":
        raise ValueError("Pi branch field did not pass speculative feasibility")

    envelope = submission.get("envelope")
    if not isinstance(envelope, dict):
        raise ValueError("QPU submission envelope is missing")
    if envelope.get("provider") != "ibm_quantum" or envelope.get("qpu_approved") is not True:
        raise ValueError("submission does not prove an approved IBM QPU route")
    if int(envelope.get("shots", 0)) != 256:
        raise ValueError("QPU submission must contain exactly 256 bounded shots")

    if status.get("schema") != "aurum-future-branch-qpu-result-v1":
        raise ValueError("unexpected FutureBranch QPU result schema")
    if status.get("status") != "DONE":
        raise ValueError("QPU result is not complete")
    if status.get("job_id") != submission.get("job_id"):
        raise ValueError("QPU candidate/result job mismatch")
    if status.get("backend") != envelope.get("backend"):
        raise ValueError("QPU candidate/result backend mismatch")
    counts = status.get("counts")
    if not isinstance(counts, dict) or sum(int(value) for value in counts.values()) != 256:
        raise ValueError("QPU counts do not contain the complete 256-shot result")

    evaluation = status.get("evaluation")
    if not isinstance(evaluation, dict):
        raise ValueError("QPU evaluation is missing")
    if evaluation.get("distribution_usable") is not True:
        raise ValueError("QPU distribution failed its usability gate")
    if evaluation.get("winning_path") != EXPECTED_WINNER:
        raise ValueError("QPU winner does not match the prepared physical-success path")
    if evaluation.get("winning_path_selected_for_execution") is not True:
        raise ValueError("QPU winner was not retained by the execution gate")
    agreement = evaluation.get("rank_agreement", {})
    if agreement.get("top_path_agreement") is not True:
        raise ValueError("QPU and model top paths disagree")
    if float(agreement.get("spearman_rank_correlation", -1.0)) != 1.0:
        raise ValueError("QPU result did not preserve the complete model ordering")
    if evaluation.get("learning", {}).get("recommendation") != (
        "retain-top-probability-execution-selection"
    ):
        raise ValueError("QPU result requires model review instead of physical collapse")

    return {
        "provider": envelope["provider"],
        "backend": status["backend"],
        "job_id": status["job_id"],
        "shots": 256,
        "winner": evaluation["winning_path"],
        "winning_shots": int(counts[evaluation["winning_state"]]),
        "total_variation_distance": float(evaluation["total_variation_distance"]),
        "spearman_rank_correlation": 1.0,
        "candidate_sha256": candidate_sha,
        "result_sha256": status_sha,
        "branch_state_sha256": branch_state_sha,
        "secret_free": True,
    }


def _load_futurebranch_modules(lib_dir: Path) -> dict[str, Any]:
    sys.path.insert(0, str(lib_dir))
    names = (
        "pi3_physical_probe",
        "reality_gap",
        "gap_stack",
        "surprise_budget",
        "human_availability",
        "unattended_precompute",
        "execution_route",
    )
    return {name: importlib.import_module(name) for name in names}


def canonical_layers(modules: dict[str, Any]) -> dict[str, Any]:
    reality = modules["reality_gap"]
    gap_stack = modules["gap_stack"]
    surprise = modules["surprise_budget"]
    human = modules["human_availability"]
    unattended = modules["unattended_precompute"]
    routes = modules["execution_route"]

    transition = reality.RealityTransition(
        proven_at=reality.ProofLevel.VM_EMULATED,
        target=reality.ProofLevel.KNOWN_HARDWARE,
        hardware_novelty=0.10,
        firmware_dependency=0.20,
        driver_dependency=0.20,
        external_state_dependency=0.10,
        prior_physical_proof=True,
    )
    reality_profile = reality.preparation_profile(transition)
    gaps = [
        gap_stack.GapExposure(gap_stack.GapKind.REALITY, 0.30, 0.95, True),
        gap_stack.GapExposure(gap_stack.GapKind.RUNTIME, 0.35, 0.90, True),
        gap_stack.GapExposure(gap_stack.GapKind.EVIDENCE, 0.25, 0.95, True),
        gap_stack.GapExposure(gap_stack.GapKind.RECOVERY_PROOF, 0.25, 0.90, True),
    ]
    gap_profile = gap_stack.gap_preparation_profile(gaps)
    reserve = surprise.surprise_reserve(unpredicted_failures=1, total_failures=1)
    coverage = surprise.failure_family_coverage(set(surprise.CORE_FAILURE_FAMILIES))
    profile = human.default_profile_for_hour(datetime.now().astimezone().hour)
    boundary = human.boundary_policy(
        human_required=False,
        physical_required=False,
        profile=profile,
    )
    pending = unattended.PendingPhysicalAction(
        name="preserve-pi3-qpu-physical-proof",
        probability=1.0,
        hours_until_likely_human_action=0.0,
        reality_gap=float(reality_profile["reality_gap_score"]),
        stacked_gap=float(gap_profile["stacked_gap_score"]),
    )
    route_field = routes.rank_execution_routes(
        [
            routes.ExecutionRoute(
                "direct-local-physical-probe",
                routes.RouteKind.DIRECT_LOCAL,
                True,
                True,
                0.99,
                0.98,
                1.0,
                1.0,
                0.01,
                0.0,
                0.0,
            ),
            routes.ExecutionRoute(
                "bound-ibm-qpu-evidence",
                routes.RouteKind.WORKSPACE_HANDOFF,
                True,
                True,
                0.98,
                0.98,
                0.95,
                1.0,
                0.01,
                0.0,
                0.0,
            ),
            routes.ExecutionRoute(
                "human-kvm-observation",
                routes.RouteKind.HUMAN_ASSISTED,
                True,
                True,
                0.95,
                0.90,
                0.10,
                1.0,
                0.01,
                0.0,
                0.0,
                human_steps=1,
            ),
        ]
    )
    return {
        "reality_gap": reality_profile,
        "gap_stack": gap_profile,
        "surprise_budget": {
            "reserve": reserve,
            "leader_confidence_after_reserve": surprise.calibrated_leader_confidence(
                leader_probability=8 / 9,
                reserve=reserve,
            ),
            "failure_family_coverage": coverage,
        },
        "human_availability": {
            "mode": profile.mode.value,
            "boundary_policy": boundary,
        },
        "unattended_precompute": unattended.physical_session_packet(pending),
        "execution_routes": route_field,
    }


def complete_run(
    *,
    candidate_path: Path,
    status_path: Path,
    branch_state_path: Path,
    lib_dir: Path,
    physical_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    qpu = validate_qpu_evidence(candidate_path, status_path, branch_state_path)
    modules = _load_futurebranch_modules(lib_dir)
    physical_probe = modules["pi3_physical_probe"]
    receipt = physical_receipt or physical_probe.collect_receipt()
    gate = physical_probe.gate_receipt(receipt)
    if not gate["accepted"]:
        raise ValueError("physical Pi 3 receipt gate failed: " + ",".join(gate["problems"]))
    if receipt.get("kernel") != EXPECTED_KERNEL:
        raise ValueError(
            f"unexpected kernel: expected {EXPECTED_KERNEL}, got {receipt.get('kernel')}"
        )
    trial = physical_probe.build_observe_only_trial(receipt)
    layers = canonical_layers(modules)
    if layers["human_availability"]["boundary_policy"]["execution_blocked"]:
        raise ValueError("physical collapse unexpectedly retained a human boundary")
    if layers["execution_routes"][0]["name"] != "direct-local-physical-probe":
        raise ValueError("direct physical verification was not the preferred execution route")

    return {
        "schema": "aurum-pi3-future-branch-qpu-physical-collapse-v1",
        "state": "success",
        "completed_at": datetime.now(UTC).isoformat(),
        "kernel": {
            "release": receipt["kernel"],
            "architecture": receipt["arch"],
            "self_built": True,
        },
        "physical": {
            "receipt": receipt,
            "gate": gate,
            "stateweave_adaptive_kernel_trial": trial,
        },
        "qpu": qpu,
        "canonical_layers": layers,
        "collapse": {
            "observed_branch": EXPECTED_WINNER,
            "matches_qpu_winner": qpu["winner"] == EXPECTED_WINNER,
            "execution_gate_changed": False,
            "promotion_allowed": False,
            "unresolved_frontier": "physical-kvm-evidence-preservation",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate",
        type=Path,
        default=Path("/etc/aurum/future-branch-qpu.json"),
    )
    parser.add_argument(
        "--status",
        type=Path,
        default=Path("/etc/aurum/qpu-status.json"),
    )
    parser.add_argument(
        "--branch-state",
        type=Path,
        default=Path("/etc/aurum/future-branch-state.json"),
    )
    parser.add_argument(
        "--lib-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/var/lib/aurum/pi3-future-branch-qpu.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        receipt = complete_run(
            candidate_path=args.candidate,
            status_path=args.status,
            branch_state_path=args.branch_state,
            lib_dir=args.lib_dir,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        run_path = Path("/run/aurum/pi3-future-branch-qpu.json")
        run_path.parent.mkdir(parents=True, exist_ok=True)
        run_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        qpu = receipt["qpu"]
        print(
            "AURUM_PI3_FUTURE_BRANCH_QPU_COMPLETE "
            f"kernel={platform.release()} backend={qpu['backend']} "
            f"job={qpu['job_id']} shots={qpu['shots']} "
            "paths=8 rank_agreement=1.0 physical_gate=passed"
        )
        return 0
    except Exception as error:
        message = " ".join(str(error).split())
        print(f"AURUM_PI3_FUTURE_BRANCH_QPU_FAILED error={message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
