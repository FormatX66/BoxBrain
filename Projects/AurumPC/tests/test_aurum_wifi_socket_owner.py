from __future__ import annotations

import ast
from pathlib import Path
import unittest

MODULE = Path(__file__).parents[1] / "aurum_network.py"


class WifiProcessBoundaryTests(unittest.TestCase):
    def test_aurum_executes_only_nmcli_and_bounded_probe(self) -> None:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        command_literals: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in {"_command", "_run"}:
                continue
            for argument in node.args:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    command_literals.append(argument.value)
                elif isinstance(argument, ast.List):
                    command_literals.extend(
                        element.value
                        for element in argument.elts
                        if isinstance(element, ast.Constant) and isinstance(element.value, str)
                    )
        self.assertIn("nmcli", command_literals)
        for forbidden in ("wpa_supplicant", "wpa_cli", "dhclient", "networkctl", "systemd-run", "iw"):
            self.assertNotIn(forbidden, command_literals)

    def test_no_process_or_control_socket_cleanup_implementation_remains(self) -> None:
        names = {node.id for node in ast.walk(ast.parse(MODULE.read_text(encoding="utf-8"))) if isinstance(node, ast.Name)}
        for removed in ("PROC_ROOT", "_stop_owned_supplicant", "_supplicant_status", "_wait_for_control_socket"):
            self.assertNotIn(removed, names)


if __name__ == "__main__":
    unittest.main()
