from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import recovery_control


@unittest.skipUnless(shutil.which("openssl"), "openssl is required")
class RecoveryControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.private_key = self.root / "private.pem"
        self.public_key = self.root / "public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(self.private_key)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", str(self.private_key), "-pubout", "-out", str(self.public_key)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.now = int(time.time())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def payload(self, **changes):
        payload = {
            "schema": recovery_control.REQUEST_SCHEMA,
            "request_id": "test-request-0001",
            "node_id": "node-123",
            "issued_at_unix": self.now - 5,
            "expires_at_unix": self.now + 300,
            "target": "last-known-good",
            "ref": None,
            "reboot": False,
        }
        payload.update(changes)
        return payload

    def envelope(self, payload):
        payload_path = self.root / "payload.bin"
        sig_path = self.root / "signature.bin"
        payload_path.write_bytes(recovery_control.canonical_json(payload))
        subprocess.run(
            [
                "openssl", "pkeyutl", "-sign", "-inkey", str(self.private_key),
                "-rawin", "-in", str(payload_path), "-out", str(sig_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {
            "schema": recovery_control.ENVELOPE_SCHEMA,
            "payload": payload,
            "signature_ed25519_base64": base64.b64encode(sig_path.read_bytes()).decode("ascii"),
        }

    def verify(self, envelope, trusted=None, node="node-123", now=None):
        return recovery_control.verify_envelope(
            envelope,
            public_key=self.public_key,
            local_node_id=node,
            trusted_commits=set() if trusted is None else trusted,
            now=self.now if now is None else now,
        )

    def test_valid_lkg_request_passes(self):
        checked = self.verify(self.envelope(self.payload()))
        self.assertEqual(checked["target"], "last-known-good")
        self.assertEqual(checked["node_id"], "node-123")

    def test_tampered_payload_fails_signature(self):
        envelope = self.envelope(self.payload())
        envelope["payload"]["reboot"] = True
        with self.assertRaises(recovery_control.RecoveryControlError):
            self.verify(envelope)

    def test_wrong_node_fails_closed(self):
        with self.assertRaises(recovery_control.RecoveryControlError):
            self.verify(self.envelope(self.payload()), node="another-node")

    def test_expired_request_fails_closed(self):
        payload = self.payload(issued_at_unix=self.now - 500, expires_at_unix=self.now - 1)
        with self.assertRaises(recovery_control.RecoveryControlError):
            self.verify(self.envelope(payload))

    def test_specific_commit_must_be_immutable_and_trusted(self):
        commit = "a" * 40
        payload = self.payload(target="specific", ref=commit)
        envelope = self.envelope(payload)
        with self.assertRaises(recovery_control.RecoveryControlError):
            self.verify(envelope)
        checked = self.verify(envelope, trusted={commit})
        self.assertEqual(checked["ref"], commit)

    def test_trust_file_rejects_moving_refs(self):
        path = self.root / "trust.json"
        path.write_text(
            json.dumps({"schema": recovery_control.TRUST_SCHEMA, "specific_commits": ["main"]}),
            encoding="utf-8",
        )
        with self.assertRaises(recovery_control.RecoveryControlError):
            recovery_control.load_trusted_commits(path)


if __name__ == "__main__":
    unittest.main()
