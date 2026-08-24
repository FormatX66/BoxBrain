#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import carrier
import reseed


GENETICS_COMMIT = "1" * 40
PLATFORM_COMMIT = "2" * 40


def fixture(root: Path) -> tuple[Path, Path]:
    genetics = root / "genetics-source"
    platform = root / "platform-source"
    required = [
        "Projects/Aurum/Germ/GENETICS.json",
        "Projects/Aurum/Germ/reseed.py",
        "docs/architecture/SEED_RECOVERY_ARCHITECTURE.md",
    ]
    manifest = {
        "schema": "aurum-genetics-v1",
        "germ_protocol": 1,
        "repository": reseed.REPOSITORY,
        "default_trusted_ref": "main",
        "required_paths": required,
        "platforms": {
            "x86_64": {
                "source_ref": "aurum/trunk-v0.01",
                "runtime_root": "Projects/AurumPC",
                "codelation_root": "Projects/Codelation",
                "growth_adapter": "python-runtime-slot-v1",
                "local_ab_slots": True,
                "offline_carrier": {"enabled": True, "pinned_commit": PLATFORM_COMMIT},
            }
        },
        "policy": {
            "candidate_only_staging": True,
            "live_overwrite_allowed": False,
            "promotion_requires_health_evidence": True,
        },
    }
    manifest_path = genetics / reseed.MANIFEST_RELATIVE
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (genetics / "Projects/Aurum/Germ/reseed.py").write_text("VALUE = 'germ'\n", encoding="utf-8")
    docs = genetics / "docs/architecture/SEED_RECOVERY_ARCHITECTURE.md"
    docs.parent.mkdir(parents=True)
    docs.write_text("protected recovery\n", encoding="utf-8")
    runtime = platform / "Projects/AurumPC"
    codelation = platform / "Projects/Codelation"
    runtime.mkdir(parents=True)
    codelation.mkdir(parents=True)
    (runtime / "aurum_console.py").write_text(
        "import json\n"
        "from aurum_workspace import AurumWorkspace, WorkspaceError\n"
        "def command_help():\n"
        "    print(\n"
        "        \"reboot | poweroff | help\",\n"
        "    )\n"
        "def dispatch(command, tokens):\n"
        "    while True:\n"
        "        if False:\n"
        "            pass\n"
        "        elif command == \"reboot\" and len(tokens) == 1:\n"
        "            pass\n",
        encoding="utf-8",
    )
    (runtime / "aurum_workspace.py").write_text("class AurumWorkspace: pass\nclass WorkspaceError(Exception): pass\n", encoding="utf-8")
    (codelation / "genetics.py").write_text("VALUE = 'codelation'\n", encoding="utf-8")
    return genetics, platform


class OfflineCarrierTests(unittest.TestCase):
    def test_prepare_verify_and_stage_are_hash_bound_and_network_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            genetics, platform = fixture(root)
            carrier_root = root / "carrier"
            prepared = carrier.prepare(
                genetics_root=genetics,
                platform_root=platform,
                output=carrier_root,
                genetics_commit=GENETICS_COMMIT,
                platform_commit=PLATFORM_COMMIT,
            )
            self.assertEqual(prepared["status"], "verified")
            self.assertFalse(prepared["live_overwrite_allowed"])
            self.assertTrue(prepared["promotion_requires_guardian_health"])

            state = root / "state"
            staged = reseed.stage_offline(carrier_root=carrier_root, state_root=state)
            self.assertEqual(staged["status"], "staged-offline-carrier")
            self.assertFalse(staged["network_authorized"])
            self.assertFalse(staged["active_overwritten"])
            self.assertTrue(Path(staged["candidate"]).is_dir())
            self.assertTrue(Path(staged["platform_source"]).is_dir())

    def test_tampered_platform_tree_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            genetics, platform = fixture(root)
            carrier_root = root / "carrier"
            carrier.prepare(
                genetics_root=genetics,
                platform_root=platform,
                output=carrier_root,
                genetics_commit=GENETICS_COMMIT,
                platform_commit=PLATFORM_COMMIT,
            )
            target = carrier_root / "platform/Projects/AurumPC/aurum_console.py"
            target.write_text("VALUE = 'tampered'\n", encoding="utf-8")
            with self.assertRaisesRegex(carrier.CarrierError, "platform tree digest"):
                carrier.verify(carrier_root)

    def test_offline_regrow_still_uses_inactive_slot_and_guardian_trial(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            genetics, platform = fixture(root)
            carrier_root = root / "carrier"
            carrier.prepare(
                genetics_root=genetics,
                platform_root=platform,
                output=carrier_root,
                genetics_commit=GENETICS_COMMIT,
                platform_commit=PLATFORM_COMMIT,
            )
            state = root / "state"
            state.mkdir()
            (state / "slots.json").write_text(
                json.dumps({"active": "A", "lkg": "A", "trial": None}),
                encoding="utf-8",
            )
            slots = root / "slots"
            slots.mkdir()
            with (
                mock.patch.object(reseed.os, "geteuid", return_value=0, create=True),
                mock.patch.object(reseed, "_architecture", return_value="x86_64"),
                mock.patch.object(reseed, "SLOTS_ROOT", slots),
                mock.patch.object(reseed, "_preboot_health", return_value={"compile": "passed"}),
                mock.patch.object(reseed, "_guardian_checkpoint", return_value={"status": "checkpointed"}),
                mock.patch.object(reseed, "_commit_slot_replacement", return_value={"status": "committed"}),
                mock.patch.object(reseed, "_arm_trial", return_value={"status": "trial-armed"}),
            ):
                result = reseed.regrow(
                    ref="main",
                    state_root=state,
                    authorize_network=False,
                    offline_carrier=carrier_root,
                )
            self.assertEqual(result["status"], "trial-armed")
            self.assertEqual(result["candidate_slot"], "B")
            self.assertEqual(result["source_transport"], "offline-carrier")
            self.assertTrue((slots / "B/opt/aurum/aurum_console.py").is_file())
            self.assertEqual(json.loads((state / "slots.json").read_text(encoding="utf-8"))["lkg"], "A")

    def test_unpinned_platform_commit_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            genetics, platform = fixture(root)
            with self.assertRaisesRegex(carrier.CarrierError, "pinned offline carrier commit"):
                carrier.prepare(
                    genetics_root=genetics,
                    platform_root=platform,
                    output=root / "carrier",
                    genetics_commit=GENETICS_COMMIT,
                    platform_commit="3" * 40,
                )


if __name__ == "__main__":
    unittest.main()
