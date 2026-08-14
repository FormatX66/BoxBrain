from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from capacity_mesh import Node, RewardSignal, WorkItem, assign_parallel, score_reward


DEFAULT_SPLIT_MODES = (
    "safe",
    "adventurous",
    "independent-verifier",
)


@dataclass(frozen=True)
class Bottleneck:
    """A blocked or uncertain frontier that should branch instead of serializing work."""

    name: str
    requires: frozenset[str]
    goal: str
    weight: int = 1
    modes: tuple[str, ...] = DEFAULT_SPLIT_MODES


@dataclass(frozen=True)
class SplitLane:
    bottleneck: str
    mode: str
    node: str
    requires: frozenset[str]
    work_name: str


@dataclass(frozen=True)
class FrontierPlan:
    bottlenecks: tuple[str, ...]
    lanes: tuple[SplitLane, ...]
    assignments: Mapping[str, tuple[str, ...]]
    unassigned: tuple[str, ...]
    missing_capabilities: frozenset[str]

    def lanes_for(self, bottleneck: str) -> tuple[SplitLane, ...]:
        return tuple(lane for lane in self.lanes if lane.bottleneck == bottleneck)


@dataclass(frozen=True)
class CandidateOutcome:
    bottleneck: str
    mode: str
    node: str
    reward: RewardSignal
    implementation_identity: str | None = None
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConvergenceResult:
    bottleneck: str
    accepted: bool
    selected_mode: str | None
    selected_node: str | None
    selected_implementation_identity: str | None
    verifier_nodes: tuple[str, ...]
    ranked_candidates: tuple[str, ...]
    reason: str


def _mode_priority(mode: str) -> int:
    if mode == "safe":
        return 3
    if mode == "independent-verifier":
        return 3
    if mode == "adventurous":
        return 2
    return 1


def split_frontier(
    bottlenecks: Iterable[Bottleneck],
    nodes: Sequence[Node],
) -> FrontierPlan:
    """Fan every independent bottleneck out together across all available capacity.

    This function intentionally plans the whole frontier in one assignment pass.
    A blocked item therefore cannot become a global barrier for unrelated work.
    Each bottleneck emits safe, adventurous, and independent-verifier paths by
    default; callers may add more modes without changing the scheduler.
    """

    ordered = tuple(sorted(bottlenecks, key=lambda item: item.name))
    work: list[WorkItem] = []
    work_meta: dict[str, tuple[str, str, frozenset[str]]] = {}

    for bottleneck in ordered:
        seen_modes: set[str] = set()
        for mode in bottleneck.modes:
            if not mode or mode in seen_modes:
                continue
            seen_modes.add(mode)
            name = f"bottleneck:{bottleneck.name}:{mode}"
            work_meta[name] = (bottleneck.name, mode, bottleneck.requires)
            work.append(
                WorkItem(
                    name=name,
                    requires=bottleneck.requires,
                    weight=max(1, bottleneck.weight) * 10 + _mode_priority(mode),
                )
            )

    assignment = assign_parallel(work, nodes)
    lanes: list[SplitLane] = []
    for node, names in sorted(assignment.assignments.items()):
        for name in names:
            bottleneck_name, mode, requires = work_meta[name]
            lanes.append(
                SplitLane(
                    bottleneck=bottleneck_name,
                    mode=mode,
                    node=node,
                    requires=requires,
                    work_name=name,
                )
            )

    lanes.sort(key=lambda lane: (lane.bottleneck, lane.mode, lane.node))
    return FrontierPlan(
        bottlenecks=tuple(item.name for item in ordered),
        lanes=tuple(lanes),
        assignments=assignment.assignments,
        unassigned=assignment.unassigned,
        missing_capabilities=assignment.missing_capabilities,
    )


def split_bottleneck(bottleneck: Bottleneck, nodes: Sequence[Node]) -> FrontierPlan:
    """Convenience wrapper for one bottleneck; still uses the same frontier scheduler."""

    return split_frontier((bottleneck,), nodes)


def converge_bottleneck(
    bottleneck: Bottleneck,
    outcomes: Iterable[CandidateOutcome],
    *,
    require_independent_verifier: bool = True,
) -> ConvergenceResult:
    """Converge split paths by evidence, not by which path finished first."""

    matching = tuple(outcome for outcome in outcomes if outcome.bottleneck == bottleneck.name)
    verified_verifiers = tuple(
        sorted(
            {
                outcome.node
                for outcome in matching
                if outcome.mode == "independent-verifier"
                and outcome.reward.verified
                and not outcome.reward.false_claim
                and not outcome.reward.unsafe_or_unauthorized
            }
        )
    )

    candidates = [
        outcome
        for outcome in matching
        if outcome.mode != "independent-verifier"
        and outcome.implementation_identity
        and outcome.reward.verified
        and not outcome.reward.false_claim
        and not outcome.reward.unsafe_or_unauthorized
    ]
    candidates.sort(
        key=lambda outcome: (
            -score_reward(outcome.reward),
            -_mode_priority(outcome.mode),
            outcome.mode,
            outcome.node,
            outcome.implementation_identity or "",
        )
    )
    ranked = tuple(
        f"{outcome.mode}:{outcome.node}:{outcome.implementation_identity}:{score_reward(outcome.reward)}"
        for outcome in candidates
    )

    if require_independent_verifier and not verified_verifiers:
        return ConvergenceResult(
            bottleneck=bottleneck.name,
            accepted=False,
            selected_mode=None,
            selected_node=None,
            selected_implementation_identity=None,
            verifier_nodes=(),
            ranked_candidates=ranked,
            reason="independent-verification-missing",
        )
    if not candidates:
        return ConvergenceResult(
            bottleneck=bottleneck.name,
            accepted=False,
            selected_mode=None,
            selected_node=None,
            selected_implementation_identity=None,
            verifier_nodes=verified_verifiers,
            ranked_candidates=(),
            reason="no-verified-candidate",
        )

    selected = candidates[0]
    return ConvergenceResult(
        bottleneck=bottleneck.name,
        accepted=True,
        selected_mode=selected.mode,
        selected_node=selected.node,
        selected_implementation_identity=selected.implementation_identity,
        verifier_nodes=verified_verifiers,
        ranked_candidates=ranked,
        reason="verified-convergence",
    )


__all__ = [
    "Bottleneck",
    "CandidateOutcome",
    "ConvergenceResult",
    "DEFAULT_SPLIT_MODES",
    "FrontierPlan",
    "SplitLane",
    "converge_bottleneck",
    "split_bottleneck",
    "split_frontier",
]
