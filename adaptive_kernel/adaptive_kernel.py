from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Callable, Mapping


State = dict[int, int]
Verifier = Callable[[Mapping[int, int]], bool]
Realizer = Callable[[State], State]


@dataclass(slots=True)
class Candidate:
    candidate_id: int
    cost: int
    confidence: int
    reversible: bool
    realize: Realizer


@dataclass(slots=True)
class Outcome:
    candidate_id: int
    success: bool
    before_hash: str
    after_hash: str
    rolled_back: bool = False


@dataclass(slots=True)
class AdaptiveKernel:
    state: State
    confidence: dict[int, int] = field(default_factory=dict)

    def rank(self, candidates: list[Candidate]) -> list[Candidate]:
        def key(candidate: Candidate) -> tuple[int, int, int]:
            learned = self.confidence.get(candidate.candidate_id, candidate.confidence)
            return (-learned, candidate.cost, candidate.candidate_id)
        return sorted(candidates, key=key)

    def realize(
        self,
        candidates: list[Candidate],
        verify: Verifier,
        invariant: Verifier | None = None,
    ) -> tuple[State, list[Outcome]]:
        attempts: list[Outcome] = []
        for candidate in self.rank(candidates):
            before = dict(self.state)
            before_hash = _digest(before)
            proposed = candidate.realize(dict(before))
            safe = invariant(proposed) if invariant is not None else True
            success = safe and verify(proposed)
            rolled_back = False
            if success:
                self.state = proposed
                self.confidence[candidate.candidate_id] = min(
                    100, self.confidence.get(candidate.candidate_id, candidate.confidence) + 5
                )
            else:
                self.confidence[candidate.candidate_id] = max(
                    0, self.confidence.get(candidate.candidate_id, candidate.confidence) - 20
                )
                if candidate.reversible:
                    self.state = before
                    rolled_back = True
                else:
                    raise RuntimeError(
                        f"candidate {candidate.candidate_id} failed and is not reversible"
                    )
            attempts.append(
                Outcome(
                    candidate_id=candidate.candidate_id,
                    success=success,
                    before_hash=before_hash,
                    after_hash=_digest(self.state),
                    rolled_back=rolled_back,
                )
            )
            if success:
                return dict(self.state), attempts
        raise RuntimeError("no candidate produced a verified safe outcome")


def _digest(state: Mapping[int, int]) -> str:
    payload = b"".join(
        int(k).to_bytes(4, "little", signed=False)
        + int(v).to_bytes(8, "little", signed=True)
        for k, v in sorted(state.items())
    )
    return sha256(payload).hexdigest()
