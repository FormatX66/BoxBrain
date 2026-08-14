from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from aurum_field import Field  # noqa: E402
from windows_node_growth import (  # noqa: E402
    MORRIS_NODE_ID,
    MORRIS_NODE_NAME,
    WindowsResourceObservation,
    advertised_worker_capabilities,
    derive_morris_growth,
    growth_field,
)

GIB = 1024 ** 3


class WindowsNodeGrowthTests(unittest.TestCase):
    def observation(self, **changes):
        values = dict(
            node_id=MORRIS_NODE_ID,
            node_name=MORRIS_NODE_NAME,
            logical_processors=8,
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

    def test_resource_observation_is_always_a_base_capability(self):
        state = derive_morris_growth(self.observation())
        self.assertIn("resource-observation", state.names)

    def test_verified_storage_unlocks_slush_ladder(self):
        state = derive_morris_growth(self.observation())
        self.assertIn("slush-extent-plan", state.names)
        self.assertIn("slush-extent-provision", state.names)
        self.assertIn("slush-seed", state.names)
        self.assertIsNotNone(state.slush_plan)
        self.assertEqual(state.slush_plan.capacity_bytes, 64 * GIB)
        self.assertEqual(state.slush_plan.reserve_bytes, 32 * GIB)

    def test_low_free_space_keeps_slush_provision_blocked(self):
        state = derive_morris_growth(self.observation(storage_free_bytes=60 * GIB))
        self.assertNotIn("slush-extent-provision", state.names)
        self.assertIn("slush-extent-provision", state.blocked)
        self.assertIsNone(state.slush_plan)

    def test_non_sparse_filesystem_keeps_slush_blocked(self):
        state = derive_morris_growth(self.observation(sparse_supported=False, filesystem="FAT32"))
        self.assertNotIn("slush-extent-plan", state.names)
        self.assertIn("slush-extent-provision", state.blocked)

    def test_runtime_materialization_needs_verified_isolation_carrier(self):
        state = derive_morris_growth(self.observation())
        self.assertNotIn("prototype-runtime-materialize", state.names)
        self.assertEqual(
            state.blocked["prototype-runtime-materialize"],
            "no-verified-isolated-runtime-carrier",
        )

    def test_hypervisor_evidence_unlocks_runtime_materialization(self):
        state = derive_morris_growth(self.observation(hypervisor_present=True))
        self.assertIn("prototype-runtime-materialize", state.names)

    def test_wrong_node_identity_is_rejected(self):
        with self.assertRaises(ValueError):
            derive_morris_growth(self.observation(node_id="other"))

    def test_field_projection_is_closed_and_declares_no_partition_change(self):
        observation = self.observation()
        state = derive_morris_growth(observation)
        field = growth_field(observation, state)
        self.assertEqual(field.missing_refs(), set())
        projection = field.project()
        rebuilt = Field.absorb(projection)
        self.assertEqual(rebuilt.identity, field.identity)
        self.assertEqual(rebuilt.missing_refs(), set())
        plan_facts = [
            rebuilt.get(identity).value
            for identity in rebuilt.identities()
            if rebuilt.get(identity).kind == 1
            and isinstance(rebuilt.get(identity).value, dict)
            and rebuilt.get(identity).value.get("kind") == "slush-extent-plan"
        ]
        self.assertEqual(len(plan_facts), 1)
        self.assertIs(plan_facts[0]["host_partition_change"], False)
        self.assertGreaterEqual(len(field), 8)

    def test_worker_advertisement_is_explicit(self):
        state = derive_morris_growth(self.observation(hypervisor_present=True))
        names = advertised_worker_capabilities(state)
        self.assertEqual(names, tuple(sorted(names)))
        self.assertIn("resource-observation", names)
        self.assertIn("slush-extent-provision", names)
        self.assertIn("prototype-runtime-materialize", names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
