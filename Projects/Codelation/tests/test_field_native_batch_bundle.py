from __future__ import annotations

import sys
import unittest
from pathlib import Path

FIELD = Path(__file__).resolve().parents[1] / "field"
sys.path.insert(0, str(FIELD))

from field_native_batch import NativeBatchItem
from field_native_batch_bundle import run_native_batch_bundle
from field_native_bundle import bundle_programs, restore_native_bundle
from field_native_vm import NativeExample, execute_native


class FieldNativeBatchBundleTests(unittest.TestCase):
    def test_batch_verifies_and_round_trips_as_one_carrier(self):
        items = (
            NativeBatchItem(
                name="delta",
                parameters=("before", "after"),
                expression={
                    "op": "length",
                    "value": {
                        "op": "symmetric_difference",
                        "left": {"op": "split", "value": {"op": "input", "name": "before"}},
                        "right": {"op": "split", "value": {"op": "input", "name": "after"}},
                    },
                },
                examples=(
                    NativeExample({"before": "a b", "after": "a b c"}, 1),
                    NativeExample({"before": "a b", "after": "a c"}, 2),
                ),
                invocation_arguments={"before": "field slush", "after": "field aurum slush"},
            ),
            NativeBatchItem(
                name="overlap",
                parameters=("before", "after"),
                expression={
                    "op": "length",
                    "value": {
                        "op": "intersection",
                        "left": {"op": "split", "value": {"op": "input", "name": "before"}},
                        "right": {"op": "split", "value": {"op": "input", "name": "after"}},
                    },
                },
                examples=(
                    NativeExample({"before": "a b", "after": "a b c"}, 2),
                    NativeExample({"before": "a b", "after": "c d"}, 0),
                ),
                invocation_arguments={"before": "field slush", "after": "field aurum slush"},
            ),
        )
        proof = run_native_batch_bundle(items)
        self.assertTrue(proof.verified)
        self.assertEqual({result.name for result in proof.results}, {"delta", "overlap"})
        restored = restore_native_bundle(proof.bundle.carrier)
        self.assertEqual(restored.carrier_sha256, proof.bundle_sha256)
        programs = bundle_programs(restored)
        args = {"before": "field slush", "after": "field aurum slush"}
        self.assertEqual(execute_native(programs["delta"], args), 1)
        self.assertEqual(execute_native(programs["overlap"], args), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
