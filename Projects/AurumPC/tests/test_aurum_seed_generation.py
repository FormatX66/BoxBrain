from __future__ import annotations

import importlib.util
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).parents[1]
RUNTIME_PATH = ROOT / "aurum_runtime_update.py"
SPEC = importlib.util.spec_from_file_location("aurum_seed_generation_runtime", RUNTIME_PATH)
assert SPEC and SPEC.loader
runtime_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime_module
SPEC.loader.exec_module(runtime_module)

PROJECTION_PATH = ROOT / "aurum_projection_runtime.py"
PROJECTION_SPEC = importlib.util.spec_from_file_location("aurum_seed_generation_projection", PROJECTION_PATH)
assert PROJECTION_SPEC and PROJECTION_SPEC.loader
projection_module = importlib.util.module_from_spec(PROJECTION_SPEC)
sys.modules[PROJECTION_SPEC.name] = projection_module
PROJECTION_SPEC.loader.exec_module(projection_module)


class AurumSeedGenerationTests(unittest.TestCase):
    def test_html_and_pygame_physical_proofs_remain_distinct(self) -> None:
        html = runtime_module.RuntimeUpdater._physical_proof(
            {
                "physical_desktop": True,
                "desktop": {"status": "running", "renderer": "html5", "primary": True},
            }
        )
        fallback = runtime_module.RuntimeUpdater._physical_proof(
            {
                "physical_desktop": True,
                "desktop": {"status": "running", "renderer": "pygame-fallback", "primary": False},
            }
        )
        self.assertEqual(html["status"], "passed")
        self.assertTrue(html["html_primary"])
        self.assertFalse(html["pygame_fallback"])
        self.assertEqual(fallback["status"], "passed")
        self.assertFalse(fallback["html_primary"])
        self.assertTrue(fallback["pygame_fallback"])

    def test_runtime_and_health_receipts_cover_the_canonical_lifecycle(self) -> None:
        runtime = RUNTIME_PATH.read_text(encoding="utf-8")
        autonomy = (ROOT / "aurum_autonomy.py").read_text(encoding="utf-8")
        health = (ROOT / "aurum_self_debug.py").read_text(encoding="utf-8")
        credential = (ROOT / "aurum_credential_bootstrap.py").read_text(encoding="utf-8")
        projection = (ROOT / "aurum_projection_runtime.py").read_text(encoding="utf-8")
        for marker in ("discover_pull", '"verify"', '"stage"', '"apply"', '"prove"', '"become_next_seed"'):
            self.assertIn(marker, runtime)
        self.assertIn("fast_forward_only", autonomy)
        self.assertIn('runtime.get("changed")', health)
        self.assertIn('"html_primary"', health)
        self.assertIn('"bounded_executor"', health)
        self.assertIn("generation-proof", health)
        self.assertIn("credential_status", health)
        self.assertIn("machine-sealed", credential)
        self.assertIn("plaintext_in_git", credential)
        self.assertIn("aurum-projection.lock", projection)
        self.assertIn("_clear_stale_vt2", projection)
        self.assertIn("pygame-fallback", projection)

    def test_named_weaves_and_nonblocking_adapter_lane_are_preserved(self) -> None:
        lifecycle = (ROOT / "SEED_LIFECYCLE.md").read_text(encoding="utf-8")
        self.assertIn("AinWeave", lifecycle)
        self.assertIn("StateWeave", lifecycle)
        self.assertIn("ComputeWeave", lifecycle)
        adapter = ROOT.parent / "AurumLLM" / "training"
        self.assertTrue(adapter.is_dir())
        self.assertNotIn("AurumLLM", runtime_module.ALLOWLIST)

    def test_stale_projection_cleanup_signals_only_recognized_launch_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = projection_module.ProjectionRuntime(
                policy=root / "policy.json",
                receipt=root / "installed.json",
                state_dir=root / "state",
                run_dir=root / "run",
                desktop=Path("/opt/aurum/aurum_desktop.py"),
            )
            runtime.run_dir.mkdir(parents=True)
            snapshots = [
                {
                    101: {
                        "command": "/usr/bin/python3 /opt/aurum/aurum_desktop.py run",
                        "group": 91,
                        "session": 81,
                        "state": "S",
                    },
                    102: {
                        "command": "/usr/bin/python3 /opt/aurum/aurum_desktop.py run",
                        "group": 92,
                        "session": 81,
                        "state": "S",
                    },
                },
            ]
            members = {
                80: {"command": "/usr/bin/openvt -c 2", "group": 80, "session": 81, "state": "S"},
                101: snapshots[0][101],
                102: snapshots[0][102],
            }
            with (
                patch.object(runtime, "_recognized_vt2_processes", side_effect=snapshots),
                patch.object(runtime, "_session_members", side_effect=[members, {}, {}, {}, {}]),
                patch.object(runtime, "_signal_processes", return_value={}) as signal_processes,
            ):
                result = runtime._clear_stale_vt2()

        self.assertEqual(result["status"], "cleared")
        self.assertEqual(result["groups"], [91, 92])
        self.assertEqual(result["sessions"], [81])
        signal_processes.assert_any_call({80, 101, 102}, signal.SIGTERM)
        signal_processes.assert_any_call(set(), signal.SIGKILL)

    def test_cleanup_blocks_only_for_a_surviving_vt2_x_server(self) -> None:
        processes = {
            80: {"command": "/usr/lib/xorg/Xorg :0 vt2 -nolisten tcp"},
            81: {"command": "/usr/bin/python3 /opt/aurum/aurum_desktop.py run"},
            82: {"command": "/usr/lib/xorg/Xorg :1 vt3 -nolisten tcp"},
        }
        self.assertEqual(projection_module.ProjectionRuntime._vt2_servers(processes), [80])

    def test_physical_proof_carries_reboot_requirement_without_passing(self) -> None:
        proof = runtime_module.RuntimeUpdater._physical_proof(
            {
                "physical_desktop": False,
                "desktop": {"status": "stopped", "renderer": None, "reboot_required": True},
            }
        )
        self.assertEqual(proof["status"], "failed")
        self.assertTrue(proof["reboot_required"])

    def test_kernel_wait_skips_pygame_to_prevent_process_storm(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = projection_module.ProjectionRuntime(
                policy=root / "policy.json",
                receipt=root / "installed.json",
                state_dir=root / "state",
                run_dir=root / "run",
                desktop=Path("/opt/aurum/aurum_desktop.py"),
            )
            projection_module._atomic(
                runtime.state_path,
                {"status": "web-unavailable", "reboot_required": True},
            )
            with (
                patch.object(projection_module.os, "geteuid", return_value=0),
                patch.object(runtime, "_authorized", return_value=(True, "authorized-hopper")),
                patch.object(runtime, "status", return_value={"status": "stopped"}),
                patch.object(runtime, "_start_web", return_value=None),
                patch.object(runtime, "_fallback_runtime") as fallback,
            ):
                result = runtime._start_locked()

        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reboot_required"])
        self.assertEqual(result["fallback_result"]["status"], "skipped")
        fallback.assert_not_called()

    def test_transient_verified_html_launch_gets_one_clean_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = projection_module.ProjectionRuntime(
                policy=root / "policy.json",
                receipt=root / "installed.json",
                state_dir=root / "state",
                run_dir=root / "run",
                desktop=Path("/opt/aurum/aurum_desktop.py"),
            )
            failure = {
                "status": "web-unavailable",
                "reason": "html-launch-not-verified",
                "dependencies": {"status": "ready"},
                "input_path": {"status": "ready"},
                "ui_user": {"status": "ready"},
            }
            attempts = 0

            def start_web():
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    projection_module._atomic(runtime.state_path, failure)
                    return None
                return {"status": "running", "renderer": "html5", "primary": True}

            with (
                patch.object(projection_module.os, "geteuid", return_value=0),
                patch.object(runtime, "_authorized", return_value=(True, "authorized-hopper")),
                patch.object(runtime, "status", return_value={"status": "stopped"}),
                patch.object(runtime, "_start_web", side_effect=start_web),
                patch.object(runtime, "_fallback_runtime") as fallback,
                patch.object(projection_module.time, "sleep"),
            ):
                result = runtime._start_locked()

        self.assertEqual(attempts, 2)
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["launch_recovery"]["status"], "recovered")
        self.assertEqual(result["launch_recovery"]["attempts"], 2)
        fallback.assert_not_called()

    def test_reboot_marker_expires_when_boot_identity_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = projection_module.ProjectionRuntime(
                policy=root / "policy.json",
                receipt=root / "installed.json",
                state_dir=root / "state",
                run_dir=root / "run",
                desktop=Path("/opt/aurum/aurum_desktop.py"),
            )
            projection_module._atomic(
                runtime.state_path,
                {"status": "failed", "reboot_required": True, "boot_id": "previous-boot"},
            )
            with (
                patch.object(projection_module, "_boot_id", return_value="current-boot"),
                patch.object(runtime, "_authorized", return_value=(True, "authorized-hopper")),
                patch.object(runtime, "_fallback_runtime", return_value=None),
            ):
                status = runtime.status()

        self.assertEqual(status["status"], "stopped")
        self.assertFalse(status["reboot_required"])

    def test_empty_stale_set_is_a_verified_clear_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = projection_module.ProjectionRuntime(
                policy=root / "policy.json",
                receipt=root / "installed.json",
                state_dir=root / "state",
                run_dir=root / "run",
                desktop=Path("/opt/aurum/aurum_desktop.py"),
            )
            with patch.object(runtime, "_recognized_vt2_processes", return_value={}):
                result = runtime._clear_stale_vt2()

        self.assertEqual(result["status"], "cleared")


if __name__ == "__main__":
    unittest.main()
