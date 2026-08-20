from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "aurum_arcade.py"
SPEC = importlib.util.spec_from_file_location("aurum_arcade", MODULE_PATH)
assert SPEC and SPEC.loader
arcade = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = arcade
SPEC.loader.exec_module(arcade)


class AurumArcadeTests(unittest.TestCase):
    def test_echo_rally_is_dependency_free_loopback_game(self) -> None:
        self.assertEqual(arcade.MACHINE, "Hopper")
        self.assertEqual(arcade.GAME, "Echo Rally")
        self.assertEqual(arcade.DEFAULT_HOST, "127.0.0.1")
        self.assertIn("Every fourth return leaves a temporary echo well", arcade.PAGE)
        self.assertIn("KeyW", arcade.PAGE)
        self.assertIn("ArrowDown", arcade.PAGE)
        self.assertIn("pointerdown", arcade.PAGE)
        self.assertIn("AudioContext", arcade.PAGE)
        self.assertIn("rally%4===0", arcade.PAGE)
        self.assertNotIn("fetch(", arcade.PAGE)


if __name__ == "__main__":
    unittest.main()
