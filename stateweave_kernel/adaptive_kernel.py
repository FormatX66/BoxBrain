from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Callable, Mapping, MutableMapping, Sequence


ApplyFn = Callable[[MutableMapping[int, int], Mapping[int, int]], bool]
CompatibleFn = Callable[[Mapping[int, int]], bool]


@dataclass(slots=True)
class HardwareCandidate:
    action_id: int
    transition_id: int
    cost: int
    confidence: int
    reversible: bool
    apply: ApplyFn
    compatible: CompatibleFn = lambda state: True

    def rank(self) -> tuple[int, int, int]:
        # Cost remains primary in v0, then prefer higher confidence and stable ID.
        return (self.cost, -self.confidence, self.action_id)


@dataclass(frozen=True, slots=True)
class KernelReceipt:
    transition_id: int
    action_id: int
    before_hash: str
    after_hash: str
    confidence_before: int
    confidence_after: int


@dataclass(frozen=True, slots=True)
class CandidateFailure:
    transition_id: int
    action_id: int
    reason: str
    confidence_before: int
    confidence_after: int


@dataclass(frozen=True, slots=True)
class KernelRun:
    final_state: Mapping[int, int]
    receipts: tuple[KernelReceipt, ...]
    failures: tuple[CandidateFailure, ...]


class AdaptiveKernelFabric:
    """Experimental hardware realization layer for a StateWeave plan.

    The object intentionally knows only the small StateWeave protocol it needs:
    ``plan()``, transition IDs/effects, invariant checks, and goal checks. This
    keeps StateWeave as the semantic planner while this layer learns how a
    particular machine can realize each transition.
    """

    def __init__(self, initial_hardware_state: Mapping[int, int] | None = None) -> None:
        self.hardware_state: dict[int, int] = dict(initial_hardware_state or {})
        self._candidates: dict[int, list[HardwareCandidate]] = {}

    def register(self, candidate: HardwareCandidate) -> None:
        if candidate.cost < 0:
            raise ValueError("candidate cost cannot be negative")
        if not 0 <= candidate.confidence <= 1000:
            raise ValueError("confidence must be between 0 and 1000")
        self._candidates.setdefault(candidate.transition_id, []).append(candidate)

    def candidates_for(self, transition_id: int) -> tuple[HardwareCandidate, ...]:
        return tuple(self._candidates.get(transition_id, ()))

    def execute_weave(self, weave, max_candidates_per_transition: int = 8) -> KernelRun:
        plan = weave.plan()
        logical_state = dict(weave.state)
        if not self.hardware_state:
            self.hardware_state.update(logical_state)

        receipts: list[KernelReceipt] = []
        failures: list[CandidateFailure] = []

        for transition in plan:
            expected = transition.apply(logical_state)
            candidates = [
                c
                for c in self._candidates.get(transition.transition_id, ())
                if c.compatible(self.hardware_state)
            ]
            candidates.sort(key=lambda c: c.rank())
            if not candidates:
                raise RuntimeError(
                    f"no compatible hardware candidate for transition {transition.transition_id}"
                )

            accepted = False
            for candidate in candidates[:max_candidates_per_transition]:
                before_state = dict(self.hardware_state)
                before_hash = _digest(before_state)
                confidence_before = candidate.confidence

                try:
                    claimed_success = bool(candidate.apply(self.hardware_state, expected))
                except Exception as exc:  # bounded experimental carrier failure
                    claimed_success = False
                    reason = f"exception:{type(exc).__name__}"
                else:
                    reason = "reported_failure" if not claimed_success else "verification_mismatch"

                verified = claimed_success and _effects_match(
                    transition.effects, self.hardware_state, expected
                )
                invariants_ok = verified and weave.invariants_hold(self.hardware_state)

                if verified and invariants_ok:
                    candidate.confidence = min(1000, candidate.confidence + 25)
                    receipts.append(
                        KernelReceipt(
                            transition_id=transition.transition_id,
                            action_id=candidate.action_id,
                            before_hash=before_hash,
                            after_hash=_digest(self.hardware_state),
                            confidence_before=confidence_before,
                            confidence_after=candidate.confidence,
                        )
                    )
                    logical_state = expected
                    accepted = True
                    break

                if verified and not invariants_ok:
                    reason = "invariant_violation"

                candidate.confidence = max(0, candidate.confidence - 100)
                if candidate.reversible:
                    self.hardware_state.clear()
                    self.hardware_state.update(before_state)
                else:
                    # A non-reversible failed candidate ends this simulated run;
                    # v0 does not pretend it can safely recover unknown mutation.
                    failures.append(
                        CandidateFailure(
                            transition_id=transition.transition_id,
                            action_id=candidate.action_id,
                            reason=reason,
                            confidence_before=confidence_before,
                            confidence_after=candidate.confidence,
                        )
                    )
                    raise RuntimeError(
                        f"non-reversible candidate {candidate.action_id} failed verification"
                    )

                failures.append(
                    CandidateFailure(
                        transition_id=transition.transition_id,
                        action_id=candidate.action_id,
                        reason=reason,
                        confidence_before=confidence_before,
                        confidence_after=candidate.confidence,
                    )
                )

            if not accepted:
                raise RuntimeError(
                    f"no hardware candidate verified transition {transition.transition_id}"
                )

        if not weave.goals_hold(self.hardware_state):
            raise RuntimeError("hardware run completed without satisfying StateWeave goals")
        if not weave.invariants_hold(self.hardware_state):
            raise RuntimeError("hardware run completed with violated StateWeave invariant")

        return KernelRun(dict(self.hardware_state), tuple(receipts), tuple(failures))


def _effects_match(effects: Sequence, actual: Mapping[int, int], expected: Mapping[int, int]) -> bool:
    for effect in effects:
        if actual.get(effect.node, 0) != expected.get(effect.node, 0):
            return False
    return True


def _digest(state: Mapping[int, int]) -> str:
    payload = bytearray()
    for node, value in sorted((int(k), int(v)) for k, v in state.items()):
        payload += node.to_bytes(4, "little", signed=False)
        payload += value.to_bytes(8, "little", signed=True)
    return sha256(payload).hexdigest()
