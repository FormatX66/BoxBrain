from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from slush_lifecycle import (  # noqa: E402
    MATERIALIZED,
    RUNTIME_READY,
    SEEDED,
    SlushState,
    advance_slush,
    next_slush_work,
    slush_lifecycle_field,
)


class SlushLifecycleTests(unittest.TestCase):
    def base(self):
        return SlushState("abc123", "morris", "windows-sparse-file", 64 * 1024**3)

    def test_planned_slush_exposes_only_materialize_next(self):
        work = next_slush_work(self.base())
        self.assertEqual(len(work), 1)
        self.assertIn("slush-extent-provision", work[0].requires)

    def test_materialization_requires_all_safety_evidence(self):
        with self.assertRaises(ValueError):
            advance_slush(self.base(), MATERIALIZED, {"storage-capacity-verified"})

    def test_full_lifecycle_advances_only_adjacent_states(self):
        materialized = advance_slush(
            self.base(),
            MATERIALIZED,
            {"storage-capacity-verified", "write-scope-approved", "no-partition-change"},
        )
        seeded = advance_slush(
            materialized,
            SEEDED,
            {"extent-verified", "seed-digest-verified", "mirrored-anchor-verified"},
        )
        ready = advance_slush(
            seeded,
            RUNTIME_READY,
            {"isolation-carrier-verified", "runtime-artifact-verified", "runtime-selftest-pass"},
        )
        self.assertEqual(ready.state, RUNTIME_READY)
        self.assertEqual(next_slush_work(ready), ())

    def test_state_skip_is_rejected(self):
        with self.assertRaises(ValueError):
            advance_slush(self.base(), SEEDED, set())

    def test_field_projection_keeps_next_work_declarative(self):
        field = slush_lifecycle_field(self.base())
        self.assertEqual(field.missing_refs(), set())
        self.assertGreaterEqual(len(field), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
