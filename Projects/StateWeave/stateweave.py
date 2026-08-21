"""StateWeave generation-0 prototype.

A deterministic machine-state representation and transition engine. This lane is
standalone on purpose: it does not import or depend on the Adaptive Kernel lane.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Mapping

Scalar = bool | int | float | str | None


def _canonical(mapping: Mapping[str, Scalar]) -> tuple[tuple[str, Scalar], ...]:
    return tuple(sorted(mapping.items(), key=lambda item: item[0]))


@dataclass(frozen=True)
class State:
    values: tuple[tuple[str, Scalar], ...]

    @classmethod
    def from_mapping(cls, values: Mapping[str, Scalar]) -> "State":
        return cls(_canonical(values))

    def as_dict(self) -> dict[str, Scalar]:
        return dict(self.values)

    def digest(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Transition:
    name: str
    requires: tuple[tuple[str, Scalar], ...]
    writes: tuple[tuple[str, Scalar], ...]

    @classmethod
    def build(
        cls,
        name: str,
        *,
        requires: Mapping[str, Scalar] | None = None,
        writes: Mapping[str, Scalar] | None = None,
    ) -> "Transition":
        return cls(name, _canonical(requires or {}), _canonical(writes or {}))

    def enabled(self, state: State) -> bool:
        current = state.as_dict()
        return all(current.get(key) == value for key, value in self.requires)

    def apply(self, state: State) -> State:
        if not self.enabled(state):
            raise ValueError(f"transition {self.name!r} requirements are not satisfied")
        updated = state.as_dict()
        updated.update(dict(self.writes))
        return State.from_mapping(updated)


@dataclass(frozen=True)
class TraceStep:
    transition: str
    before: str
    after: str


def run(initial: State, transitions: Iterable[Transition]) -> tuple[State, tuple[TraceStep, ...]]:
    state = initial
    trace: list[TraceStep] = []
    for transition in transitions:
        before = state.digest()
        state = transition.apply(state)
        trace.append(TraceStep(transition.name, before, state.digest()))
    return state, tuple(trace)
