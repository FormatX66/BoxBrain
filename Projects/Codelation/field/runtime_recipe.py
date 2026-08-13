from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

from aurum_field import Field

RUNTIME_RECIPE_SCHEMA = "aurum.runtime.recipe.v0"


@dataclass(frozen=True)
class RuntimeComponent:
    name: str
    requires: frozenset[str]
    provides: frozenset[str]
    optional: bool = False


@dataclass(frozen=True)
class RuntimeRecipe:
    target_identity: str
    requested: tuple[str, ...]
    components: tuple[str, ...]
    provides: tuple[str, ...]
    missing: tuple[str, ...]
    identity: str


def default_components() -> tuple[RuntimeComponent, ...]:
    return (
        RuntimeComponent(
            "field-core",
            frozenset({"cpu-capacity", "memory-capacity", "storage-capacity"}),
            frozenset({"field-state", "content-addressed-state"}),
        ),
        RuntimeComponent(
            "event-handoff",
            frozenset({"field-state"}),
            frozenset({"event-continuation", "claimable-work"}),
        ),
        RuntimeComponent(
            "slush-store",
            frozenset({"storage-capacity"}),
            frozenset({"slush-state"}),
        ),
        RuntimeComponent(
            "network-carrier",
            frozenset({"network-capacity"}),
            frozenset({"remote-capability-transport"}),
            optional=True,
        ),
        RuntimeComponent(
            "human-text-io",
            frozenset({"human-text-input", "human-readable"}),
            frozenset({"human-dialogue"}),
            optional=True,
        ),
        RuntimeComponent(
            "model-gateway",
            frozenset({"model-access"}),
            frozenset({"language-reasoning"}),
            optional=True,
        ),
        RuntimeComponent(
            "isolated-host-carrier",
            frozenset({"isolation-carrier"}),
            frozenset({"isolated-prototype-runtime"}),
            optional=True,
        ),
    )


def derive_runtime_recipe(
    target_identity: str,
    observed: Iterable[str],
    requested: Iterable[str],
    *,
    components: tuple[RuntimeComponent, ...] | None = None,
) -> RuntimeRecipe:
    if not target_identity:
        raise ValueError("target identity is required")
    available = set(observed)
    wanted = set(requested)
    selected: list[str] = []
    provided: set[str] = set(available)
    library = components or default_components()

    changed = True
    while changed:
        changed = False
        for item in sorted(library, key=lambda component: component.name):
            if item.name in selected:
                continue
            if item.requires <= provided and (not item.optional or item.provides & wanted):
                selected.append(item.name)
                before = len(provided)
                provided.update(item.provides)
                changed = changed or len(provided) != before

    missing = tuple(sorted(wanted - provided))
    payload = {
        "schema": RUNTIME_RECIPE_SCHEMA,
        "target_identity": target_identity,
        "requested": sorted(wanted),
        "components": selected,
        "provides": sorted(provided),
        "missing": list(missing),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    identity = hashlib.blake2s(b"AURUM-RUNTIME-RECIPE-0\x00" + raw, digest_size=32).hexdigest()
    return RuntimeRecipe(
        target_identity=target_identity,
        requested=tuple(sorted(wanted)),
        components=tuple(selected),
        provides=tuple(sorted(provided)),
        missing=missing,
        identity=identity,
    )


def runtime_recipe_field(recipe: RuntimeRecipe) -> Field:
    field = Field()
    recipe_ref = field.add(
        "capability",
        {
            "schema": RUNTIME_RECIPE_SCHEMA,
            "identity": recipe.identity,
            "target_identity": recipe.target_identity,
            "requested": list(recipe.requested),
            "components": list(recipe.components),
            "provides": list(recipe.provides),
            "missing": list(recipe.missing),
            "declarative_only": True,
            "host_boot_change": False,
        },
    )
    field.add(
        "view",
        {"name": "aurum-runtime-recipe", "recipe": recipe_ref},
    )
    return field


__all__ = [
    "RUNTIME_RECIPE_SCHEMA",
    "RuntimeComponent",
    "RuntimeRecipe",
    "default_components",
    "derive_runtime_recipe",
    "runtime_recipe_field",
]
