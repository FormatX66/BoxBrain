from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "aurum_runtime_update.py"
SPEC = importlib.util.spec_from_file_location("aurum_runtime_update", MODULE_PATH)
assert SPEC and SPEC.loader
runtime_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime_module
SPEC.loader.exec_module(runtime_module)
ALLOWLIST = runtime_module.ALLOWLIST
RuntimeUpdater = runtime_module.RuntimeUpdater


class AurumRuntimeUpdateTests(unittest.TestCase):
    def test_plan_and_apply_are_allowlisted_atomic_and_receipted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            source = workspace / "Projects" / "AurumPC"
            target = root / "target"
            state = root / "state"
            marker = root / "aurum-installed.json"
            (workspace / ".git").mkdir(parents=True)
            source.mkdir(parents=True)
            target.mkdir()
            marker.write_text("{}\n", encoding="utf-8")
            for name in ALLOWLIST:
                (source / name).write_text(f"VALUE = {name!r}\n", encoding="utf-8")
                (target / name).write_text("VALUE = 'old'\n", encoding="utf-8")

            updater = RuntimeUpdater(
                workspace=workspace,
                target=target,
                state_dir=state,
                installed_marker=marker,
            )
            plan = updater.plan()
            self.assertTrue(plan["available"])
            self.assertEqual(set(plan["changed"]), set(ALLOWLIST))
            self.assertFalse(plan["identity"]["authorized"])

            with patch("aurum_runtime_update.os.geteuid", return_value=0):
                result = updater.apply()
            self.assertEqual(result["status"], "updated")
            self.assertFalse(result["reboot_required"])
            self.assertEqual(set(result["changed"]), set(ALLOWLIST))
            receipt = json.loads((state / "runtime-update.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["schema"], "aurum-pc-runtime-update-v3")
            self.assertTrue(Path(receipt["backup"]).is_dir())
            for name in ALLOWLIST:
                self.assertEqual((target / name).read_text(encoding="utf-8"), f"VALUE = {name!r}\n")

    def test_plan_refuses_when_not_installed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            updater = RuntimeUpdater(
                workspace=root / "workspace",
                target=root / "target",
                state_dir=root / "state",
                installed_marker=root / "missing-marker",
            )
            plan = updater.plan()
            self.assertFalse(plan["available"])
            self.assertEqual(plan["reason"], "not-installed-runtime")


if __name__ == "__main__":
    unittest.main()
