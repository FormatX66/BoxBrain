from __future__ import annotations

import unittest
from unittest.mock import patch

import recovery_poller


class RecoveryPollerTargetTests(unittest.TestCase):
    def request(self, target: str) -> dict:
        return {
            "request_id": "test-request-0001",
            "target": target,
            "ref": None,
            "platform_commit": None,
            "reboot": False,
        }

    def test_stay_current_is_read_only(self) -> None:
        with patch.object(
            recovery_poller,
            "_steady_lkg",
            return_value=(True, {"active": "A", "lkg": "A", "trial": None}),
        ):
            result = recovery_poller._apply(self.request("stay-current"))
        self.assertEqual(result["status"], "observed-current")
        self.assertTrue(result["steady_lkg"])

    def test_current_resolves_main_to_immutable_receipt(self) -> None:
        captured = []

        def fake_run(args, timeout):
            captured.append((args, timeout))
            return {
                "status": "trial-armed",
                "genetics_commit": "a" * 40,
                "platform_source_commit": "b" * 40,
            }

        with patch.object(recovery_poller, "_run_json", side_effect=fake_run):
            result = recovery_poller._apply(self.request("current"))
        self.assertEqual(result["status"], "trial-armed")
        self.assertIn("main", captured[0][0])
        self.assertIn("--authorize-network", captured[0][0])

    def test_previous_uses_guardian_previous_proven_slot(self) -> None:
        with patch.object(
            recovery_poller,
            "_run_json",
            return_value={"status": "restored-previous", "active": "A", "lkg": "A"},
        ) as run:
            result = recovery_poller._apply(self.request("previous"))
        self.assertEqual(result["status"], "restored-previous")
        self.assertIn("restore-previous", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
