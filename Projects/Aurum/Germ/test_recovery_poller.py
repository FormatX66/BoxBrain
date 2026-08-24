from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import recovery_poller


class RecoveryPollerReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.originals = {
            "PUBLIC_KEY": recovery_poller.PUBLIC_KEY,
            "TRUST_FILE": recovery_poller.TRUST_FILE,
            "REPLAY_FILE": recovery_poller.REPLAY_FILE,
            "RECEIPT_ROOT": recovery_poller.RECEIPT_ROOT,
        }
        recovery_poller.PUBLIC_KEY = self.root / "authority.pem"
        recovery_poller.TRUST_FILE = self.root / "trust.json"
        recovery_poller.REPLAY_FILE = self.root / "replay.json"
        recovery_poller.RECEIPT_ROOT = self.root / "receipts"
        recovery_poller.PUBLIC_KEY.write_text("fixture", encoding="utf-8")
        recovery_poller.TRUST_FILE.write_text("{}", encoding="utf-8")

    def tearDown(self) -> None:
        for name, value in self.originals.items():
            setattr(recovery_poller, name, value)
        self.temp.cleanup()

    def _verified_request(self, request_id: str = "replay-test-0001") -> dict:
        return {
            "schema": "aurum-recovery-request-v1",
            "request_id": request_id,
            "node_id": "node-123",
            "issued_at_unix": 1,
            "expires_at_unix": 2,
            "target": "last-known-good",
            "ref": None,
            "platform_commit": None,
            "reboot": False,
        }

    def test_consumed_request_is_refused_before_apply(self) -> None:
        request = self._verified_request()
        recovery_poller._consume(request["request_id"], {"status": "fixture"})

        with (
            mock.patch.object(recovery_poller, "_fetch", return_value={"fixture": True}),
            mock.patch.object(recovery_poller, "_node_id", return_value="node-123"),
            mock.patch.object(recovery_poller.recovery_control, "load_trusted_states", return_value=set()),
            mock.patch.object(recovery_poller.recovery_control, "verify_envelope", return_value=request),
            mock.patch.object(recovery_poller, "_apply") as apply,
        ):
            result = recovery_poller.poll_once()

        self.assertEqual(result["status"], "replay-ignored")
        self.assertEqual(result["request_id"], request["request_id"])
        apply.assert_not_called()

    def test_successful_request_is_consumed_for_future_replay_refusal(self) -> None:
        request = self._verified_request("replay-test-0002")
        with (
            mock.patch.object(recovery_poller, "_fetch", return_value={"fixture": True}),
            mock.patch.object(recovery_poller, "_node_id", return_value="node-123"),
            mock.patch.object(recovery_poller.recovery_control, "load_trusted_states", return_value=set()),
            mock.patch.object(recovery_poller.recovery_control, "verify_envelope", return_value=request),
            mock.patch.object(recovery_poller, "_apply", return_value={"status": "already-last-known-good"}),
        ):
            receipt = recovery_poller.poll_once()

        self.assertEqual(receipt["status"], "applied")
        self.assertTrue(recovery_poller._already_consumed(request["request_id"]))
        replay = json.loads(recovery_poller.REPLAY_FILE.read_text(encoding="utf-8"))
        self.assertEqual(replay["consumed"][-1]["request_id"], request["request_id"])

    def test_invalid_replay_state_fails_closed(self) -> None:
        recovery_poller.REPLAY_FILE.write_text(
            json.dumps({"schema": "wrong", "consumed": []}), encoding="utf-8"
        )
        with self.assertRaises(recovery_poller.PollerError):
            recovery_poller._already_consumed("replay-test-0003")


if __name__ == "__main__":
    unittest.main()
