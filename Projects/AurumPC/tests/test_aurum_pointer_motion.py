from __future__ import annotations

import unittest

from Projects.AurumPC.aurum_pointer_motion import PointerMotionTracker, motion_evidence


class PointerMotionProofTests(unittest.TestCase):
    def test_open_pointer_path_is_not_motion_proof(self) -> None:
        proof = motion_evidence(None, path_available=True)
        self.assertTrue(proof["path_available"])
        self.assertFalse(proof["motion_observed"])
        self.assertFalse(proof["ready"])
        self.assertEqual(proof["event_count"], 0)

    def test_recorded_motion_requires_path_and_event(self) -> None:
        tracker = PointerMotionTracker()
        snapshot = tracker.record(
            position=(640, 360),
            delta=(7, -3),
            observed_at="2026-08-27T10:30:00Z",
            monotonic_at=123.5,
        )

        proof = motion_evidence(snapshot, path_available=True)
        self.assertTrue(proof["motion_observed"])
        self.assertTrue(proof["ready"])
        self.assertEqual(proof["event_count"], 1)
        self.assertEqual(proof["position"], [640, 360])
        self.assertEqual(proof["delta"], [7, -3])
        self.assertEqual(proof["last_at"], "2026-08-27T10:30:00Z")

        no_path = motion_evidence(snapshot, path_available=False)
        self.assertTrue(no_path["motion_observed"])
        self.assertFalse(no_path["ready"])

    def test_mapping_without_timestamp_cannot_claim_motion(self) -> None:
        proof = motion_evidence({"event_count": 4}, path_available=True)
        self.assertFalse(proof["motion_observed"])
        self.assertFalse(proof["ready"])


if __name__ == "__main__":
    unittest.main()
