from __future__ import annotations

import sys
import unittest
from pathlib import Path

FIELD = Path(__file__).resolve().parents[1] / "field"
sys.path.insert(0, str(FIELD))

from field_native_batch import NativeBatchItem, run_native_batch
from field_native_vm import NativeExample


class FieldNativeBatchTests(unittest.TestCase):
    def test_multiple_pure_capabilities_verify_in_one_memory_batch(self):
        tokens = lambda name: {
            "op": "split",
            "value": {"op": "casefold", "value": {"op": "input", "name": name}},
        }
        items = (
            NativeBatchItem(
                name="delta",
                parameters=("before", "after"),
                expression={
                    "op": "length",
                    "value": {
                        "op": "symmetric_difference",
                        "left": tokens("before"),
                        "right": tokens("after"),
                    },
                },
                examples=(NativeExample({"before": "a b", "after": "a c"}, 2),),
                invocation_arguments={"before": "field", "after": "field slush"},
            ),
            NativeBatchItem(
                name="overlap",
                parameters=("before", "after"),
                expression={
                    "op": "length",
                    "value": {
                        "op": "intersection",
                        "left": tokens("before"),
                        "right": tokens("after"),
                    },
                },
                examples=(NativeExample({"before": "a b", "after": "a b c"}, 2),),
                invocation_arguments={"before": "field slush", "after": "field aurum"},
            ),
        )
        proof = run_native_batch(items)
        self.assertTrue(proof.verified)
        self.assertFalse(proof.model_reasoning_required)
        self.assertFalse(proof.source_generation_required)
        self.assertFalse(proof.filesystem_build_required)
        self.assertFalse(proof.subprocess_test_required)
        outputs = {result.name: result.output for result in proof.results}
        self.assertEqual(outputs, {"delta": 1, "overlap": 1})

    def test_batch_is_deterministic_across_input_order(self):
        base = NativeBatchItem(
            name="count",
            parameters=("text",),
            expression={"op": "length", "value": {"op": "split", "value": {"op": "input", "name": "text"}}},
            examples=(NativeExample({"text": "a b"}, 2),),
            invocation_arguments={"text": "a b c"},
        )
        other = NativeBatchItem(
            name="unique-count",
            parameters=("text",),
            expression={
                "op": "length",
                "value": {
                    "op": "unique",
                    "value": {"op": "split", "value": {"op": "input", "name": "text"}},
                },
            },
            examples=(NativeExample({"text": "a a b"}, 2),),
            invocation_arguments={"text": "a a b c"},
        )
        first = run_native_batch((base, other))
        second = run_native_batch((other, base))
        self.assertEqual(first.batch_identity, second.batch_identity)
        self.assertEqual(first.results, second.results)


if __name__ == "__main__":
    unittest.main(verbosity=2)
