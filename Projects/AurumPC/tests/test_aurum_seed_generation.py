from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
RUNTIME_PATH = ROOT / "aurum_runtime_update.py"
SPEC = importlib.util.spec_from_file_location("aurum_seed_generation_runtime", RUNTIME_PATH)
assert SPEC and SPEC.loader
runtime_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime_module
SPEC.loader.exec_module(runtime_module)


class AurumSeedGenerationTests(unittest.TestCase):
    def test_html_and_pygame_physical_proofs_remain_distinct(self) -> None:
        html = runtime_module.RuntimeUpdater._physical_proof(
            {
                "physical_desktop": True,
                "desktop": {"status": "running", "renderer": "html5", "primary": True},
            }
        )
        fallback = runtime_module.RuntimeUpdater._physical_proof(
            {
                "physical_desktop": True,
                "desktop": {"status": "running", "renderer": "pygame-fallback", "primary": False},
            }
        )
        self.assertEqual(html["status"], "passed")
        self.assertTrue(html["html_primary"])
        self.assertFalse(html["pygame_fallback"])
        self.assertEqual(fallback["status"], "passed")
        self.assertFalse(fallback["html_primary"])
        self.assertTrue(fallback["pygame_fallback"])

    def test_runtime_and_health_receipts_cover_the_canonical_lifecycle(self) -> None:
        runtime = RUNTIME_PATH.read_text(encoding="utf-8")
        autonomy = (ROOT / "aurum_autonomy.py").read_text(encoding="utf-8")
        health = (ROOT / "aurum_self_debug.py").read_text(encoding="utf-8")
        for marker in ("discover_pull", '"verify"', '"stage"', '"apply"', '"prove"', '"become_next_seed"'):
            self.assertIn(marker, runtime)
        self.assertIn("fast_forward_only", autonomy)
        self.assertIn('runtime.get("changed")', health)
        self.assertIn('"html_primary"', health)
        self.assertIn('"bounded_executor"', health)

    def test_named_weaves_and_nonblocking_adapter_lane_are_preserved(self) -> None:
        lifecycle = (ROOT / "SEED_LIFECYCLE.md").read_text(encoding="utf-8")
        self.assertIn("AinWeave", lifecycle)
        self.assertIn("StateWeave", lifecycle)
        self.assertIn("ComputeWeave", lifecycle)
        adapter = ROOT.parent / "AurumLLM" / "training"
        self.assertTrue(adapter.is_dir())
        self.assertNotIn("AurumLLM", runtime_module.ALLOWLIST)


if __name__ == "__main__":
    unittest.main()
