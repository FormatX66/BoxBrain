from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import product
from math import prod
from typing import Callable, Hashable, Iterable, Mapping, Sequence


State = Mapping[str, str]
Predicate = Callable[[State], bool]
Signature = Callable[[State], Hashable]


@dataclass(frozen=True)
class Variable:
    """A finite variable that Aurum can exhaustively reason about in the test world."""

    name: str
    values: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("variable name must not be empty")
        if not self.values:
            raise ValueError(f"variable {self.name!r} must have at least one value")
        if len(set(self.values)) != len(self.values):
            raise ValueError(f"variable {self.name!r} contains duplicate values")


@dataclass(frozen=True)
class Constraint:
    """A rule that removes impossible or intentionally unsupported combinations."""

    name: str
    predicate: Predicate
    rationale: str


@dataclass(frozen=True)
class ConvergenceStage:
    """A downstream equivalence relation over otherwise distinct machine states."""

    name: str
    signature: Signature


@dataclass(frozen=True)
class SolveReport:
    raw_states: int
    valid_states: int
    pruned_states: int
    pruned_by_rule: tuple[tuple[str, int], ...]
    convergence: tuple[tuple[str, int], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "raw_states": self.raw_states,
            "valid_states": self.valid_states,
            "pruned_states": self.pruned_states,
            "pruned_by_rule": dict(self.pruned_by_rule),
            "convergence": [
                {"stage": stage, "equivalence_classes": classes}
                for stage, classes in self.convergence
            ],
        }


class FiniteStateSolver:
    """Enumerate bounded variables, prune invalid states, then collapse equivalent paths.

    The important property is not brute force for its own sake.  Early machine states can
    differ while later states no longer depend on those differences.  Each convergence
    stage therefore describes which distinctions still matter at that point in execution.
    """

    def __init__(
        self,
        variables: Sequence[Variable],
        constraints: Sequence[Constraint] = (),
        convergence_stages: Sequence[ConvergenceStage] = (),
    ) -> None:
        if not variables:
            raise ValueError("at least one variable is required")
        names = [variable.name for variable in variables]
        if len(set(names)) != len(names):
            raise ValueError("variable names must be unique")
        self.variables = tuple(variables)
        self.constraints = tuple(constraints)
        self.convergence_stages = tuple(convergence_stages)

    @property
    def raw_state_count(self) -> int:
        return prod(len(variable.values) for variable in self.variables)

    def iter_valid_states(self) -> Iterable[dict[str, str]]:
        names = tuple(variable.name for variable in self.variables)
        domains = tuple(variable.values for variable in self.variables)
        for values in product(*domains):
            state = dict(zip(names, values, strict=True))
            if all(constraint.predicate(state) for constraint in self.constraints):
                yield state

    def rejection_reasons(self, state: State) -> tuple[str, ...]:
        return tuple(
            constraint.name
            for constraint in self.constraints
            if not constraint.predicate(state)
        )

    def is_valid(self, state: State) -> bool:
        expected = {variable.name for variable in self.variables}
        if set(state) != expected:
            return False
        for variable in self.variables:
            if state[variable.name] not in variable.values:
                return False
        return not self.rejection_reasons(state)

    def solve(self) -> SolveReport:
        names = tuple(variable.name for variable in self.variables)
        domains = tuple(variable.values for variable in self.variables)
        valid_states: list[dict[str, str]] = []
        pruned = Counter[str]()

        for values in product(*domains):
            state = dict(zip(names, values, strict=True))
            for constraint in self.constraints:
                if not constraint.predicate(state):
                    # Count the first decisive rule.  This keeps pruning totals exact even
                    # when one impossible state violates more than one constraint.
                    pruned[constraint.name] += 1
                    break
            else:
                valid_states.append(state)

        convergence: list[tuple[str, int]] = []
        previous_count = len(valid_states)
        for stage in self.convergence_stages:
            signatures = {stage.signature(state) for state in valid_states}
            count = len(signatures)
            if count > previous_count:
                raise ValueError(
                    f"convergence stage {stage.name!r} splits states instead of converging "
                    f"({count} > {previous_count})"
                )
            convergence.append((stage.name, count))
            previous_count = count

        valid_count = len(valid_states)
        return SolveReport(
            raw_states=self.raw_state_count,
            valid_states=valid_count,
            pruned_states=self.raw_state_count - valid_count,
            pruned_by_rule=tuple(sorted(pruned.items())),
            convergence=tuple(convergence),
        )
