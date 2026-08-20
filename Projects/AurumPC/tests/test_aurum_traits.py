from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "aurum_traits.py"
SPEC = importlib.util.spec_from_file_location("aurum_traits", MODULE_PATH)
assert SPEC and SPEC.loader
traits_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = traits_module
SPEC.loader.exec_module(traits_module)


class AurumTraitRegistryTests(unittest.TestCase):
    def test_gen1_catalog_has_durable_unique_trait_ids(self) -> None:
        catalog = traits_module.catalog()
        ids = [item["id"] for item in catalog]
        self.assertEqual(len(ids), 8)
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(
            ids,
            [
                "TRAIT:GPT",
                "TRAIT:INTENT",
                "TRAIT:CONNECT",
                "TRAIT:RECOVER",
                "TRAIT:WEB",
                "TRAIT:FILES",
                "TRAIT:WRITE",
                "TRAIT:MEDIA",
            ],
        )

    def test_existing_gen1_foundations_are_not_claimed_as_complete_traits(self) -> None:
        summary = traits_module.summary()
        self.assertEqual(summary["schema"], "aurum.traits.v1")
        self.assertEqual(summary["foundation_ready"], 3)
        self.assertEqual(summary["foundation_building"], 1)
        self.assertEqual(summary["planned"], 4)
        self.assertFalse(summary["host_actuation"])
        self.assertEqual(traits_module.trait("trait:connect")["stage"], "foundation-ready")
        self.assertIsNone(traits_module.trait("TRAIT:DOES-NOT-EXIST"))


if __name__ == "__main__":
    unittest.main()
