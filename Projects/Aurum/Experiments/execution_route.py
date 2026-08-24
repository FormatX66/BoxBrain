"""Experimental execution-route layer for Future Branch.

Future Branch decides *what* state/action is likely useful next.  This module
ranks *how* the current context can actually carry that action out.  It is a
planner only: it grants no authority and performs no external side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class RouteKind(str, Enum):
    DIRECT_LOCAL = "direct-local"
    CONNECTED_CAPABILITY = "connected-capability"
    AUTHORIZED_RUNNER = "authorized-runner"
    WORKSPACE_HANDOFF = "workspace-handoff"
    HUMAN_ASSISTED = "human-assisted"


class RouteDisposition(str, Enum):
    EXECUTE = "execute"
    PREPARE = "prepare"
    ASK_HUMAN = "ask-human"
    WAIT = "wait"


@dataclass(frozen=True)
class ExecutionRoute:
    name: str
    kind: RouteKind
    available: bool
    authority_ready: bool
    expected_success: float
    evidence_quality: float
    autonomy: float
    reversibility: float
    risk: float
    setup_cost: float
    latency_cost: float
    human_steps: int = 0
    stale: bool = False

    def validate(self) -> None:
        if not self.name:
            raise ValueError("route name required")
        for value in (
            self.expected_success,
            self.evidence_quality,
            self.autonomy,
            self.reversibility,
            self.risk,
        ):
            if not 0 <= value <= 1:
                raise ValueError("normalized route values must be between 0 and 1")
        if self.setup_cost < 0 or self.latency_cost < 0:
            raise ValueError("route costs must be non-negative")
        if self.human_steps < 0:
            raise ValueError("human_steps must be non-negative")

    @property
    def requires_human(self) -> bool:
        return self.kind == RouteKind.HUMAN_ASSISTED or self.human_steps > 0


def route_score(route: ExecutionRoute) -> float:
    """Return bounded comparative utility for an execution route.

    Human effort is a real cost, but not an absolute prohibition.  A human path
    can still win when it is materially safer/faster or when machine routes are
    unavailable.  Stale routes never compete.
    """
    route.validate()
    if not route.available or route.stale:
        return float("-inf")

    capability = (
        0.34 * route.expected_success
        + 0.22 * route.evidence_quality
        + 0.20 * route.autonomy
        + 0.12 * route.reversibility
        + (0.12 if route.authority_ready else 0.0)
    )
    penalty = (
        0.32 * route.risk
        + 0.10 * route.setup_cost
        + 0.08 * route.latency_cost
        + 0.08 * min(route.human_steps, 5)
    )
    # Prefer machine-capable routes when utility is otherwise similar.
    machine_bonus = 0.10 if not route.requires_human else 0.0
    return capability + machine_bonus - penalty


def route_disposition(route: ExecutionRoute) -> RouteDisposition:
    route.validate()
    if not route.available or route.stale:
        return RouteDisposition.WAIT
    if route.requires_human:
        return RouteDisposition.ASK_HUMAN
    if route.authority_ready:
        return RouteDisposition.EXECUTE
    return RouteDisposition.PREPARE


def rank_execution_routes(routes: Iterable[ExecutionRoute], *, limit: int = 5) -> list[dict]:
    """Rank available routes while retaining useful alternates.

    The top route is the preferred carrier.  Alternatives stay warm so a failed
    connector/runner/handoff does not force fresh linear reasoning.
    """
    if limit < 1:
        raise ValueError("limit must be positive")
    values = list(routes)
    for route in values:
        route.validate()
    ranked = sorted(values, key=lambda item: (-route_score(item), item.name))[:limit]
    return [
        {
            "name": route.name,
            "kind": route.kind.value,
            "score": round(route_score(route), 6),
            "disposition": route_disposition(route).value,
            "available": route.available,
            "authority_ready": route.authority_ready,
            "requires_human": route.requires_human,
            "stale": route.stale,
        }
        for route in ranked
    ]


def preferred_route(routes: Iterable[ExecutionRoute]) -> ExecutionRoute | None:
    """Return the best non-stale available route, or None when no route exists."""
    values = list(routes)
    for route in values:
        route.validate()
    candidates = [route for route in values if route.available and not route.stale]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (route_score(item), item.name))
