from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from io_fabric import default_io_catalog, io_field, plan_io  # noqa: E402


class IOFabricTests(unittest.TestCase):
    def test_catalog_is_broad_and_unique(self):
        catalog = default_io_catalog()
        names = [port.name for port in catalog]
        self.assertGreaterEqual(len(catalog), 20)
        self.assertEqual(len(names), len(set(names)))

    def test_sensitive_ports_are_permission_visible(self):
        for port in default_io_catalog():
            if port.privacy_sensitive or port.actuator:
                self.assertNotEqual(port.permission, "none")

    def test_unavailable_permission_blocks_selection(self):
        catalog = default_io_catalog()
        port = next(item for item in catalog if item.permission != "none")
        semantic = next(iter(port.semantics))
        denied = plan_io({semantic}, available_ports={port.name})
        self.assertEqual(denied.selected, ())
        self.assertEqual(denied.blocked, (port.name,))
        allowed = plan_io(
            {semantic},
            available_ports={port.name},
            permissions={port.permission},
        )
        self.assertEqual(allowed.missing, frozenset())
        self.assertEqual(allowed.selected, (port.name,))

    def test_catalog_projects_to_field(self):
        catalog = default_io_catalog()
        field = io_field(catalog)
        self.assertEqual(field.missing_refs(), set())
        self.assertEqual(len(field), len(catalog) + 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
