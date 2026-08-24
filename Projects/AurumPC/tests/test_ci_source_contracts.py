from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
REPO = ROOT.parents[1]


class AurumCISourceContractTests(unittest.TestCase):
    def assert_source_contract(self, relative_path: str, pattern: str) -> None:
        text = (REPO / relative_path).read_text(encoding="utf-8")
        self.assertRegex(text, pattern, msg=f"stale CI contract: {relative_path} / {pattern}")

    def test_workflow_source_contracts_are_current(self) -> None:
        checks = [
            ("Projects/AurumPC/aurum_console.py", r"git-sync authorize-network"),
            ("Projects/AurumPC/aurum_console.py", r"git-promote authorize-network confirm-push"),
            ("Projects/AurumPC/aurum_console.py", r"network-status \| wifi-setup \| wifi-reconnect"),
            ("Projects/AurumPC/aurum_console.py", r"runtime-status \| runtime-sync"),
            ("Projects/AurumPC/aurum_console.py", r"autonomy-status \| autonomy-cycle"),
            ("Projects/AurumPC/aurum_console.py", r"driver-status \| driver-cycle"),
            ("Projects/AurumPC/aurum_console.py", r"gui-status \| gui-start \| gui-stop"),
            ("Projects/AurumPC/aurum_console.py", r"install confirm ERASE-CODE"),
            ("Projects/AurumPC/aurum_hardware.py", r"internal_disk_writes.*False"),
            ("Projects/AurumPC/aurum_hardware.py", r"preserve_current_removable_boot.*True"),
            ("Projects/AurumPC/aurum_bootstrap.py", r"AURUM_WIFI_DIAG"),
            ("Projects/AurumPC/aurum_bootstrap.py", r"recover_existing_wifi_driver"),
            ("Projects/AurumPC/aurum_bootstrap.py", r"synchronize_clock"),
            ("Projects/Codelation/seed/codelation_seed.py", r"_launch_installed_autonomy"),
            ("Projects/AurumPC/aurum_autonomy.py", r"aurum_driver_synthesis\.py"),
            ("Projects/AurumPC/pc01_autonomy_policy.json", r"load_synthesized_modules.*false"),
            ("Projects/AurumPC/pc01_autonomy_policy.json", r'"machine_display_name": "Hopper"'),
            ("Projects/AurumPC/pc01_autonomy_policy.json", r'"auto_local_echo_display": false'),
            ("Projects/AurumPC/aurum_arcade.py", r"Every fourth return leaves a temporary echo well"),
            ("Projects/AurumPC/aurum_gui_runtime.py", r"aurum_arcade\.py"),
            ("Projects/AurumPC/aurum_gui_runtime.py", r"aurum_projection_runtime\.py"),
            ("Projects/AurumPC/aurum_runtime_update.py", r"aurum_desktop\.py"),
            ("Projects/AurumPC/aurum_runtime_update.py", r"aurum_traits\.py"),
            ("Projects/AurumPC/aurum_runtime_update.py", r"aurum_gpt_trait\.py"),
            ("Projects/AurumPC/aurum_runtime_update.py", r"aurum_control_plane\.py"),
            ("Projects/AurumPC/aurum_desktop_runtime.py", r"SDL_VIDEODRIVER=kmsdrm"),
            ("Projects/AurumPC/aurum_desktop.py", r"Ctrl\+Alt\+F1 recovery"),
            ("Projects/AurumPC/build-iso.sh", r"xserver-xorg-input-libinput"),
            ("Projects/AurumPC/aurum_display_runtime.py", r"SDL_VIDEODRIVER=kmsdrm"),
            ("Projects/AurumPC/aurum_display_runtime.py", r'EXPECTED_GAME_SCHEMA = "aurum\.echo\.native\.v2"'),
            ("Projects/AurumPC/aurum_runtime_update.py", r"physical_echo_activation"),
            ("Projects/AurumPC/aurum_echo_native.py", r'PROOF_SCHEMA = "aurum\.hopper\.echo-proof\.v1"'),
            ("Projects/AurumPC/aurum_echo_native.py", r"keyboard_path_available"),
            ("Projects/AurumPC/aurum_echo_native.py", r"pointer_path_available"),
            ("Projects/AurumPC/aurum_echo_native.py", r"host_actuation.*False"),
        ]
        for relative_path, pattern in checks:
            with self.subTest(path=relative_path, pattern=pattern):
                self.assert_source_contract(relative_path, pattern)


if __name__ == "__main__":
    unittest.main()
