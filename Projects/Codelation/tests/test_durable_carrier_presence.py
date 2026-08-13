from __future__ import annotations

import sys
import unittest
from pathlib import Path

FIELD = Path(__file__).resolve().parents[1] / "field"
sys.path.insert(0, str(FIELD))

from durable_carrier_presence import CarrierPresence, presence_field, verify_presence  # noqa: E402


class DurableCarrierPresenceTests(unittest.TestCase):
    def base(self, **changes):
        values = {
            "node": "git-cell-a",
            "carrier_sha256": "a" * 64,
            "locator_kind": "content-addressed-local-store",
            "locator_identity": "local:carrier:a",
            "readback_sha256": "a" * 64,
            "immutable": True,
            "locally_owned_variant": True,
            "shared_as_learning_only": True,
        }
        values.update(changes)
        return CarrierPresence(**values)

    def test_valid_presence_requires_readback_and_immutability(self):
        proof = verify_presence(self.base())
        self.assertTrue(proof.valid)
        self.assertEqual(proof.reason, "durable-carrier-readback-verified")

    def test_digest_mismatch_fails_closed(self):
        proof = verify_presence(self.base(readback_sha256="b" * 64))
        self.assertFalse(proof.valid)
        self.assertEqual(proof.reason, "readback-digest-mismatch")

    def test_mutable_or_nonlocal_carrier_cannot_qualify(self):
        self.assertEqual(verify_presence(self.base(immutable=False)).reason, "carrier-not-immutable")
        self.assertEqual(verify_presence(self.base(locally_owned_variant=False)).reason, "variant-not-locally-owned")

    def test_implementation_sharing_is_rejected(self):
        proof = verify_presence(self.base(shared_as_learning_only=False))
        self.assertFalse(proof.valid)
        self.assertEqual(proof.reason, "implementation-sharing-not-allowed")

    def test_projection_is_reference_closed(self):
        presence = self.base()
        proof = verify_presence(presence)
        field = presence_field(presence, proof)
        self.assertEqual(field.missing_refs(), set())
        self.assertGreaterEqual(len(field), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
