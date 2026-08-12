#!/usr/bin/env python3
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class Goal:
    name: str
    need: int
    cost: int
    risk: int
    blocked: bool=False

def choose_next(goals: Iterable[Goal]) -> Goal | None:
    viable=[g for g in goals if not g.blocked]
    if not viable:
        return None
    return sorted(viable,key=lambda g:(-g.need,g.cost,g.risk,g.name))[0]

DEFAULT_GOALS=(
    Goal("Hive Event Integration",10,2,1),
    Goal("Pi Deployment Verification",9,2,1,blocked=True),
    Goal("Capability Self-Inventory",7,1,0),
)
