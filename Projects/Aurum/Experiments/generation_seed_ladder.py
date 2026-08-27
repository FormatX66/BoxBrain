"""Executable safety/dependency contract for Aurum's next three seed generations.

This module deliberately models *evidence gates*, not release authority.  It lets
Future Branch prepare later generations in parallel while refusing to call a
later generation earned before its parent, recovery, provenance, and generation-
specific proof gates exist.

Nothing in this module performs I/O, promotes a candidate, mutates LKG, widens
trust, or infers physical proof from software evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class GenerationSpec:
    name: str
    parent: str | None
    software_gates: tuple[str, ...]
    external_gates: tuple[str, ...]


@dataclass(frozen=True)
class GenerationEvidence:
    generation: str
    software: Mapping[str, bool]
    external: Mapping[str, bool]
    parent_earned: bool = False
    lkg_preserved: bool = True
    recovery_preserved: bool = True
    provenance_bound: bool = True
    compatibility_fallback_preserved: bool = True
    trust_or_authority_widened: bool = False


GENERATION_SPECS: dict[str, GenerationSpec] = {
    "gen1": GenerationSpec(
        name="gen1",
        parent=None,
        software_gates=(
            "graphical_shell_contract",
            "everyday_traits_contract",
            "intent_accessibility_contract",
            "recovery_contract",
            "unattended_candidate_validation",
        ),
        external_gates=(
            "hopper_physical_boot",
            "guardian_forced_rollback",
            "second_architecture_usable",
        ),
    ),
    "gen2": GenerationSpec(
        name="gen2",
        parent="gen1",
        software_gates=(
            "machine_native_state_projection",
            "slush_relationship_model",
            "evidence_driven_generation_selector",
            "presence_adaptive_resource_shadow",
            "adaptive_kernel_driver_shadow",
        ),
        external_gates=(
            "machine_native_state_recovery",
            "presence_policy_physical_canary",
        ),
    ),
    "gen3": GenerationSpec(
        name="gen3",
        parent="gen2",
        software_gates=(
            "lineage_ledger",
            "scoped_trait_inheritance",
            "cross_node_evidence_merge",
            "phenotype_scope_guard",
            "provenance_replay",
            "non_widening_trust_guard",
        ),
        external_gates=(
            "multi_node_live_exchange",
            "independent_node_recovery",
        ),
    ),
}


def _missing(required: tuple[str, ...], supplied: Mapping[str, bool]) -> list[str]:
    return [gate for gate in required if supplied.get(gate) is not True]


def evaluate_generation(evidence: GenerationEvidence) -> dict:
    """Evaluate one generation without granting authority or inventing proof.

    Later generations may be prepared before their parent is earned because that
    work is branch-shared and reversible, but they cannot be marked ``earned``.
    Fail-closed invariants (LKG, recovery, provenance, compatibility, trust) also
    block software-ready status rather than being treated as optional warnings.
    """
    key = evidence.generation.lower().strip()
    spec = GENERATION_SPECS.get(key)
    if spec is None:
        raise ValueError(f"unknown generation: {evidence.generation}")

    missing_software = _missing(spec.software_gates, evidence.software)
    missing_external = _missing(spec.external_gates, evidence.external)
    invariant_failures: list[str] = []

    if not evidence.lkg_preserved:
        invariant_failures.append("lkg-not-preserved")
    if not evidence.recovery_preserved:
        invariant_failures.append("recovery-not-preserved")
    if not evidence.provenance_bound:
        invariant_failures.append("provenance-not-bound")
    if not evidence.compatibility_fallback_preserved:
        invariant_failures.append("compatibility-fallback-not-preserved")
    if evidence.trust_or_authority_widened:
        invariant_failures.append("trust-or-authority-widened")

    parent_blocked = spec.parent is not None and not evidence.parent_earned
    software_ready = not missing_software and not invariant_failures
    earned = software_ready and not missing_external and not parent_blocked

    if invariant_failures:
        state = "refused"
        next_gate = invariant_failures[0]
    elif missing_software:
        state = "prepare-software"
        next_gate = missing_software[0]
    elif parent_blocked:
        state = "software-ready-parent-blocked"
        next_gate = f"{spec.parent}-earned"
    elif missing_external:
        state = "software-ready-external-boundary"
        next_gate = missing_external[0]
    else:
        state = "earned"
        next_gate = "next-generation-selection"

    return {
        "generation": spec.name,
        "parent": spec.parent,
        "state": state,
        "software_ready": software_ready,
        "earned": earned,
        "safe_parallel_preparation_allowed": not invariant_failures,
        "missing_software": missing_software,
        "missing_external": missing_external,
        "parent_earned_required": spec.parent is not None,
        "parent_blocked": parent_blocked,
        "invariant_failures": invariant_failures,
        "next_gate": next_gate,
        "grants_execution_authority": False,
        "grants_mutation_authority": False,
        "infers_physical_proof": False,
        "may_promote_candidate": False,
    }


def generation_field(evidence_by_generation: Mapping[str, GenerationEvidence]) -> list[dict]:
    """Return Gen1->Gen3 state in dependency order for Future Branch consumers."""
    field: list[dict] = []
    for name in ("gen1", "gen2", "gen3"):
        evidence = evidence_by_generation.get(name)
        if evidence is None:
            spec = GENERATION_SPECS[name]
            evidence = GenerationEvidence(
                generation=name,
                software={},
                external={},
                parent_earned=False,
            )
        field.append(evaluate_generation(evidence))
    return field
