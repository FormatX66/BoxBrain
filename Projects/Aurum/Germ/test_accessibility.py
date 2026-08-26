#!/usr/bin/env python3
from __future__ import annotations

import unittest
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import accessibility


class AccessibilityTests(unittest.TestCase):
    def test_blind_entry_is_explicit(self) -> None:
        self.assertTrue(accessibility.enabled("boot=live aurum.accessibility=blind aurum.ui=plain"))
        self.assertFalse(accessibility.enabled("boot=live aurum.ui=compact"))

    def test_noop_when_blind_entry_was_not_selected(self) -> None:
        with (
            mock.patch.object(accessibility, "enabled", return_value=False),
            mock.patch.object(accessibility, "_run") as run,
        ):
            self.assertTrue(accessibility.activate())
        run.assert_not_called()

    def test_ready_requires_module_daemon_and_active_state(self) -> None:
        with (
            mock.patch.object(accessibility, "enabled", return_value=True),
            mock.patch.object(accessibility, "_run", side_effect=[True, True, True]) as run,
            mock.patch.object(accessibility, "_announce") as announce,
        ):
            self.assertTrue(accessibility.activate())
        self.assertEqual(run.call_count, 3)
        announce.assert_called_once_with(accessibility.MARKER)

    def test_failure_is_visible_and_fails_the_selected_mode(self) -> None:
        with (
            mock.patch.object(accessibility, "enabled", return_value=True),
            mock.patch.object(accessibility, "_run", return_value=False),
            mock.patch.object(accessibility, "_announce") as announce,
        ):
            self.assertFalse(accessibility.activate())
        self.assertIn("ACCESSIBILITY_FAILED", announce.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
