from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


CATALOG_REVISION = "aurum-builder-capability-catalog-v0"


@dataclass(frozen=True)
class BuilderCapabilityDescriptor:
    name: str
    module: str
    callable_name: str
    provides: frozenset[str]
    constraints: frozenset[str]
    authority: str = "none"


@dataclass(frozen=True)
class BuilderCapabilityCandidate:
    name: str
    module: str
    callable_name: str
    matched: tuple[str, ...]
    missing: tuple[str, ...]
    coverage: float
    authority: str


def default_builder_capabilities() -> tuple[BuilderCapabilityDescriptor, ...]:
    """Describe reusable local builder substrate without invoking it.

    This is an inventory only. Discovery does not route work, execute a callable,
    grant permission, verify an artifact, or promote a capability.
    """
    return (
        BuilderCapabilityDescriptor(
            name="io-plan",
            module="io_fabric",
            callable_name="plan_io",
            provides=frozenset(
                {
                    "bounded-token-selection",
                    "declarative-fact-binding",
                    "deterministic-conditional-selection",
                    "least-privilege-ranking",
                    "permission-aware-selection",
                    "semantic-port-selection",
                }
            ),
            constraints=frozenset(
                {
                    "pure-decision",
                    "deterministic",
                    "no-host-authority",
                    "permission-does-not-equal-authority",
                }
            ),
            authority="none",
        ),
    )


def find_builder_capability_candidates(
    requirements: Iterable[str],
    *,
    catalog: Iterable[BuilderCapabilityDescriptor] | None = None,
) -> tuple[BuilderCapabilityCandidate, ...]:
    required = frozenset(str(item) for item in requirements if str(item))
    if not required:
        return ()
    candidates: list[BuilderCapabilityCandidate] = []
    for descriptor in catalog or default_builder_capabilities():
        matched = tuple(sorted(required & descriptor.provides))
        if not matched:
            continue
        missing = tuple(sorted(required - descriptor.provides))
        candidates.append(
            BuilderCapabilityCandidate(
                name=descriptor.name,
                module=descriptor.module,
                callable_name=descriptor.callable_name,
                matched=matched,
                missing=missing,
                coverage=len(matched) / len(required),
                authority=descriptor.authority,
            )
        )
    return tuple(
        sorted(
            candidates,
            key=lambda item: (-item.coverage, len(item.missing), item.authority != "none", item.name),
        )
    )


__all__ = [
    "CATALOG_REVISION",
    "BuilderCapabilityCandidate",
    "BuilderCapabilityDescriptor",
    "default_builder_capabilities",
    "find_builder_capability_candidates",
]
