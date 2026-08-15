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


if __name__ == "__main__":
    unittest.main()
