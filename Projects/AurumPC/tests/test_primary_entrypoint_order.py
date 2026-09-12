"""Exercise the real bootstrap entrypoint with isolated, inert runtime adapters.

No physical hardware, display, driver, network, workspace or build is contacted.
These tests establish software call ordering, not VM or physical acceptance.
"""
from __future__ import annotations

import importlib.util
import io
import os
import sys
import threading
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

SOURCE = Path(os.environ.get("AURUM_BOOTSTRAP_TEST_SOURCE", Path(__file__).parents[1] / "aurum_bootstrap.py"))


class Screen:
    def __init__(self, **_kwargs):
        self.states = {"desktop": "waiting"}
        self.finished = None

    def update(self, stage, state, detail=None):
        self.states[stage] = state

    def finish(self, state, detail):
        self.finished = (state, detail)


def load_boot():
    class RuntimeErrorFixture(Exception):
        pass

    def module(name, **members):
        return types.SimpleNamespace(**members)

    gui = Mock(return_value={"status": "running", "physical_desktop": True})
    console = module("aurum_console", WORKSPACE=module("workspace", seed=Mock(return_value={"status": "seeded"})),
                     BUILDS=module("builds", start=Mock(return_value={"status": "started"})),
                     selftest=Mock(return_value=(True, "fixture")), main=Mock(return_value=0))
    profile = {key: [] for key in ("pci_devices", "usb_devices", "block_devices", "input_devices", "graphics_devices", "network_interfaces")}
    plan = {"required_existing_drivers": [], "unresolved_devices": []}
    modules = {
        "aurum_console": console,
        "aurum_boot_screen": module("screen", BootScreen=Screen),
        "aurum_gui_runtime": module("gui", GuiRuntime=Mock(return_value=module("instance", start=gui)), GuiRuntimeError=RuntimeErrorFixture),
        "aurum_hardware": module("hardware", DEFAULT_PLAN=Path("fixture-plan"), DEFAULT_PROFILE=Path("fixture-profile"),
                                 capture_hardware_evidence=Mock(return_value=(profile, plan)), collect_hardware_profile=Mock()),
        "aurum_network": module("network", ensure_online=Mock(side_effect=AssertionError("network must not gate primary boot")), wireless_interfaces=Mock(return_value=[])),
        "aurum_time": module("time", synchronize_clock=Mock()),
        "aurum_wifi_diag": module("diag", diagnose=Mock(return_value={"status": "fixture"})),
        "aurum_wifi_recovery": module("recovery", recover_existing_wifi_driver=Mock(return_value={"status": "fixture"})),
        "aurum_workspace": module("workspace", WorkspaceError=RuntimeErrorFixture),
    }
    spec = importlib.util.spec_from_file_location("isolated_boot_contract", SOURCE)
    boot = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(boot)
    boot._json_file = Mock(return_value={"auto_gui_start": True})
    boot._input_summary = Mock(return_value=("ready", "fixture"))
    boot._write_assessment = Mock()
    boot.BootScreen = Mock(return_value=Screen())
    return boot, gui, console, RuntimeErrorFixture


class PrimaryEntrypointOrderTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"AURUM_PRIMARY_CONSOLE": "1", "AURUM_DISABLE_AUTONOMOUS_FIRST_BOOT": "0"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.boot, self.gui, self.console, self.runtime_error = load_boot()

    def run_boot(self):
        with redirect_stdout(io.StringIO()):
            return self.boot.main()

    def test_gui_precedes_wireless_recovery_and_diagnostics(self):
        order = []
        self.gui.side_effect = lambda: order.append("gui") or {"status": "running", "physical_desktop": True}
        self.boot.recover_existing_wifi_driver.side_effect = lambda: order.append("recover") or {"status": "fixture"}
        self.boot.diagnose_wifi.side_effect = lambda: order.append("diagnose") or {"status": "fixture"}
        self.assertEqual(self.run_boot(), 0)
        self.assertEqual(order, ["gui", "recover", "diagnose"])

    def test_stalled_wireless_recovery_cannot_delay_gui_start(self):
        release, ready = threading.Event(), threading.Event()
        errors = []

        def recover():
            release.wait(4)
            return {"status": "fixture"}

        def gui():
            ready.set()
            return {"status": "running", "physical_desktop": True}

        def run():
            try:
                self.run_boot()
            except BaseException as exc:
                errors.append(exc)

        self.boot.recover_existing_wifi_driver.side_effect = recover
        self.gui.side_effect = gui
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        try:
            self.assertTrue(ready.wait(0.5), "main() blocked GUI on wireless recovery")
        finally:
            release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])

    def test_hardware_diagnostic_failure_does_not_disable_local_desktop(self):
        self.boot.capture_hardware_evidence.side_effect = OSError("fixture diagnostic failure")
        self.assertEqual(self.run_boot(), 0)
        self.gui.assert_called_once()
        self.assertEqual(self.boot.BootScreen.return_value.states["hardware"], "degraded")

    def test_serial_console_does_not_acquire_primary_gui_authority(self):
        with patch.dict(os.environ, {"AURUM_PRIMARY_CONSOLE": "0"}):
            self.assertEqual(self.run_boot(), 0)
        self.gui.assert_not_called()
        self.boot.recover_existing_wifi_driver.assert_not_called()
        self.boot.diagnose_wifi.assert_called_once()

    def test_disabled_autonomous_boot_stays_disabled(self):
        with patch.dict(os.environ, {"AURUM_DISABLE_AUTONOMOUS_FIRST_BOOT": "1"}):
            self.assertEqual(self.run_boot(), 0)
        self.gui.assert_not_called()
        self.boot.recover_existing_wifi_driver.assert_not_called()

    def test_existing_wireless_interface_does_not_trigger_recovery(self):
        self.boot.wireless_interfaces.return_value = ["fixture-interface"]
        self.assertEqual(self.run_boot(), 0)
        self.gui.assert_called_once()
        self.boot.recover_existing_wifi_driver.assert_not_called()
        self.boot.diagnose_wifi.assert_not_called()

    def test_gui_failure_is_not_reported_as_ready(self):
        self.gui.side_effect = self.runtime_error("fixture GUI failure")
        self.assertEqual(self.run_boot(), 0)
        self.assertEqual(self.boot.BootScreen.return_value.finished[0], "degraded")
        self.assertEqual(self.boot._write_assessment.call_args.args[0]["gui"]["status"], "failed")
        self.console.main.assert_called_once()

    def test_diagnostic_exception_does_not_prevent_recovery_console(self):
        self.boot.diagnose_wifi.side_effect = OSError("fixture diagnosis unavailable")
        self.assertEqual(self.run_boot(), 0)
        self.gui.assert_called_once()
        self.console.main.assert_called_once()


if __name__ == "__main__":
    unittest.main()
