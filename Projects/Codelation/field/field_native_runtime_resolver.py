from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from field_native_carrier import verify_native_program_carrier
from field_native_vm import NativeProgram, execute_native
from self_build_registry import PROMOTED, CapabilityArtifact


RESOLVER_REVISION = "aurum-field-native-runtime-resolver-v0"


class NativeResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedNativeCapability:
    capability: str
    local_variant_identity: str
    carrier_sha256: str
    program: NativeProgram


def resolve_promoted_native_capability(
    artifact: CapabilityArtifact,
    carrier: bytes,
) -> ResolvedNativeCapability:
    """Resolve only a locally promoted native carrier with matching evidence."""
    if artifact.state != PROMOTED:
        raise NativeResolutionError("native runtime resolution requires promoted artifact")
    if not artifact.learning_packet_identity:
        raise NativeResolutionError("promoted artifact is missing learning packet identity")
    program = verify_native_program_carrier(
        carrier,
        expected_sha256=artifact.carrier_sha256,
        expected_tape_identity=artifact.local_variant_identity,
    )
    return ResolvedNativeCapability(
        capability=artifact.capability,
        local_variant_identity=artifact.local_variant_identity,
        carrier_sha256=artifact.carrier_sha256,
        program=program,
    )


def invoke_resolved_native_capability(
    resolved: ResolvedNativeCapability,
    arguments: Mapping[str, Any],
) -> Any:
    return execute_native(resolved.program, arguments)


__all__ = [
    "RESOLVER_REVISION",
    "NativeResolutionError",
    "ResolvedNativeCapability",
    "invoke_resolved_native_capability",
    "resolve_promoted_native_capability",
]
