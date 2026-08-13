from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from boot_aperture import choose_boot_aperture  # noqa: E402
from boot_aperture_handshake import (  # noqa: E402
    boot_handshake_field,
    make_boot_offer,
    make_boot_receipt,
    make_boot_request,
)


class BootApertureHandshakeTests(unittest.TestCase):
    def test_request_identity_is_order_independent(self):
        left = make_boot_request("pi3", ["authorized-lan", "pi3-rom-network-boot"])
        right = make_boot_request("pi3", ["pi3-rom-network-boot", "authorized-lan"])
        self.assertEqual(left.request_id, right.request_id)

    def test_offer_is_bound_to_request_and_aperture(self):
        request = make_boot_request("pi3", ["authorized-lan", "pi3-rom-network-boot"])
        aperture = choose_boot_aperture("pi3", request.observed_boot_tokens)
        digest = hashlib.sha256(b"bootstrap").hexdigest()
        offer = make_boot_offer(request, aperture, [digest])
        self.assertEqual(offer.request_id, request.request_id)
        self.assertEqual(offer.aperture_identity, aperture.identity)

    def test_target_mismatch_is_rejected(self):
        request = make_boot_request("pi3-a", ["authorized-lan", "pi3-rom-network-boot"])
        aperture = choose_boot_aperture("pi3-b", ["authorized-lan", "pi3-rom-network-boot"])
        with self.assertRaises(ValueError):
            make_boot_offer(request, aperture, [hashlib.sha256(b"x").hexdigest()])

    def test_receipt_accepts_only_offered_digest(self):
        request = make_boot_request("pi3", ["authorized-lan", "pi3-rom-network-boot"])
        aperture = choose_boot_aperture("pi3", request.observed_boot_tokens)
        good = hashlib.sha256(b"good").hexdigest()
        offer = make_boot_offer(request, aperture, [good])
        accepted = make_boot_receipt(offer, "pi3", good)
        rejected = make_boot_receipt(offer, "pi3", hashlib.sha256(b"bad").hexdigest())
        self.assertTrue(accepted.accepted)
        self.assertFalse(rejected.accepted)

    def test_handshake_projects_cleanly_into_field(self):
        request = make_boot_request("pi3", ["authorized-lan", "pi3-rom-network-boot"])
        aperture = choose_boot_aperture("pi3", request.observed_boot_tokens)
        digest = hashlib.sha256(b"bootstrap").hexdigest()
        offer = make_boot_offer(request, aperture, [digest])
        receipt = make_boot_receipt(offer, "pi3", digest)
        field = boot_handshake_field(request, offer, receipt)
        self.assertEqual(field.missing_refs(), set())
        self.assertGreaterEqual(len(field), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
