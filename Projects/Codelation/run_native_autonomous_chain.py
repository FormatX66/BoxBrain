#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Mapping

FIELD_DIR = Path(__file__).resolve().parent / "field"
sys.path.insert(0, str(FIELD_DIR))

from external_prerequisite_evidence import apply_external_prerequisite_evidence_from_file  # noqa: E402
from field_native_registry_bridge import build_verified_native_registry_artifact  # noqa: E402
from field_native_self_build import NativeGap  # noqa: E402
from local_capability_verification import (  # noqa: E402
    LOCAL_VERIFICATION_REVISION,
    verify_local_capability_for_gap,
)
from native_failure_diagnosis import diagnose_native_synthesis_failure  # noqa: E402
from native_gap_catalog import CATALOG_REVISION, get_native_semantic_gap  # noqa: E402
from native_program_synthesis import SYNTHESIS_REVISION, synthesize_native_expression  # noqa: E402
from native_self_debug import SELF_DEBUG_REVISION, audit_native_self_build  # noqa: E402


STATE_PATH = Path(__file__).resolve().parent / "autobuild" / "native_chain_state.json"
STATE_SCHEMA = "aurum-native-autonomous-chain-v6"
PROGRESS_PREFIX = "AURUM_BUILD_PROGRESS "


def _atomic_state_write(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _compatible_checkpoint_state(state: Mapping[str, Any] | None) -> bool:
    if not isinstance(state, Mapping):
        return False
    checkpoint = state.get("_checkpoint")
    return bool(
        state.get("schema") == STATE_SCHEMA
        and state.get("catalog_revision") == CATALOG_REVISION
        and state.get("synthesis_revision") == SYNTHESIS_REVISION
        and state.get("self_debug_revision") == SELF_DEBUG_REVISION
        and state.get("local_verification_revision") == LOCAL_VERIFICATION_REVISION
        and isinstance(checkpoint, Mapping)
        and isinstance(checkpoint.get("learned_expressions"), Mapping)
        and isinstance(checkpoint.get("verified_local_capabilities"), list)
    )


def _resumable_state(state: Mapping[str, Any] | None, start_gap: str) -> bool:
    return bool(
        _compatible_checkpoint_state(state)
        and state is not None
        and state.get("start_gap") == start_gap
        and isinstance(state.get("generations"), list)
        and isinstance(state.get("next_gap"), str)
    )


def _checkpoint_capabilities(
    state: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], set[str]]:
    checkpoint = state["_checkpoint"]
    assert isinstance(checkpoint, Mapping)
    raw_expressions = checkpoint["learned_expressions"]
    raw_local = checkpoint["verified_local_capabilities"]
    assert isinstance(raw_expressions, Mapping)
    assert isinstance(raw_local, list)
    return (
        {
            str(name): dict(expression)
            for name, expression in raw_expressions.items()
            if isinstance(expression, Mapping)
        },
        {str(name) for name in raw_local if str(name)},
    )


def _complete_local_candidates(diagnosis: Mapping[str, Any]) -> tuple[str, ...]:
    raw = diagnosis.get("local_capability_candidates", ())
    names: list[str] = []
    if isinstance(raw, (list, tuple)):
        for candidate in raw:
            if not isinstance(candidate, Mapping):
                continue
            if candidate.get("missing") or candidate.get("authority") != "none":
                continue
            name = str(candidate.get("name", ""))
            if name:
                names.append(name)
    return tuple(dict.fromkeys(names))


def _is_external_prerequisite_block(spec: Any, invocation_output: Any) -> bool:
    """Stop at verified fail-closed classification boundaries without inventing work."""
    constraints = set(getattr(spec, "constraints", ()) or ())
    return (
        isinstance(invocation_output, str)
        and invocation_output.startswith("blocked-")
        and "classification-only" in constraints
        and "fail-closed" in constraints
    )


def _normalize_seed_expressions(
    seed_expressions: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Mapping[str, Any]]:
    normalized: dict[str, Mapping[str, Any]] = {}
    for name, expression in sorted((seed_expressions or {}).items()):
        if not isinstance(name, str) or not name or not isinstance(expression, Mapping):
            raise ValueError("seed expressions must map non-empty names to expression mappings")
        normalized[name] = dict(expression)
    return normalized


