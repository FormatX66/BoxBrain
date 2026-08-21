from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Gene:
    """One portable piece of learned Aurum capability evidence."""

    name: str
    kind: str
    scope: str
    confidence: float
    verified_runs: int
    regression_free: bool
    payload_digest: str


@dataclass(frozen=True)
class RepresentationMetrics:
    semantic_states: int
    procedural_steps: int
    generated_machine_ops: int
    hand_authored_code_ops: int

    @property
    def machine_native_ratio(self) -> float:
        total = self.generated_machine_ops + self.hand_authored_code_ops
        return self.generated_machine_ops / total if total else 0.0

    @property
    def semantic_compression(self) -> float:
        total = self.semantic_states + self.procedural_steps
        return self.semantic_states / total if total else 0.0


def inherit_genes(
    genes: Iterable[Gene],
    *,
    min_confidence: float = 0.90,
    min_verified_runs: int = 2,
) -> tuple[Gene, ...]:
    """Build the next seed from proven portable knowledge only."""

    accepted: list[Gene] = []
    seen_payloads: set[str] = set()
    for gene in genes:
        if gene.scope != "portable":
            continue
        if gene.kind not in {"capability", "hardware-fact", "optimization", "failure-lesson"}:
            continue
        if not 0.0 <= gene.confidence <= 1.0:
            continue
        if gene.confidence < min_confidence:
            continue
        if gene.verified_runs < min_verified_runs:
            continue
        if not gene.regression_free:
            continue
        if not gene.payload_digest or gene.payload_digest in seen_payloads:
            continue
        accepted.append(gene)
        seen_payloads.add(gene.payload_digest)

    return tuple(sorted(accepted, key=lambda item: (item.kind, item.name, item.payload_digest)))


def representation_preference(candidate: RepresentationMetrics, baseline: RepresentationMetrics) -> bool:
    """Prefer less codelation only when machine-native and semantic density both improve."""

    return (
        candidate.machine_native_ratio > baseline.machine_native_ratio
        and candidate.semantic_compression > baseline.semantic_compression
    )
