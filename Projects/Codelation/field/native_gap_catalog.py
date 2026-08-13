from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

from field_native_vm import NativeExample


CATALOG_REVISION = "aurum-native-gap-catalog-v1"
EXTERNAL_SPEC_SCHEMA = "aurum-native-semantic-gap-v0"
_SPEC_DIR = Path(__file__).resolve().parents[1] / "autobuild" / "native_gap_specs"


@dataclass(frozen=True)
class NativeSemanticGap:
    name: str
    parameters: tuple[str, ...]
    examples: tuple[NativeExample, ...]
    invocation_arguments: Mapping[str, object]
    next_gap: str
    purpose: str
    principles: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ("pure", "deterministic", "no-io", "no-host-authority")
    max_synthesis_cost: int = 12


def _gaps() -> tuple[NativeSemanticGap, ...]:
    return (
        NativeSemanticGap(
            name="learning_delta_score",
            parameters=("before", "after"),
            examples=(
                NativeExample({"before": "field slush", "after": "field aurum slush"}, 1),
                NativeExample({"before": "a b", "after": "a c"}, 2),
                NativeExample({"before": "x y", "after": "x y"}, 0),
            ),
            invocation_arguments={"before": "field slush", "after": "field aurum slush"},
            next_gap="learning_overlap_score",
            purpose="Measure how many unique learning tokens changed between observations.",
            principles=("token order is not semantic", "duplicate tokens do not amplify change"),
            max_synthesis_cost=8,
        ),
        NativeSemanticGap(
            name="learning_overlap_score",
            parameters=("before", "after"),
            examples=(
                NativeExample({"before": "a b", "after": "a b c"}, 2),
                NativeExample({"before": "field slush", "after": "field aurum"}, 1),
                NativeExample({"before": "x", "after": "y"}, 0),
            ),
            invocation_arguments={"before": "field slush", "after": "field aurum slush"},
            next_gap="learning_union_size",
            purpose="Measure shared unique learning tokens between observations.",
            principles=("shared meaning is set-like",),
            max_synthesis_cost=8,
        ),
        NativeSemanticGap(
            name="learning_union_size",
            parameters=("before", "after"),
            examples=(
                NativeExample({"before": "a b", "after": "a b c"}, 3),
                NativeExample({"before": "field slush", "after": "field aurum"}, 3),
                NativeExample({"before": "x", "after": "x"}, 1),
            ),
            invocation_arguments={"before": "field slush", "after": "field aurum slush"},
            next_gap="learning_retention_ratio",
            purpose="Measure total unique learning vocabulary across two observations.",
            max_synthesis_cost=8,
        ),
        NativeSemanticGap(
            name="learning_retention_ratio",
            parameters=("before", "after"),
            examples=(
                NativeExample({"before": "a b", "after": "a b c"}, 2 / 3),
                NativeExample({"before": "field slush", "after": "field"}, 1 / 2),
                NativeExample({"before": "", "after": ""}, 0),
            ),
            invocation_arguments={"before": "a b", "after": "a b c"},
            next_gap="learning_novelty_ratio",
            purpose="Normalize retained shared learning by total observed vocabulary.",
            principles=("zero vocabulary yields zero ratio",),
            max_synthesis_cost=12,
        ),
        NativeSemanticGap(
            name="learning_novelty_ratio",
            parameters=("before", "after"),
            examples=(
                NativeExample({"before": "a b", "after": "a b c"}, 1 / 3),
                NativeExample({"before": "field slush", "after": "field"}, 1 / 2),
                NativeExample({"before": "x", "after": "x"}, 0),
                NativeExample({"before": "", "after": ""}, 0),
            ),
            invocation_arguments={"before": "a b", "after": "a b c"},
            next_gap="learning_stability_index",
            purpose="Normalize changed unique learning by total observed vocabulary.",
            principles=("zero vocabulary yields zero ratio",),
            max_synthesis_cost=12,
        ),
    )


