from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path


class BootProofTests(unittest.TestCase):
    def test_capture_records_slot_and_boot_context(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence = root / "evidence"
            slots = root / "slots.json"
            active = root / "active"
            runtime = root / "slotA"
            boot_id = root / "boot_id"
            cmdline = root / "cmdline"
            runtime.mkdir()
            active.symlink_to(runtime)
            slots.write_text(
                json.dumps(
                    {
                        "schema": "aurum-germ-slots-v1",
                        "active": "A",
                        "lkg": "A",
                        "trial": None,
                        "trial_boots": 0,
                        "last_result": "tiny-seed-bootstrap",
                    }
                ),
                encoding="utf-8",
            )
            boot_id.write_text("boot-123\n", encoding="utf-8")
            cmdline.write_text("aurum.tinyseed=1 quiet\n", encoding="utf-8")

            env = {
                "AURUM_EVIDENCE_ROOT": str(evidence),
                "AURUM_SLOT_STATE": str(slots),
                "AURUM_ACTIVE_LINK": str(active),
                "AURUM_BOOT_ID_PATH": str(boot_id),
                "AURUM_CMDLINE_PATH": str(cmdline),
            }
            old = {key: os.environ.get(key) for key in env}
            try:
                os.environ.update(env)
                import proof

                proof = importlib.reload(proof)
                payload = proof.capture()
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

            receipt = json.loads((evidence / "boot-proof.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "aurum-boot-proof-v1")
            self.assertEqual(receipt["boot_id"], "boot-123")
            self.assertIn("aurum.tinyseed=1", receipt["kernel_cmdline"])
            self.assertEqual(receipt["guardian"]["active"], "A")
            self.assertEqual(receipt["guardian"]["lkg"], "A")
            self.assertEqual(receipt["active_runtime"], str(runtime.resolve()))


if __name__ == "__main__":
    unittest.main()
