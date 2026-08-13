from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

from aurum_field import Field
from capacity_mesh import RewardSignal
from capability_wave import (
    CapabilityCompletion,
    UpgradeNode,
    emit_capability_wave,
)


SELF_BUILD_SCHEMA = "aurum-self-build-proof-v0"
_ALLOWED_OPS = frozenset({
    "input",
    "strip",
    "casefold",
    "split",
    "unique",
    "sort",
    "join",
})


class SelfBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class CapabilityExample:
    arguments: Mapping[str, Any]
    expected: Any


@dataclass(frozen=True)
class CapabilityGap:
    name: str
    parameters: tuple[str, ...]
    expression: Mapping[str, Any]
    examples: tuple[CapabilityExample, ...]
    purpose: str
    learned_principles: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class SelfBuildProof:
    gap_name: str
    candidate_sha256: str
    test_sha256: str
    promoted_sha256: str
    invocation_output: Any
    learning_packet_identity: str
    wave_id: str
    wave_targets: tuple[str, ...]
    next_gap: str
    stages: tuple[str, ...]


def _validate_identifier(value: str, *, label: str) -> None:
    if not value or not value.replace("_", "a").isalnum() or value[0].isdigit():
        raise SelfBuildError(f"invalid {label}: {value!r}")


def _validate_expression(expr: Mapping[str, Any], parameters: frozenset[str]) -> None:
    op = str(expr.get("op", ""))
    if op not in _ALLOWED_OPS:
        raise SelfBuildError(f"unsupported operation: {op}")
    if op == "input":
        name = str(expr.get("name", ""))
        if name not in parameters:
            raise SelfBuildError(f"unknown input: {name}")
        return
    source = expr.get("value")
    if not isinstance(source, Mapping):
        raise SelfBuildError(f"operation {op} requires mapping value")
    _validate_expression(source, parameters)
    if op == "join" and not isinstance(expr.get("separator", ""), str):
        raise SelfBuildError("join separator must be text")


def validate_gap(gap: CapabilityGap) -> None:
    _validate_identifier(gap.name, label="capability name")
    if not gap.parameters:
        raise SelfBuildError("at least one parameter is required")
    if len(set(gap.parameters)) != len(gap.parameters):
        raise SelfBuildError("duplicate parameters")
    for parameter in gap.parameters:
        _validate_identifier(parameter, label="parameter")
    _validate_expression(gap.expression, frozenset(gap.parameters))
    if not gap.examples:
        raise SelfBuildError("at least one example is required")
    required = set(gap.parameters)
    for example in gap.examples:
        if set(example.arguments) != required:
            raise SelfBuildError("example arguments must exactly match parameters")


def _render_expression(expr: Mapping[str, Any]) -> str:
    op = str(expr["op"])
    if op == "input":
        return str(expr["name"])
    inner = _render_expression(expr["value"])
    if op == "strip":
        return f"({inner}).strip()"
    if op == "casefold":
        return f"({inner}).casefold()"
    if op == "split":
        return f"({inner}).split()"
    if op == "unique":
        return f"list(dict.fromkeys({inner}))"
    if op == "sort":
        return f"sorted({inner})"
    if op == "join":
        separator = json.dumps(str(expr.get("separator", "")))
        return f"{separator}.join({inner})"
    raise SelfBuildError(f"cannot render operation: {op}")


def synthesize_module(gap: CapabilityGap) -> bytes:
    """Synthesize a pure Python capability from a validated declarative expression."""
    validate_gap(gap)
    body = _render_expression(gap.expression)
    params = ", ".join(gap.parameters)
    source = (
        "from __future__ import annotations\n\n"
        f"CAPABILITY = {gap.name!r}\n"
        f"PURPOSE = {gap.purpose!r}\n\n"
        f"def invoke({params}):\n"
        f"    return {body}\n"
    )
    return source.encode("utf-8")


