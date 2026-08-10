from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boxbrain.drive_sync import (  # noqa: E402
    DriveSync,
    verify_patch_inbox,
)
from boxbrain.patches import (  # noqa: E402
    PATCH_DELIVERY_AUTHORIZATION,
    PATCH_DELIVERY_CONFIRMATION,
    PatchDeliveryError,
    PatchManager,
)


def completed(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, 0, "", "")


class DriveSyncTests(unittest.TestCase):
    def test_sync_uses_copy_only_and_stages_the_device_inbox(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state"
            (state / "reports").mkdir(parents=True)
            (state / "reports" / "report.json").write_text("{}", encoding="utf-8")
            binary = root / "rclone"
            binary.write_text("fixture", encoding="utf-8")
            config = root / "rclone.conf"
            config.write_text("fixture", encoding="utf-8")
            commands: list[list[str]] = []
            timeouts: list[object] = []

            def runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                timeouts.append(_kwargs.get("timeout"))
                return completed(command)

            result = DriveSync(
                state_directory=str(state),
                config_file=str(config),
                remote="boxbrain-drive",
                device_id="kali-pi-usbc",
                rclone_binary=str(binary),
                runner=runner,
            ).run()

            self.assertEqual(result["status"], "ok")
            self.assertTrue(commands)
            self.assertTrue(all(command[1] == "copy" for command in commands))
            self.assertFalse(any("sync" in command for command in commands))
            self.assertTrue(all(timeout == 3300 for timeout in timeouts))
            self.assertIn(
                "boxbrain-drive:Repositories/Patches/inbox/kali-pi-usbc",
                commands[-1],
            )
            self.assertIn("--drive-skip-shortcuts", commands[-1])
            self.assertIn("--max-size=512Mi", commands[-1])
            self.assertTrue((state / "logs" / "service-latest.json").is_file())
            self.assertTrue((state / "drive" / "sync-state.json").is_file())

    def test_patch_manifest_requires_matching_hash_and_creates_immutable_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inbox = root / "inbox"
            verified = root / "verified"
            inbox.mkdir()
            payload = inbox / "kb-test.msu"
            payload.write_bytes(b"verified patch fixture")
            digest = hashlib.sha256(payload.read_bytes()).hexdigest()
            manifest = {
                "schema_version": 1,
                "patch_id": "kb-test",
                "target_hostname": "HEX-LAPTOP",
                "payload": payload.name,
                "sha256": digest,
                "size_bytes": payload.stat().st_size,
            }
            (inbox / "kb-test.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )

            result = verify_patch_inbox(inbox, verified)

            reference = f"kb-test-{digest[:12]}"
            self.assertEqual(result["accepted"], [reference])
            self.assertEqual(result["rejected"], [])
            stored = json.loads(
                (verified / reference / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(stored["sha256"], digest)
            self.assertEqual((verified / reference / payload.name).read_bytes(), payload.read_bytes())

    def test_bad_patch_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inbox = root / "inbox"
            inbox.mkdir()
            (inbox / "bad.msu").write_bytes(b"payload")
            (inbox / "bad.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "patch_id": "bad",
                        "target_hostname": "HEX-LAPTOP",
                        "payload": "bad.msu",
                        "sha256": "0" * 64,
                    }
                ),
                encoding="utf-8",
            )

            result = verify_patch_inbox(inbox, root / "verified")

            self.assertEqual(result["accepted"], [])
            self.assertIn("SHA-256 verification failed", result["rejected"][0]["reason"])


class PatchDeliveryTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[PatchManager, str, list[dict[str, object]]]:
        state = root / "state"
        identity = state / "identity" / "target_ed25519"
        known_hosts = state / "identity" / "target_known_hosts"
        identity.parent.mkdir(parents=True)
        identity.write_text("fixture", encoding="utf-8")
        known_hosts.write_text("fixture", encoding="utf-8")
        links = state / "links"
        links.mkdir()
        (links / "10-12-194-9.json").write_text(
            json.dumps(
                {
                    "address": "10.12.194.9",
                    "hostname": "HEX-LAPTOP",
                    "status": "connected",
                }
            ),
            encoding="utf-8",
        )
        payload_bytes = b"verified patch fixture"
        digest = hashlib.sha256(payload_bytes).hexdigest()
        reference = f"kb-test-{digest[:12]}"
        verified = state / "drive" / "patches" / "verified" / reference
        verified.mkdir(parents=True)
        (verified / "kb-test.msu").write_bytes(payload_bytes)
        (verified / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "patch_id": "kb-test",
                    "target_hostname": "HEX-LAPTOP",
                    "payload": "kb-test.msu",
                    "sha256": digest,
                    "size_bytes": len(payload_bytes),
                }
            ),
            encoding="utf-8",
        )
        calls: list[dict[str, object]] = []

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append({"command": command, **kwargs})
            return completed(command)

        manager = PatchManager(str(state), str(identity), runner=runner)
        return manager, reference, calls

    def test_delivery_rechecks_target_and_stages_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager, reference, calls = self._fixture(Path(directory))

            receipt = manager.deliver(
                reference,
                PATCH_DELIVERY_AUTHORIZATION,
                PATCH_DELIVERY_CONFIRMATION,
            )

            self.assertEqual(receipt["status"], "delivered-not-executed")
            self.assertEqual(receipt["target_address"], "10.12.194.9")
            self.assertEqual(len(calls), 1)
            command = calls[0]["command"]
            self.assertEqual(command[0], "sftp")
            self.assertIn("StrictHostKeyChecking=yes", command)
            batch = str(calls[0]["input"])
            self.assertIn("BoxBrain/Patches/incoming", batch)
            self.assertNotIn("powershell", batch.lower())
            self.assertNotIn("execute", batch.lower())

    def test_delivery_requires_both_authorization_and_exact_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager, reference, calls = self._fixture(Path(directory))
            with self.assertRaises(PatchDeliveryError):
                manager.deliver(reference, "", PATCH_DELIVERY_CONFIRMATION)
            with self.assertRaises(PatchDeliveryError):
                manager.deliver(reference, PATCH_DELIVERY_AUTHORIZATION, "GO")
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
