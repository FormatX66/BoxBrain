from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from runtime_recipe import derive_runtime_recipe, runtime_recipe_field  # noqa: E402


class RuntimeRecipeTests(unittest.TestCase):
    def test_minimum_machine_builds_field_event_and_slush_core(self):
        recipe = derive_runtime_recipe(
            "machine-a",
            {"cpu-capacity", "memory-capacity", "storage-capacity"},
            {"field-state", "event-continuation", "slush-state"},
        )
        self.assertFalse(recipe.missing)
        self.assertIn("field-core", recipe.components)
        self.assertIn("event-handoff", recipe.components)
        self.assertIn("slush-store", recipe.components)

    def test_optional_model_gateway_is_not_installed_without_model_access(self):
        recipe = derive_runtime_recipe(
            "machine-a",
            {"cpu-capacity", "memory-capacity", "storage-capacity"},
            {"language-reasoning"},
        )
        self.assertIn("language-reasoning", recipe.missing)
        self.assertNotIn("model-gateway", recipe.components)

    def test_verified_isolation_carrier_unlocks_isolated_runtime(self):
        recipe = derive_runtime_recipe(
            "morris",
            {
                "cpu-capacity",
                "memory-capacity",
                "storage-capacity",
                "isolation-carrier",
            },
            {"isolated-prototype-runtime"},
        )
        self.assertFalse(recipe.missing)
        self.assertIn("isolated-host-carrier", recipe.components)

    def test_recipe_identity_is_deterministic(self):
        a = derive_runtime_recipe(
            "machine-a",
            {"cpu-capacity", "memory-capacity", "storage-capacity"},
            {"slush-state", "field-state"},
        )
        b = derive_runtime_recipe(
            "machine-a",
            ["storage-capacity", "memory-capacity", "cpu-capacity"],
            ["field-state", "slush-state"],
        )
        self.assertEqual(a.identity, b.identity)

    def test_field_projection_is_closed(self):
        recipe = derive_runtime_recipe(
            "machine-a",
            {"cpu-capacity", "memory-capacity", "storage-capacity"},
            {"field-state"},
        )
        field = runtime_recipe_field(recipe)
        self.assertEqual(field.missing_refs(), set())
        self.assertGreaterEqual(len(field), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
