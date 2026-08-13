from __future__ import annotations

import sys
import unittest
from pathlib import Path

FIELD = Path(__file__).resolve().parents[1] / "field"
sys.path.insert(0, str(FIELD))

from field_native_carrier import verify_native_program_carrier
from field_native_registry_bridge import build_verified_native_registry_artifact
from field_native_self_build import first_native_gap
from field_native_vm import execute_native
from self_build_registry import VERIFIED, CapabilityRegistry


class FieldNativeRegistryBridgeTests(unittest.TestCase):
    def test_verified_registry_artifact_is_backed_by_real_native_carrier(self):
        registry = CapabilityRegistry()
        built = build_verified_native_registry_artifact(
            first_native_gap(),
            invocation_arguments={"text": "SLUSH Field field Aurum slush"},
            node="test-node",
            registry=registry,
        )
        self.assertEqual(built.artifact.state, VERIFIED)
        self.assertEqual(built.artifact.carrier_sha256, built.carrier.carrier_sha256)
        self.assertEqual(built.artifact.local_variant_identity, built.carrier.tape_identity)
        restored = verify_native_program_carrier(
            built.carrier.carrier,
            expected_sha256=built.artifact.carrier_sha256,
            expected_tape_identity=built.artifact.local_variant_identity,
        )
        self.assertEqual(
            execute_native(restored, {"text": "SLUSH Field field Aurum slush"}),
            "aurum field slush",
        )
        self.assertEqual(len(registry.artifacts()), 1)

    def test_bridge_does_not_promote(self):
        built = build_verified_native_registry_artifact(
            first_native_gap(),
            invocation_arguments={"text": "Field Slush"},
            node="test-node",
        )
        self.assertEqual(built.artifact.state, VERIFIED)
        self.assertIsNone(built.artifact.learning_packet_identity)


if __name__ == "__main__":
    unittest.main(verbosity=2)
