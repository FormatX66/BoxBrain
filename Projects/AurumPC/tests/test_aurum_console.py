from __future__ import annotations

from contextlib import redirect_stdout
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if sys.platform != "win32":
    import aurum_console
else:  # Windows runs source-contract coverage; the runtime itself requires fcntl.
    aurum_console = None


class AurumConsoleContractTests(unittest.TestCase):
    @unittest.skipIf(aurum_console is None, "Aurum runtime requires Linux process locks")
    def test_self_build_status_projects_machine_wide_durable_completion(self) -> None:
        output = io.StringIO()
        with (
            patch.object(aurum_console.BUILDS, "status", return_value={"running": False, "latest": {"status": "idle"}}),
            patch.object(aurum_console.WORKSPACE, "self_build_status", return_value={"stage": "complete", "status": "passed"}),
            redirect_stdout(output),
        ):
            aurum_console.show_self_build_status()
        self.assertIn("AURUM_SELF_BUILD_STATUS status=passed stage=complete", output.getvalue())
        self.assertIn("AURUM_SELF_BUILD_FINISHED status=passed source=durable-machine-status", output.getvalue())

    def test_console_source_keeps_bounded_commands(self) -> None:
        source = (ROOT / "aurum_console.py").read_text(encoding="utf-8")
        for token in (
            "status | hardware",
            "network-status | wifi-setup | wifi-reconnect",
            "self-build-status",
            "git-sync authorize-network",
            "runtime-status | runtime-sync",
            "autonomy-status | autonomy-cycle",
            "driver-status | driver-cycle",
            "gui-status | gui-start | gui-stop",
            "install confirm ERASE-CODE",
        ):
            self.assertIn(token, source)

    def test_bootstrap_forces_detailed_hardware_provider(self) -> None:
        source = (ROOT / "aurum_bootstrap.py").read_text(encoding="utf-8")
        self.assertIn("aurum_console.hardware = collect_hardware_profile", source)
        self.assertIn("AURUM_WIFI_DIAG", source)

    def test_seed_can_refresh_runtime_and_launch_unattended_builds_without_a_shell(self) -> None:
        source = (ROOT.parent / "Codelation" / "seed" / "codelation_seed.py").read_text(encoding="utf-8")
        self.assertIn("_installed_runtime_sync", source)
        self.assertIn("aurum_runtime_update.py", source)
        self.assertIn("_launch_installed_autonomy", source)
        self.assertIn("aurum_autonomy.py", source)
        self.assertIn("AURUM_AUTONOMY_BOOTSTRAP", source)


if __name__ == "__main__":
    unittest.main()
