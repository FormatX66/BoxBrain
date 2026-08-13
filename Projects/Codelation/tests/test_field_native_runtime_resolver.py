from __future__ import annotations

import sys
import unittest
from pathlib import Path

FIELD = Path(__file__).resolve().parents[1] / "field"
sys.path.insert(0, str(FIELD))

from field_native_carrier import make_native_program_carrier
from field_native_runtime_resolver import (
    NativeResolutionError,
    invoke_resolved_native_capability,
    resolve_promoted_native_capability,
)
from field_native_vm import compile_native
from self_build_registry import CapabilityArtifact, CapabilityRegistry


class FieldNativeRuntimeResolverTests(unittest.TestCase):
    def setUp(self):
        self.program = compile_native(
            ("text",),
            {"op": "length", "value": {"op": "split", "value": {"op": "input", "name": "text"}}},
        )
        self.carrier = make_native_program_carrier(self.program)
        self.registry = CapabilityRegistry()
        candidate = CapabilityArtifact(
            capability="token_count",
            local_variant_identity=self.program.tape_identity,
            carrier_sha256=self.carrier.carrier_sha256,
            node="test-node",
            semantic_contract="Count whitespace-delimited learning tokens.",
        )
        self.identity = self.registry.add(candidate)
        self.verified = self.registry.verify(
            self.identity,
            test_sha256="verified-test-digest",
            evidence=("native-tests-pass",),
        )

    def test_verified_but_unpromoted_artifact_cannot_resolve(self):
        with self.assertRaises(NativeResolutionError):
            resolve_promoted_native_capability(self.verified, self.carrier.carrier)

    def test_promoted_matching_carrier_resolves_and_executes(self):
        promoted = self.registry.promote(
            self.identity,
            observed_carrier_sha256=self.carrier.carrier_sha256,
            learning_packet_identity="learning-packet-id",
        )
        resolved = resolve_promoted_native_capability(promoted, self.carrier.carrier)
        self.assertEqual(invoke_resolved_native_capability(resolved, {"text": "field aurum slush"}), 3)

    def test_tampered_carrier_is_rejected(self):
        promoted = self.registry.promote(
            self.identity,
            observed_carrier_sha256=self.carrier.carrier_sha256,
            learning_packet_identity="learning-packet-id",
        )
        damaged = bytearray(self.carrier.carrier)
        damaged[-1] ^= 1
        with self.assertRaises((NativeResolutionError, ValueError)):
            resolve_promoted_native_capability(promoted, bytes(damaged))


if __name__ == "__main__":
    unittest.main(verbosity=2)
