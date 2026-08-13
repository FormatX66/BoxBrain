from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from windows_capacity_mapping import derive_capacity_mapping  # noqa: E402
from windows_node_growth import MORRIS_NODE_ID, MORRIS_NODE_NAME, WindowsResourceObservation  # noqa: E402

GIB = 1024 ** 3


class WindowsCapacityMappingTests(unittest.TestCase):
    def observation(self, **changes):
        values = dict(
            node_id=MORRIS_NODE_ID,
            node_name=MORRIS_NODE_NAME,
            logical_processors=16,
            memory_total_bytes=32 * GIB,
            memory_available_bytes=20 * GIB,
            system_volume="C:",
            filesystem="NTFS",
            storage_total_bytes=512 * GIB,
            storage_free_bytes=160 * GIB,
            sparse_supported=True,
            gpu_names=("test-gpu",),
            hypervisor_present=False,
            new_vhd_available=False,
        )
        values.update(changes)
        return WindowsResourceObservation(**values)

    def test_slots_are_bounded_by_memory_cpu_and_maximum(self):
        mapping = derive_capacity_mapping(self.observation())
        self.assertEqual(mapping.worker_slots, 5)
        self.assertEqual(mapping.node.capacity, 5)

    def test_low_memory_reduces_parallel_slots(self):
        mapping = derive_capacity_mapping(self.observation(memory_available_bytes=6 * GIB))
        self.assertEqual(mapping.worker_slots, 1)

    def test_capabilities_are_evidence_gated(self):
        mapping = derive_capacity_mapping(self.observation())
        self.assertIn("resource-observation", mapping.node.capabilities)
        self.assertIn("slush-extent-plan", mapping.node.capabilities)
        self.assertNotIn("prototype-runtime-materialize", mapping.node.capabilities)

    def test_verified_hypervisor_adds_runtime_capability(self):
        mapping = derive_capacity_mapping(self.observation(hypervisor_present=True))
        self.assertIn("prototype-runtime-materialize", mapping.node.capabilities)

    def test_storage_headroom_preserves_slush_reserve(self):
        mapping = derive_capacity_mapping(self.observation(storage_free_bytes=160 * GIB))
        self.assertEqual(mapping.storage_headroom_bytes, 128 * GIB)


if __name__ == "__main__":
    unittest.main(verbosity=2)
