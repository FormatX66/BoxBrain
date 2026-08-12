#!/usr/bin/env python3
from dataclasses import dataclass
from typing import Any, Callable
from capability_registry import DEFAULT as REGISTRY
from state_diff import summary as state_diff
from human_projection import project

@dataclass
class CycleResult:
    selected_capability: str | None
    before: Any
    after: Any
    diff: dict
    projection: Any
    status: str

def choose(required_permissions: tuple[str,...]):
    return REGISTRY.choose(required_permissions)

def run_cycle(before: Any, *, required_permissions: tuple[str,...], action: Callable[[Any], Any] | None = None) -> CycleResult:
    cap=choose(required_permissions)
    if cap is None:
        return CycleResult(None,before,before,state_diff(before,before),project(before),"no-compatible-capability")
    after=before if action is None else action(before)
    d=state_diff(before,after)
    return CycleResult(cap.name,before,after,d,project(after),"changed" if d["changed"] else "verified-no-change")
