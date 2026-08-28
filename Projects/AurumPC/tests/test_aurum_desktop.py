from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "aurum_desktop.py"
SPEC = importlib.util.spec_from_file_location("aurum_desktop", MODULE_PATH)
assert SPEC and SPEC.loader
desktop_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = desktop_module
SPEC.loader.exec_module(desktop_module)


class AurumDesktopTests(unittest.TestCase):
    def test_fallback_gpt_panel_uses_bounded_trait_and_returns_text(self) -> None:
        trait = SimpleNamespace(ask=lambda prompt: {"status": "completed", "text": f"heard {prompt}"})
        with patch.object(desktop_module, "_runtime_module", return_value=trait):
            ok, response = desktop_module._gpt_ask(
                "Hopper status", Path("state"), Path("workspace"), Path("runtime")
            )
        self.assertTrue(ok)
        self.assertEqual(response, "heard Hopper status")
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("AURUM GPT PROMPT", source)
        self.assertIn('elif action == "gpt-send"', source)

    def test_snapshot_reads_gen1_machine_state_without_host_actuation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            workspace = root / "workspace"
            runtime = root / "runtime"
            state.mkdir()
            (workspace / ".git" / "refs" / "heads" / "aurum").mkdir(parents=True)
            (workspace / ".git" / "HEAD").write_text("ref: refs/heads/aurum/trunk-v0.01\n", encoding="utf-8")
            head = "abcdef0123456789abcdef0123456789abcdef01"
            (workspace / ".git" / "refs" / "heads" / "aurum" / "trunk-v0.01").write_text(head + "\n", encoding="utf-8")
            (runtime / "codelation" / "autobuild").mkdir(parents=True)
            (runtime / "codelation" / "autobuild" / "native_chain_state.json").write_text(
                json.dumps({"completed_generations": 17, "next_gap": "physical-desktop-proof"}),
                encoding="utf-8",
            )
            (state / "autonomy.json").write_text(
                json.dumps({"status": "cycle-complete", "unattended": True}), encoding="utf-8"
            )
            (state / "runtime-update.json").write_text(
                json.dumps({"schema": "aurum-pc-runtime-update-v4", "status": "current"}), encoding="utf-8"
            )
            (state / "machine-identity.json").write_text(
                json.dumps({"display_name": "Hopper", "hostname": "hopper"}), encoding="utf-8"
            )
            (state / "seed.bin").write_bytes(b"seed")
            (state / "driver-lab").mkdir()
            (state / "driver-lab" / "latest-cycle.json").write_text(
                json.dumps({"status": "cycle-complete", "devices": [{"id": "wifi"}]}), encoding="utf-8"
            )
            input_state = root / "aurum-input-status.json"
            input_state.write_text(
                json.dumps({
                    "status": "ready",
                    "pointers": [{"kind": "mouse"}, {"kind": "touchpad"}],
                    "touchpads": [{"kind": "touchpad"}],
                    "wake_policy": {"status": "ready"},
                }),
                encoding="utf-8",
            )

            with patch.object(desktop_module, "_online", return_value=True):
                snapshot = desktop_module.collect_snapshot(
                    state_dir=state,
                    workspace=workspace,
                    runtime_root=runtime,
                    input_state=input_state,
                )

            self.assertEqual(snapshot["schema"], "aurum.desktop.v1")
            self.assertEqual(snapshot["machine"], "Hopper")
            self.assertEqual(snapshot["head"], head)
            self.assertEqual(snapshot["head_short"], head[:12])
            self.assertEqual(snapshot["runtime_status"], "current")
            self.assertEqual(snapshot["autonomy_status"], "cycle-complete")
            self.assertTrue(snapshot["autonomy_unattended"])
            self.assertEqual(snapshot["seed_status"], "seeded")
            self.assertEqual(snapshot["driver_devices"], 1)
            self.assertEqual(snapshot["branch"], "aurum/trunk-v0.01")
            self.assertEqual(snapshot["pointer_devices"], 2)
            self.assertEqual(snapshot["touchpad_devices"], 1)
            self.assertEqual(snapshot["input_wake_status"], "ready")
            self.assertEqual(snapshot["next_gap"], "physical-desktop-proof")
            self.assertTrue(snapshot["online"])


if __name__ == "__main__":
    unittest.main()
