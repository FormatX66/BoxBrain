from __future__ import annotations

import importlib.util
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "aurum_console.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("aurum_console", MODULE_PATH)
assert SPEC and SPEC.loader
aurum_console = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aurum_console)


class BlockingWorkspace:
    def __init__(self) -> None:
        self.entered = threading.Event()

    def self_build(self, *, progress, cancel_event):
        self.entered.set()
        progress({"stage": "chain", "status": "generation-started", "elapsed_seconds": 0.0})
        while not cancel_event.wait(0.01):
            pass
        raise aurum_console.WorkspaceError("Self-build cancelled safely")


class SelfBuildControllerTests(unittest.TestCase):
    @patch("builtins.print")
    def test_build_runs_in_background_and_accepts_safe_cancellation(self, _print) -> None:
        workspace = BlockingWorkspace()
        controller = aurum_console.SelfBuildController(workspace)

        started_at = time.monotonic()
        result = controller.start()
        self.assertLess(time.monotonic() - started_at, 0.2)
        self.assertEqual(result["status"], "started")
        self.assertTrue(workspace.entered.wait(1))
        self.assertTrue(controller.status()["running"])
        self.assertEqual(controller.start()["status"], "already-running")
        self.assertEqual(controller.cancel()["status"], "cancellation-requested")
        self.assertTrue(controller._done.wait(1))
        self.assertEqual(controller.status()["latest"]["status"], "cancelled")


class NetworkStatusTests(unittest.TestCase):
    @patch.object(aurum_console, "_wired_interfaces", return_value=["enp4s0"])
    @patch.object(aurum_console, "_interface_addresses", return_value=[{"family": "inet", "local": "192.0.2.10"}])
    @patch.object(aurum_console, "_default_routes", return_value=[{"dst": "default", "dev": "enp4s0"}])
    @patch.object(aurum_console, "_read_text")
    @patch.object(aurum_console, "_bounded_command")
    def test_pc01_enp4s0_reports_ready_only_with_working_dns(
        self,
        bounded_command,
        read_text,
        _default_routes,
        _interface_addresses,
        _wired_interfaces,
    ) -> None:
        read_text.side_effect = lambda path, default="unknown": "1" if path.name == "carrier" else "up"
        bounded_command.return_value = {"ok": True, "returncode": 0, "output": "ready"}

        result = aurum_console.network_status()

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["interfaces"][0]["name"], "enp4s0")
        self.assertTrue(result["resolver"]["github_lookup"]["ok"])

    @patch.object(aurum_console, "_wired_interfaces", return_value=["enp4s0"])
    @patch.object(aurum_console, "_interface_addresses", return_value=[{"family": "inet", "local": "192.0.2.10"}])
    @patch.object(aurum_console, "_default_routes", return_value=[{"dst": "default", "dev": "enp4s0"}])
    @patch.object(aurum_console, "_read_text", return_value="1")
    @patch.object(aurum_console, "_bounded_command")
    def test_dns_failure_is_not_reported_as_network_ready(
        self,
        bounded_command,
        _read_text,
        _default_routes,
        _interface_addresses,
        _wired_interfaces,
    ) -> None:
        bounded_command.side_effect = lambda arguments, **_kwargs: {
            "ok": arguments[:2] != ["getent", "ahostsv4"],
            "returncode": 0 if arguments[:2] != ["getent", "ahostsv4"] else 2,
            "output": "",
        }

        result = aurum_console.network_status()

        self.assertEqual(result["status"], "dns-failed")


if __name__ == "__main__":
    unittest.main()
