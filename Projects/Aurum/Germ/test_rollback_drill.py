from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path


class RollbackDrillTests(unittest.TestCase):
    def test_plan_uses_only_inactive_slot_and_preserves_lkg(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_root = root / "germ"
            slots_root = root / "slots"
            state_root.mkdir()
            slots_root.mkdir()
            (state_root / "slots.json").write_text(
                json.dumps(
                    {
                        "schema": "aurum-germ-slots-v1",
                        "active": "A",
                        "lkg": "A",
                        "trial": None,
                        "trial_boots": 0,
                        "quarantined": [],
                    }
                ),
                encoding="utf-8",
            )
            old_state = os.environ.get("AURUM_GERM_STATE_ROOT")
            old_slots = os.environ.get("AURUM_SLOTS_ROOT")
            try:
                os.environ["AURUM_GERM_STATE_ROOT"] = str(state_root)
                os.environ["AURUM_SLOTS_ROOT"] = str(slots_root)
                import rollback_drill

                rollback_drill = importlib.reload(rollback_drill)
                result = rollback_drill.plan()
            finally:
                if old_state is None:
                    os.environ.pop("AURUM_GERM_STATE_ROOT", None)
                else:
                    os.environ["AURUM_GERM_STATE_ROOT"] = old_state
                if old_slots is None:
                    os.environ.pop("AURUM_SLOTS_ROOT", None)
                else:
                    os.environ["AURUM_SLOTS_ROOT"] = old_slots

            self.assertEqual(result["disposable_slot"], "B")
            self.assertFalse(result["lkg_will_be_modified"])
            self.assertFalse(result["active_will_be_modified"])


if __name__ == "__main__":
    unittest.main()
