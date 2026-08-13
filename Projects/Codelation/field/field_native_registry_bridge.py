from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Sequence

from aurum_field import encode
from field_native_carrier import NativeProgramCarrier, make_native_program_carrier
from field_native_self_build import NativeGap
from field_native_vm import NativeVerification, compile_native, execute_native, verify_native
from self_build_registry import (
    VERIFIED,
    CapabilityArtifact,
    CapabilityRegistry,
    artifact_identity,
)


BRIDGE_REVISION = "aurum-field-native-registry-bridge-v0"


@dataclass(frozen=True)
class VerifiedNativeRegistryBuild:
    artifact_identity: str
    artifact: CapabilityArtifact
    carrier: NativeProgramCarrier
    verification_identity: str
    invocation_output: Any


def native_verification_identity(verification: NativeVerification) -> str:
    payload = {
        "revision": BRIDGE_REVISION,
        "program_identity": verification.program_identity,
        "tape_identity": verification.tape_identity,
        "examples": verification.examples,
        "passed": verification.passed,
        "verified": verification.verified,
    }
    return hashlib.sha256(encode(payload)).hexdigest()


def build_verified_native_registry_artifact(
    gap: NativeGap,
    *,
    invocation_arguments: Mapping[str, Any],
    node: str,
    registry: CapabilityRegistry | None = None,
) -> VerifiedNativeRegistryBuild:
    """Build a native capability and persist a durable VERIFIED registry record.

    This function never promotes the artifact. The returned Field carrier is the
    exact local carrier whose digest is recorded by the registry.
    """
    target = registry if registry is not None else CapabilityRegistry()
    program = compile_native(gap.parameters, gap.expression)
    verification = verify_native(program, gap.examples)
    if not verification.verified:
        raise ValueError(
            f"native verification failed: {verification.passed}/{verification.examples}"
        )
    invocation_output = execute_native(program, invocation_arguments)
    carrier = make_native_program_carrier(program)
    verification_identity = native_verification_identity(verification)

    candidate = CapabilityArtifact(
        capability=gap.name,
        local_variant_identity=program.tape_identity,
        carrier_sha256=carrier.carrier_sha256,
        node=node,
        semantic_contract=gap.purpose,
        evidence=(),
    )
    identity = target.add(candidate)
    verified = target.verify(
        identity,
        test_sha256=verification_identity,
        evidence=(
            "field-native-example-verification-pass",
            "field-native-carrier-canonical",
            "field-native-carrier-roundtrip-verifiable",
            "field-native-invocation-pass",
            "no-source-generation",
            "no-filesystem-build",
            "no-subprocess-test",
        ),
    )
    if verified.state != VERIFIED:
        raise ValueError("native registry bridge did not reach verified state")
    if artifact_identity(verified) != identity:
        raise ValueError("native registry artifact identity changed across verification")

    return VerifiedNativeRegistryBuild(
        artifact_identity=identity,
        artifact=verified,
        carrier=carrier,
        verification_identity=verification_identity,
        invocation_output=invocation_output,
    )


__all__ = [
    "BRIDGE_REVISION",
    "VerifiedNativeRegistryBuild",
    "build_verified_native_registry_artifact",
    "native_verification_identity",
]