def run_chain(
    start_gap: str = "learning_delta_score",
    *,
    max_generations: int = 24,
    seed_expressions: Mapping[str, Mapping[str, Any]] | None = None,
    resume_state: Mapping[str, Any] | None = None,
    seed_state: Mapping[str, Any] | None = None,
    on_progress: Callable[[Mapping[str, Any]], None] | None = None,
    on_checkpoint: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict:
    current = start_gap
    completed: list[dict] = []
    failed_attempt: dict | None = None
    blocked_reason: str | None = None
    explicit_seed_expressions = _normalize_seed_expressions(seed_expressions)
    learned_expressions: dict[str, Mapping[str, Any]] = dict(explicit_seed_expressions)
    verified_local_capabilities: set[str] = set()
    external_evidence_status: dict[str, Any] | None = None
    resumed_from_generations = 0
    seeded_from_checkpoint = False
    started = time.monotonic()

    def emit(status: str, **details: Any) -> None:
        if on_progress is not None:
            on_progress(
                {
                    "status": status,
                    "elapsed_seconds": round(time.monotonic() - started, 1),
                    **details,
                }
            )

    if _resumable_state(resume_state, start_gap):
        assert resume_state is not None
        completed = [dict(generation) for generation in resume_state["generations"]]
        current = str(resume_state["next_gap"])
        learned_expressions, verified_local_capabilities = _checkpoint_capabilities(resume_state)
        raw_external = resume_state.get("external_evidence")
        external_evidence_status = dict(raw_external) if isinstance(raw_external, Mapping) else None
        resumed_from_generations = len(completed)
        emit("resumed", completed_generations=resumed_from_generations, next_gap=current)

        if resume_state.get("blocked_reason") == "external-prerequisite-blocked":
            current_spec = get_native_semantic_gap(current)
            if current_spec is not None:
                current_evidence = apply_external_prerequisite_evidence_from_file(current_spec)
                current_status = {
                    "applied": current_evidence.applied,
                    "reason": current_evidence.reason,
                    "evidence": (
                        dict(current_evidence.evidence)
                        if current_evidence.evidence is not None
                        else None
                    ),
                }
                if current_status == external_evidence_status:
                    cached = dict(resume_state)
                    cached["cache_hit"] = True
                    cached["resumed_from_generations"] = resumed_from_generations
                    emit("cached", completed_generations=len(completed), next_gap=current)
                    return cached
                if completed and completed[-1].get("gap") == current:
                    replaced = completed.pop()
                    local_name = replaced.get("local_capability")
                    if local_name and not any(
                        generation.get("local_capability") == local_name for generation in completed
                    ):
                        verified_local_capabilities.discard(str(local_name))
                    resumed_from_generations = len(completed)
                    emit("checkpoint-invalidated", reason="external-evidence-changed", next_gap=current)
    elif _compatible_checkpoint_state(seed_state):
        assert seed_state is not None
        learned_expressions, verified_local_capabilities = _checkpoint_capabilities(seed_state)
        learned_expressions.update(explicit_seed_expressions)
        seeded_from_checkpoint = True
        emit(
            "seeded",
            native_capabilities=len(learned_expressions),
            local_capabilities=len(verified_local_capabilities),
            next_gap=current,
        )

    initial_seed_names = tuple(sorted(learned_expressions))

    def partial_state(reason: str = "in-progress") -> dict[str, Any]:
        return {
            "schema": STATE_SCHEMA,
            "catalog_revision": CATALOG_REVISION,
            "synthesis_revision": SYNTHESIS_REVISION,
            "self_debug_revision": SELF_DEBUG_REVISION,
            "local_verification_revision": LOCAL_VERIFICATION_REVISION,
            "start_gap": start_gap,
            "completed_generations": len(completed),
            "latest_completed_gap": completed[-1]["gap"] if completed else None,
            "next_gap": current,
            "blocked_reason": reason,
            "blocked_output": None,
            "external_evidence": external_evidence_status,
            "failed_attempt": None,
            "initial_seed_capabilities": list(initial_seed_names),
            "reusable_native_capabilities": sorted(learned_expressions),
            "reusable_native_expressions": {
                name: dict(expression) for name, expression in sorted(learned_expressions.items())
            },
            "reusable_local_capabilities": sorted(verified_local_capabilities),
            "internal_next_action": None,
            "reasoning_required": False,
            "reasoning_request": None,
            "timer_dependency": False,
            "generations": completed,
            "resumed_from_generations": resumed_from_generations,
            "seeded_from_checkpoint": seeded_from_checkpoint,
            "_checkpoint": {
                "schema": "aurum-native-chain-resume-v1",
                "learned_expressions": learned_expressions,
                "verified_local_capabilities": sorted(verified_local_capabilities),
            },
        }

    def checkpoint(reason: str = "in-progress") -> None:
        if on_checkpoint is not None:
            on_checkpoint(partial_state(reason))

    chain_start_generation = len(completed)
    for _ in range(len(completed), max_generations):
        emit(
            "generation-started",
            generation=len(completed) + 1,
            total_generations=max_generations,
            gap=current,
        )
        spec = get_native_semantic_gap(current)
        if spec is None:
            blocked_reason = "semantic-spec-missing"
            break

        evidence_application = apply_external_prerequisite_evidence_from_file(spec)
        spec = evidence_application.spec
        if spec.name == "adaptive_shell_live_trial_readiness":
            external_evidence_status = {
                "applied": evidence_application.applied,
                "reason": evidence_application.reason,
                "evidence": (
                    dict(evidence_application.evidence)
                    if evidence_application.evidence is not None
                    else None
                ),
            }

        preflight = audit_native_self_build(
            spec.parameters,
            spec.examples,
            stage="preflight",
        )
        if preflight.status == "blocked":
            blocked_reason = "self-debug-preflight-rejected"
            failed_attempt = {
                "attempted_generation": len(completed) + 1,
                "gap": current,
                "self_debug": asdict(preflight),
                "verified": False,
            }
            break

        synthesis = synthesize_native_expression(
            spec.parameters,
            spec.examples,
            max_cost=spec.max_synthesis_cost,
            seed_expressions=learned_expressions,
        )
        if not synthesis.found or synthesis.expression is None:
            diagnosis = diagnose_native_synthesis_failure(spec.parameters, spec.examples)
            self_debug = audit_native_self_build(
                spec.parameters,
                spec.examples,
                stage="post-failure",
                synthesis=asdict(synthesis),
                diagnosis=asdict(diagnosis),
            )

            if self_debug.internal_next_action == "verify-existing-local-capability":
                local_failures: list[dict[str, Any]] = []
                external_prerequisite_blocked = False
                for capability_name in _complete_local_candidates(asdict(diagnosis)):
                    try:
                        local = verify_local_capability_for_gap(spec, capability_name)
                    except (ImportError, AttributeError, TypeError, ValueError) as exc:
                        local_failures.append({"capability": capability_name, "error": str(exc)})
                        continue
                    if not local.verified:
                        local_failures.append(
                            {
                                "capability": capability_name,
                                "verification_identity": local.verification_identity,
                                "passed": local.passed,
                                "examples": local.examples,
                            }
                        )
                        continue

                    verified_local_capabilities.add(local.capability)
                    completed.append(
                        {
                            "generation": len(completed) + 1,
                            "gap": spec.name,
                            "next_gap": spec.next_gap,
                            "representation": "verified-local-capability-reuse",
                            "preflight_self_debug": {
                                "status": preflight.status,
                                "report_identity": preflight.report_identity,
                                "issues": len(preflight.issues),
                                "counterexamples": len(preflight.counterexamples),
                            },
                            "native_synthesis_found": False,
                            "native_synthesis_proof_identity": synthesis.proof_identity,
                            "native_candidates_evaluated": synthesis.candidates_evaluated,
                            "native_signatures_retained": synthesis.signatures_retained,
                            "post_failure_self_debug_identity": self_debug.report_identity,
                            "local_capability": local.capability,
                            "local_module": local.module,
                            "local_callable": local.callable_name,
                            "local_verification_adapter": local.adapter,
                            "local_implementation_sha256": local.implementation_sha256,
                            "verification_identity": local.verification_identity,
                            "invocation_output": local.invocation_output,
                            "external_evidence": (
                                dict(evidence_application.evidence)
                                if evidence_application.applied and evidence_application.evidence is not None
                                else None
                            ),
                            "state": "verified",
                            "authority_granted": local.authority_granted,
                            "routed_to_host": local.routed_to_host,
                            "promotion_performed": False,
                            "model_reasoning_used": False,
                            "source_generation_used": False,
                            "filesystem_build_used": False,
                            "subprocess_test_used": False,
                            "reusable_native_capabilities_after_build": sorted(learned_expressions),
                            "reusable_local_capabilities_after_build": sorted(verified_local_capabilities),
                        }
                    )
                    failed_attempt = None
                    if _is_external_prerequisite_block(spec, local.invocation_output):
                        blocked_reason = "external-prerequisite-blocked"
                        external_prerequisite_blocked = True
                    else:
                        current = spec.next_gap
                        blocked_reason = None
                    checkpoint(blocked_reason or "in-progress")
                    emit(
                        "generation-completed",
                        generation=len(completed),
                        total_generations=max_generations,
                        gap=spec.name,
                        next_gap=current,
                        representation="verified-local-capability-reuse",
                        upper_bound_eta_seconds=round(
                            (time.monotonic() - started)
                            / max(1, len(completed) - chain_start_generation)
                            * max(0, max_generations - len(completed)),
                            1,
                        ),
                    )
                    break
                else:
                    blocked_reason = "local-capability-verification-failed"
                    failed_attempt = {
                        "attempted_generation": len(completed) + 1,
                        "gap": current,
                        "synthesis": asdict(synthesis),
                        "diagnosis": asdict(diagnosis),
                        "self_debug": asdict(self_debug),
                        "local_verification_failures": local_failures,
                        "verified": False,
                    }
                    break

                if external_prerequisite_blocked:
                    break
                continue

            blocked_reason = "native-synthesis-not-found"
            failed_attempt = {
                "attempted_generation": len(completed) + 1,
                "gap": current,
                "synthesis": asdict(synthesis),
                "diagnosis": asdict(diagnosis),
                "self_debug": asdict(self_debug),
                "verified": False,
            }
            break

        gap = NativeGap(
            name=spec.name,
            parameters=spec.parameters,
            expression=synthesis.expression,
            examples=spec.examples,
            purpose=spec.purpose,
            learned_principles=spec.principles,
            constraints=spec.constraints,
        )
        built = build_verified_native_registry_artifact(
            gap,
            invocation_arguments=spec.invocation_arguments,
            node="aurum-native-autonomous-chain",
        )
        if built.artifact.state != "verified":
            blocked_reason = "verified-registry-bridge-rejected"
            failed_attempt = {
                "attempted_generation": len(completed) + 1,
                "gap": current,
                "verified": False,
            }
            break

        learned_expressions[spec.name] = dict(synthesis.expression)
        completed.append(
            {
                "generation": len(completed) + 1,
                "gap": spec.name,
                "next_gap": spec.next_gap,
                "representation": "field-native-program",
                "preflight_self_debug": {
                    "status": preflight.status,
                    "report_identity": preflight.report_identity,
                    "issues": len(preflight.issues),
                    "counterexamples": len(preflight.counterexamples),
                },
                "synthesis_proof_identity": synthesis.proof_identity,
                "synthesis_cost": synthesis.cost,
                "candidates_evaluated": synthesis.candidates_evaluated,
                "signatures_retained": synthesis.signatures_retained,
                "seed_expressions_considered": list(synthesis.seed_expressions_considered),
                "reusable_native_capabilities_after_build": sorted(learned_expressions),
                "reusable_local_capabilities_after_build": sorted(verified_local_capabilities),
                "artifact_identity": built.artifact_identity,
                "local_variant_identity": built.artifact.local_variant_identity,
                "carrier_sha256": built.artifact.carrier_sha256,
                "carrier_field_id": built.carrier.field_id,
                "verification_identity": built.verification_identity,
                "invocation_output": built.invocation_output,
                "external_evidence": (
                    dict(evidence_application.evidence)
                    if evidence_application.applied and evidence_application.evidence is not None
                    else None
                ),
                "state": built.artifact.state,
                "promotion_performed": False,
                "model_reasoning_used": False,
                "source_generation_used": False,
                "filesystem_build_used": False,
                "subprocess_test_used": False,
            }
        )
        current = spec.next_gap
        checkpoint()
        emit(
            "generation-completed",
            generation=len(completed),
            total_generations=max_generations,
            gap=spec.name,
            next_gap=current,
            representation="field-native-program",
            upper_bound_eta_seconds=round(
                (time.monotonic() - started)
                / max(1, len(completed) - chain_start_generation)
                * max(0, max_generations - len(completed)),
                1,
            ),
        )
    else:
        blocked_reason = "generation-bound-reached"

    builder_learning: list[str] = []
    self_debug_payload: dict[str, Any] | None = None
    if failed_attempt is not None:
        diagnosis = failed_attempt.get("diagnosis")
        if isinstance(diagnosis, dict):
            raw = diagnosis.get("builder_learning", [])
            if isinstance(raw, (list, tuple)):
                builder_learning = [str(item) for item in raw]
        raw_self_debug = failed_attempt.get("self_debug")
        if isinstance(raw_self_debug, dict):
            self_debug_payload = raw_self_debug

    if blocked_reason == "semantic-spec-missing":
        reasoning_required = True
        internal_next_action = None
    elif self_debug_payload is not None:
        reasoning_required = bool(self_debug_payload.get("model_escalation_advised"))
        raw_action = self_debug_payload.get("internal_next_action")
        internal_next_action = str(raw_action) if raw_action else None
    else:
        reasoning_required = False
        internal_next_action = None

    result = {
        "schema": STATE_SCHEMA,
        "catalog_revision": CATALOG_REVISION,
        "synthesis_revision": SYNTHESIS_REVISION,
        "self_debug_revision": SELF_DEBUG_REVISION,
        "local_verification_revision": LOCAL_VERIFICATION_REVISION,
        "start_gap": start_gap,
        "completed_generations": len(completed),
        "latest_completed_gap": completed[-1]["gap"] if completed else None,
        "next_gap": current,
        "blocked_reason": blocked_reason,
        "blocked_output": (
            completed[-1].get("invocation_output")
            if blocked_reason == "external-prerequisite-blocked" and completed
            else None
        ),
        "external_evidence": external_evidence_status,
        "failed_attempt": failed_attempt,
        "initial_seed_capabilities": list(initial_seed_names),
        "reusable_native_capabilities": sorted(learned_expressions),
        "reusable_native_expressions": {
            name: dict(expression) for name, expression in sorted(learned_expressions.items())
        },
        "reusable_local_capabilities": sorted(verified_local_capabilities),
        "internal_next_action": internal_next_action,
        "reasoning_required": reasoning_required,
        "reasoning_request": (
            {
                "gap": current,
                "reason": blocked_reason,
                "required_output": "bounded diagnosis or builder-learning proposal only after Aurum self-debug has exhausted internal deterministic checks; do not provide a promoted implementation",
                "builder_learning": builder_learning,
                "self_debug_report_identity": (
                    self_debug_payload.get("report_identity") if self_debug_payload else None
                ),
                "shared_implementation": False,
            }
            if reasoning_required
            else None
        ),
        "timer_dependency": False,
        "generations": completed,
        "resumed_from_generations": resumed_from_generations,
        "seeded_from_checkpoint": seeded_from_checkpoint,
        "_checkpoint": {
            "schema": "aurum-native-chain-resume-v1",
            "learned_expressions": learned_expressions,
            "verified_local_capabilities": sorted(verified_local_capabilities),
        },
    }
    emit(
        "completed",
        completed_generations=len(completed),
        next_gap=current,
        blocked_reason=blocked_reason,
    )
    return result


def _generation_limit(value: str) -> int:
    limit = int(value)
    if limit < 1 or limit > 256:
        raise argparse.ArgumentTypeError("max generations must be between 1 and 256")
    return limit


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Aurum's bounded native autonomous chain")
    parser.add_argument("--resume", action="store_true", help="resume from a compatible generation checkpoint")
    parser.add_argument(
        "--start-gap",
        default="learning_delta_score",
        help="semantic gap where this isolated chain lane begins",
    )
    parser.add_argument(
        "--max-generations",
        type=_generation_limit,
        default=24,
        help="bounded generation limit for this lane (1-256)",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=STATE_PATH,
        help="lane-specific checkpoint/result path",
    )
    parser.add_argument(
        "--seed-state",
        type=Path,
        help="compatible checkpoint whose verified capabilities seed an isolated frontier lane",
    )
    args = parser.parse_args()
    state_path = args.state_path.resolve()
    resume_state: Mapping[str, Any] | None = None
    seed_state: Mapping[str, Any] | None = None
    if args.resume and state_path.is_file():
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(loaded, Mapping):
                resume_state = loaded
        except (OSError, json.JSONDecodeError):
            resume_state = None
    if args.seed_state is not None:
        seed_path = args.seed_state.resolve()
        try:
            loaded_seed = json.loads(seed_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"seed checkpoint is unreadable: {exc}")
        if not isinstance(loaded_seed, Mapping) or not _compatible_checkpoint_state(loaded_seed):
            parser.error("seed checkpoint is incompatible with this native chain revision")
        seed_state = loaded_seed

    def show_progress(event: Mapping[str, Any]) -> None:
        print(PROGRESS_PREFIX + json.dumps(dict(event), sort_keys=True), file=sys.stderr, flush=True)

    state = run_chain(
        start_gap=args.start_gap,
        max_generations=args.max_generations,
        resume_state=resume_state,
        seed_state=seed_state,
        on_progress=show_progress,
        on_checkpoint=lambda value: _atomic_state_write(state_path, value),
    )
    _atomic_state_write(state_path, state)
    print(json.dumps(state, indent=2, sort_keys=True))
    return 0 if state["completed_generations"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
