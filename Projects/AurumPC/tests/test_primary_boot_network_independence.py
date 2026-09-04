from __future__ import annotations

import sys
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import aurum_bootstrap as boot


class PrimaryBootNetworkIndependenceTests(unittest.TestCase):
    def _stubs(self, stack: ExitStack) -> None:
        stack.enter_context(patch.object(boot, "_autonomous_first_boot_enabled", return_value=True))
        stack.enter_context(patch.object(boot, "_primary_console", return_value=True))
        stack.enter_context(patch.object(boot.aurum_console.WORKSPACE, "seed", return_value={"status": "seeded"}))
        stack.enter_context(patch.object(boot.aurum_console, "selftest", return_value=(True, "ok")))
        stack.enter_context(patch.object(boot.aurum_console.BUILDS, "start", return_value={"status": "started"}))
        stack.enter_context(patch.object(boot, "_write_assessment"))

    def test_primary_boot_returns_with_gui_even_if_network_would_block(self) -> None:
        released = threading.Event()
        gui_ready = threading.Event()
        errors: list[BaseException] = []

        def stalled_network(**_kwargs):
            released.wait(5)
            return {"status": "offline", "online": False}

        def start_gui():
            gui_ready.set()
            return {"status": "running", "physical_desktop": True}

        def start_boot():
            try:
                boot._first_boot({}, {}, Mock())
            except BaseException as exc:
                errors.append(exc)

        with ExitStack() as stack:
            self._stubs(stack)
            network = stack.enter_context(patch.object(boot, "ensure_online", side_effect=stalled_network))
            stack.enter_context(patch.object(boot, "_start_gui", side_effect=start_gui))
            worker = threading.Thread(target=start_boot, daemon=True)
            worker.start()
            try:
                self.assertTrue(gui_ready.wait(0.5), "Primary GUI waited for the stalled network path")
                worker.join(0.5)
                self.assertFalse(worker.is_alive(), "Primary recovery console remains blocked by networking")
                self.assertEqual(errors, [])
                network.assert_not_called()
            finally:
                released.set()
                worker.join(5)

    def test_primary_gui_starts_before_local_build_and_leaves_sync_to_service(self) -> None:
        order: list[str] = []
        with ExitStack() as stack:
            self._stubs(stack)
            network = stack.enter_context(patch.object(boot, "ensure_online", return_value={"online": True}))
            sync = stack.enter_context(patch.object(boot.aurum_console.WORKSPACE, "git_sync"))
            clock = stack.enter_context(patch.object(boot, "synchronize_clock"))
            stack.enter_context(patch.object(boot, "_start_gui", side_effect=lambda: order.append("gui") or {"status": "running"}))
            stack.enter_context(patch.object(boot.aurum_console.WORKSPACE, "seed", side_effect=lambda: order.append("seed") or {"status": "seeded"}))
            boot._first_boot({}, {}, Mock())
        self.assertEqual(order, ["gui", "seed"])
        network.assert_not_called()
        sync.assert_not_called()
        clock.assert_not_called()

    def test_reconnect_service_does_not_gate_primary_console_and_has_hard_deadline(self) -> None:
        service = (ROOT / "runtime-assets/etc/systemd/system/aurum-network-bootstrap.service").read_text()
        self.assertNotIn("Before=aurum-pc-console.service", service)
        self.assertIn("TimeoutStartSec=75", service)
        self.assertIn("TimeoutStopSec=5", service)
        self.assertIn("--reconnect-saved", service)

    def test_live_and_installed_startup_do_not_cancel_each_other(self) -> None:
        services = ROOT / "runtime-assets/etc/systemd/system"
        setup = (services / "aurum-setup.service").read_text()
        primary = (services / "aurum-pc-console.service").read_text()
        setup_conflicts = next(line for line in setup.splitlines() if line.startswith("Conflicts=")).split("=", 1)[1].split()
        primary_conflicts = next(line for line in primary.splitlines() if line.startswith("Conflicts=")).split("=", 1)[1].split()
        # Conditions are checked after job conflicts have been resolved. Both
        # enabled services must survive scheduling so the correct one can run.
        self.assertNotIn("aurum-pc-console.service", setup_conflicts)
        self.assertNotIn("aurum-setup.service", primary_conflicts)
        self.assertIn("ConditionPathIsDirectory=/run/live/medium", setup)
        self.assertIn("ConditionPathExists=!/run/live/medium", primary)


if __name__ == "__main__":
    unittest.main()