def synthesize_tests(gap: CapabilityGap, module_name: str) -> bytes:
    validate_gap(gap)
    lines = [
        "from __future__ import annotations",
        "import importlib.util",
        "import pathlib",
        "import unittest",
        "",
        f"MODULE_NAME = {module_name!r}",
        "MODULE_PATH = pathlib.Path(__file__).with_name(MODULE_NAME + '.py')",
        "SPEC = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)",
        "MODULE = importlib.util.module_from_spec(SPEC)",
        "assert SPEC and SPEC.loader",
        "SPEC.loader.exec_module(MODULE)",
        "",
        "class GeneratedCapabilityTests(unittest.TestCase):",
    ]
    for index, example in enumerate(gap.examples):
        kwargs = ", ".join(
            f"{name}={example.arguments[name]!r}" for name in gap.parameters
        )
        lines.extend(
            [
                f"    def test_example_{index}(self):",
                f"        self.assertEqual(MODULE.invoke({kwargs}), {example.expected!r})",
            ]
        )
    lines.extend(["", "if __name__ == '__main__':", "    unittest.main(verbosity=2)", ""])
    return "\n".join(lines).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise SelfBuildError("generated module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_self_build(
    gap: CapabilityGap,
    *,
    invocation_arguments: Mapping[str, Any],
    nodes: Sequence[UpgradeNode],
    next_gap: str,
) -> SelfBuildProof:
    """Close one self-build loop entirely inside an isolated temporary runtime.

    The repository contains the synthesizer and declarative gap, not the generated
    capability implementation. Candidate source and generated tests exist only in
    the isolated build workspace until verification succeeds. Promotion here means
    copying the verified candidate into a separate temporary runtime directory.
    """
    validate_gap(gap)
    if set(invocation_arguments) != set(gap.parameters):
        raise SelfBuildError("invocation arguments do not match capability parameters")

    stages: list[str] = ["gap-observed"]
    module_name = "aurum_generated_" + gap.name
    with tempfile.TemporaryDirectory(prefix="aurum-self-build-") as temp:
        root = Path(temp)
        build = root / "build"
        runtime = root / "runtime"
        build.mkdir()
        runtime.mkdir()

        candidate = synthesize_module(gap)
        tests = synthesize_tests(gap, module_name)
        candidate_path = build / f"{module_name}.py"
        test_path = build / f"test_{module_name}.py"
        candidate_path.write_bytes(candidate)
        test_path.write_bytes(tests)
        stages.append("candidate-synthesized")
        stages.append("tests-synthesized")

        process = subprocess.run(
            [sys.executable, str(test_path)],
            cwd=build,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
            check=False,
        )
        if process.returncode != 0:
            raise SelfBuildError("generated capability failed generated tests:\n" + process.stdout)
        stages.append("candidate-verified")

        promoted = runtime / candidate_path.name
        shutil.copy2(candidate_path, promoted)
        if _sha256(promoted.read_bytes()) != _sha256(candidate):
            raise SelfBuildError("promotion digest mismatch")
        stages.append("candidate-promoted")

        module = _load_module(promoted, module_name + "_runtime")
        output = module.invoke(**dict(invocation_arguments))
        stages.append("promoted-capability-invoked")

        completion = CapabilityCompletion(
            capability=gap.name,
            source_node="github-actions-self-build",
            source_variant_identity=_sha256(candidate),
            requires=frozenset({"python-runtime"}),
            reward=RewardSignal(verified=True, reusable=True, generalized=True),
            evidence=(
                "generated-tests-pass",
                "promotion-digest-match",
                "promoted-capability-invoked",
            ),
            learned_principles=gap.learned_principles,
            constraints=gap.constraints,
            success_conditions=("generated examples pass", "runtime invocation succeeds"),
            failed_approaches=(),
        )
        wave = emit_capability_wave(completion, nodes)
        stages.append("learning-wave-emitted")
        stages.append("next-gap-emitted")

        return SelfBuildProof(
            gap_name=gap.name,
            candidate_sha256=_sha256(candidate),
            test_sha256=_sha256(tests),
            promoted_sha256=_sha256(promoted.read_bytes()),
            invocation_output=output,
            learning_packet_identity=wave.learning_packet_identity,
            wave_id=wave.wave_id,
            wave_targets=wave.target_nodes,
            next_gap=next_gap,
            stages=tuple(stages),
        )


def first_self_build_gap() -> CapabilityGap:
    """A small useful capability whose implementation does not exist in the repo."""
    return CapabilityGap(
        name="canonical_learning_tokens",
        parameters=("text",),
        expression={
            "op": "join",
            "separator": " ",
            "value": {
                "op": "sort",
                "value": {
                    "op": "unique",
                    "value": {
                        "op": "split",
                        "value": {
                            "op": "casefold",
                            "value": {
                                "op": "strip",
                                "value": {"op": "input", "name": "text"},
                            },
                        },
                    },
                },
            },
        },
        examples=(
            CapabilityExample({"text": "  Field field SLUSH  "}, "field slush"),
            CapabilityExample({"text": "Pi3 Morris GitHub Pi3"}, "github morris pi3"),
        ),
        purpose="Canonicalize learning vocabulary before semantic comparison.",
        learned_principles=(
            "canonical meaning should not depend on token order",
            "duplicate vocabulary should not amplify learning identity",
        ),
        constraints=("pure function", "no I/O", "no host authority"),
    )


def first_self_build_nodes() -> tuple[UpgradeNode, ...]:
    return (
        UpgradeNode("github-actions", frozenset({"python-runtime"})),
        UpgradeNode("gpt-reasoning", frozenset({"model-reasoning"})),
        UpgradeNode("Aurum-Morris", frozenset({"windows-local"})),
        UpgradeNode("BBPI4", frozenset({"arm-linux"}), available=False, verified=False),
        UpgradeNode("Pi3", frozenset({"arm-linux"}), available=False, verified=False),
    )


def run_first_self_build_proof() -> SelfBuildProof:
    return run_self_build(
        first_self_build_gap(),
        invocation_arguments={"text": "SLUSH Field field Aurum slush"},
        nodes=first_self_build_nodes(),
        next_gap="learning_delta_score",
    )


def self_build_proof_field(proof: SelfBuildProof) -> Field:
    field = Field()
    proof_ref = field.add(
        "fact",
        {
            "schema": SELF_BUILD_SCHEMA,
            "gap": proof.gap_name,
            "candidate_sha256": proof.candidate_sha256,
            "test_sha256": proof.test_sha256,
            "promoted_sha256": proof.promoted_sha256,
            "invocation_output": proof.invocation_output,
            "learning_packet_identity": proof.learning_packet_identity,
            "wave_id": proof.wave_id,
            "wave_targets": list(proof.wave_targets),
            "next_gap": proof.next_gap,
            "stages": list(proof.stages),
        },
    )
    field.add(
        "view",
        {
            "name": "aurum-first-self-build-proof",
            "proof": proof_ref,
            "candidate_matches_promoted": proof.candidate_sha256 == proof.promoted_sha256,
            "closed_loop": proof.stages[-1] == "next-gap-emitted",
        },
    )
    return field


__all__ = [
    "CapabilityExample",
    "CapabilityGap",
    "SELF_BUILD_SCHEMA",
    "SelfBuildError",
    "SelfBuildProof",
    "first_self_build_gap",
    "first_self_build_nodes",
    "run_first_self_build_proof",
    "run_self_build",
    "self_build_proof_field",
    "synthesize_module",
    "synthesize_tests",
    "validate_gap",
]