_CATALOG = {gap.name: gap for gap in _gaps()}


def _validate_external_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_validate_external_value(item) for item in value]
    raise ValueError("external semantic examples may contain only bounded scalar/list values")


def _load_external_gap(name: str) -> NativeSemanticGap | None:
    if not name or not name.replace("_", "a").isalnum() or name[0].isdigit():
        return None
    path = _SPEC_DIR / f"{name}.json"
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != EXTERNAL_SPEC_SCHEMA or raw.get("name") != name:
        raise ValueError("invalid external semantic gap schema/name")
    forbidden = {"expression", "implementation", "source", "code", "command", "script"}
    if forbidden.intersection(raw):
        raise ValueError("external semantic gap must not contain implementation payloads")

    parameters_raw = raw.get("parameters")
    examples_raw = raw.get("examples")
    invocation_raw = raw.get("invocation_arguments")
    if not isinstance(parameters_raw, list) or not parameters_raw or not all(isinstance(item, str) and item for item in parameters_raw):
        raise ValueError("external semantic gap parameters invalid")
    parameters = tuple(parameters_raw)
    if len(set(parameters)) != len(parameters):
        raise ValueError("external semantic gap parameters duplicate")
    required = set(parameters)
    if not isinstance(examples_raw, list) or not examples_raw or len(examples_raw) > 64:
        raise ValueError("external semantic gap examples invalid")
    examples: list[NativeExample] = []
    for item in examples_raw:
        if not isinstance(item, dict) or not isinstance(item.get("arguments"), dict) or "expected" not in item:
            raise ValueError("external semantic gap example invalid")
        arguments = {str(key): _validate_external_value(value) for key, value in item["arguments"].items()}
        if set(arguments) != required:
            raise ValueError("external semantic gap example arguments mismatch")
        examples.append(NativeExample(arguments, _validate_external_value(item["expected"])))
    if not isinstance(invocation_raw, dict) or set(invocation_raw) != required:
        raise ValueError("external semantic gap invocation arguments mismatch")
    invocation = {str(key): _validate_external_value(value) for key, value in invocation_raw.items()}

    next_gap = str(raw.get("next_gap", ""))
    purpose = str(raw.get("purpose", ""))
    if not next_gap or not purpose:
        raise ValueError("external semantic gap next_gap/purpose required")
    principles_raw = raw.get("principles", [])
    constraints_raw = raw.get("constraints", ["pure", "deterministic", "no-io", "no-host-authority"])
    if not isinstance(principles_raw, list) or not all(isinstance(item, str) for item in principles_raw):
        raise ValueError("external semantic gap principles invalid")
    if not isinstance(constraints_raw, list) or not all(isinstance(item, str) for item in constraints_raw):
        raise ValueError("external semantic gap constraints invalid")
    cost = int(raw.get("max_synthesis_cost", 12))
    if cost < 1 or cost > 16:
        raise ValueError("external semantic gap synthesis bound invalid")

    return NativeSemanticGap(
        name=name,
        parameters=parameters,
        examples=tuple(examples),
        invocation_arguments=invocation,
        next_gap=next_gap,
        purpose=purpose[:512],
        principles=tuple(principles_raw[:32]),
        constraints=tuple(constraints_raw[:32]),
        max_synthesis_cost=cost,
    )


def get_native_semantic_gap(name: str) -> NativeSemanticGap | None:
    return _CATALOG.get(name) or _load_external_gap(name)


def native_semantic_gap_names() -> tuple[str, ...]:
    external = tuple(path.stem for path in _SPEC_DIR.glob("*.json")) if _SPEC_DIR.is_dir() else ()
    return tuple(sorted(set(_CATALOG).union(external)))


__all__ = [
    "CATALOG_REVISION",
    "EXTERNAL_SPEC_SCHEMA",
    "NativeSemanticGap",
    "get_native_semantic_gap",
    "native_semantic_gap_names",
]
