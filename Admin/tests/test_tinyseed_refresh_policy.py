from __future__ import annotations

import unittest

from Admin.tinyseed_refresh_policy import decide_usb_refresh


SOURCE = "e845c02b984b8a40de42b58b1e059f03366804c3"
IMAGE = "afecf00f5d0c1b01c8585b74b4f31d51bd23420e6be142b6f5a4c8a0a5dd7382"


class TinySeedRefreshPolicyTests(unittest.TestCase):
    def release(self, *, source: str = SOURCE, image: str = IMAGE) -> dict:
        return {
            "schema": "aurum-tinyseed-handoff-v1",
            "state": "READY_TO_FLASH",
            "source_commit": source,
            "artifacts": {"x86": {"sha256": image}},
        }

    def receipt(self, *, source: str = SOURCE, image: str = IMAGE) -> dict:
        return {
            "schema": "aurum-tinyseed-flash-request-receipt-v1",
            "state": "READY_TO_BOOT",
            "source_commit": source,
            "image_sha256": image,
            "raw_readback_verified": True,
        }

    def test_matching_readback_verified_media_suppresses_refresh(self) -> None:
        decision = decide_usb_refresh(self.release(), self.receipt())
        self.assertFalse(decision.refresh)
        self.assertEqual(decision.reason, "current-release-media-already-readback-verified")

    def test_new_release_reenables_refresh(self) -> None:
        decision = decide_usb_refresh(self.release(source="b" * 40), self.receipt())
        self.assertTrue(decision.refresh)
        self.assertEqual(decision.reason, "current-release-media-proof-missing-or-stale")

    def test_changed_image_reenables_refresh(self) -> None:
        decision = decide_usb_refresh(self.release(image="c" * 64), self.receipt())
        self.assertTrue(decision.refresh)

    def test_missing_receipt_requires_refresh(self) -> None:
        decision = decide_usb_refresh(self.release(), None)
        self.assertTrue(decision.refresh)
        self.assertEqual(decision.reason, "current-release-flash-receipt-missing")

    def test_unverified_readback_requires_refresh(self) -> None:
        receipt = self.receipt()
        receipt["raw_readback_verified"] = False
        self.assertTrue(decide_usb_refresh(self.release(), receipt).refresh)

    def test_non_ready_release_does_not_dispatch_refresh(self) -> None:
        release = self.release()
        release["state"] = "BUILDING"
        decision = decide_usb_refresh(release, None)
        self.assertFalse(decision.refresh)
        self.assertEqual(decision.reason, "canonical-release-not-ready-to-flash")


if __name__ == "__main__":
    unittest.main()
