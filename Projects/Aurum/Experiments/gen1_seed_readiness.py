"""Evidence projector for Aurum Gen1 (the usable Everyone-OS seed).

This module converts explicit software evidence into the shared Gen1 generation
ladder.  It intentionally has no input capable of asserting Hopper boot,
Guardian rollback, or second-node usability, so CI/software evidence can never
manufacture those physical gates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from generation_seed_ladder import GenerationEvidence, evaluate_generation


REQUIRED_EVERYDAY_TRAITS = (
    "TR8:WEB",
    "TR8:FILES",
    "TR8:MEDIA",
    "TR8:WRITE",
    "TR8:INTENT",
    "TR8:CONNECT",
    "TR8:RECOVER",
)


def _revision(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a Git commit SHA")
    value = value.strip().lower()
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{name} must be a 40-character Git commit SHA")
    return value


@dataclass(frozen=True)
class Gen1SoftwareEvidence:
    source_revision: str
    carrier_revision: str
    traits: Mapping[str, bool] = field(default_factory=dict)
    graphical_shell_verified: bool = False
    intent_accessibility_verified: bool = False
    recovery_contract_verified: bool = False
    unattended_candidate_validation_verified: bool = False
    source_carrier_provenance_bound: bool = False
    lkg_preserved: bool = True
    recovery_preserved: bool = True
    compatibility_fallback_preserved: bool = True
    trust_or_authority_widened: bool = False


def project_gen1_software(evidence: Gen1SoftwareEvidence) -> dict:
    """Project software proof only; physical Gen1 gates are always left pending."""
    source_revision = _revision(evidence.source_revision, "source_revision")
    carrier_revision = _revision(evidence.carrier_revision, "carrier_revision")

    trait_results = {
        trait: evidence.traits.get(trait) is True
        for trait in REQUIRED_EVERYDAY_TRAITS
    }
    everyday_traits_verified = all(trait_results.values())
    provenance_bound = evidence.source_carrier_provenance_bound is True

    software = {
        "graphical_shell_contract": evidence.graphical_shell_verified is True,
        "everyday_traits_contract": everyday_traits_verified,
        "intent_accessibility_contract": evidence.intent_accessibility_verified is True,
        "recovery_contract": evidence.recovery_contract_verified is True,
        "unattended_candidate_validation": evidence.unattended_candidate_validation_verified is True,
    }

    ladder = evaluate_generation(
        GenerationEvidence(
            generation="gen1",
            software=software,
            # Deliberately no software path to physical evidence.
            external={},
            lkg_preserved=evidence.lkg_preserved is True,
            recovery_preserved=evidence.recovery_preserved is True,
            provenance_bound=provenance_bound,
            compatibility_fallback_preserved=evidence.compatibility_fallback_preserved is True,
            trust_or_authority_widened=evidence.trust_or_authority_widened is True,
        )
    )

    return {
        "schema": "aurum-gen1-software-readiness-v1",
        "source_revision": source_revision,
        "carrier_revision": carrier_revision,
        "source_carrier_provenance_bound": provenance_bound,
        "traits": trait_results,
        "software": software,
        "ladder": ladder,
        "physical_gates_supplied_by_this_projector": False,
        "hopper_physical_boot": False,
        "guardian_forced_rollback": False,
        "second_architecture_usable": False,
        "grants_write_authority": False,
        "grants_mutation_authority": False,
        "may_promote_candidate": False,
    }
