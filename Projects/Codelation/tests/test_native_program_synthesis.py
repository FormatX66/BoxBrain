from __future__ import annotations

import sys
import unittest
from pathlib import Path

FIELD = Path(__file__).resolve().parents[1] / "field"
sys.path.insert(0, str(FIELD))

from field_native_vm import NativeExample, compile_native, execute_native
from native_program_synthesis import synthesize_native_expression


class NativeProgramSynthesisTests(unittest.TestCase):
    def test_synthesizes_learning_delta_from_examples(self):
        examples = (
            NativeExample({"before": "field slush", "after": "field aurum slush"}, 1),
            NativeExample({"before": "a b", "after": "a c"}, 2),
            NativeExample({"before": "x y", "after": "x y"}, 0),
        )
        result = synthesize_native_expression(("before", "after"), examples, max_cost=8)
        self.assertTrue(result.found)
        program = compile_native(("before", "after"), result.expression)
        self.assertEqual(execute_native(program, {"before": "one two", "after": "one three"}), 2)

    def test_synthesizes_overlap_from_examples(self):
        examples = (
            NativeExample({"before": "a b", "after": "a b c"}, 2),
            NativeExample({"before": "field slush", "after": "field aurum"}, 1),
            NativeExample({"before": "x", "after": "y"}, 0),
        )
        result = synthesize_native_expression(("before", "after"), examples, max_cost=8)
        self.assertTrue(result.found)
        program = compile_native(("before", "after"), result.expression)
        self.assertEqual(execute_native(program, {"before": "a c", "after": "a c d"}), 2)

    def test_retention_reuses_previously_verified_capabilities(self):
        overlap_examples = (
            NativeExample({"before": "a b", "after": "a b c"}, 2),
            NativeExample({"before": "field slush", "after": "field aurum"}, 1),
            NativeExample({"before": "x", "after": "y"}, 0),
        )
        union_examples = (
            NativeExample({"before": "a b", "after": "a b c"}, 3),
            NativeExample({"before": "field slush", "after": "field aurum"}, 3),
            NativeExample({"before": "x", "after": "x"}, 1),
        )
        overlap = synthesize_native_expression(("before", "after"), overlap_examples, max_cost=8)
        union = synthesize_native_expression(("before", "after"), union_examples, max_cost=8)
        self.assertTrue(overlap.found)
        self.assertTrue(union.found)

        retention_examples = (
            NativeExample({"before": "a b", "after": "a b c"}, 2 / 3),
            NativeExample({"before": "field slush", "after": "field"}, 1 / 2),
            NativeExample({"before": "", "after": ""}, 0),
        )
        result = synthesize_native_expression(
            ("before", "after"),
            retention_examples,
            max_cost=4,
            seed_expressions={
                "learning_overlap_score": overlap.expression,
                "learning_union_size": union.expression,
            },
        )
        self.assertTrue(result.found)
        self.assertEqual(
            set(result.seed_expressions_considered),
            {"learning_overlap_score", "learning_union_size"},
        )
        program = compile_native(("before", "after"), result.expression)
        self.assertEqual(execute_native(program, {"before": "x y", "after": "x y z"}), 2 / 3)

    def test_not_found_is_bounded_and_explicit(self):
        examples = (
            NativeExample({"text": "a"}, 99),
            NativeExample({"text": "a b"}, 101),
        )
        result = synthesize_native_expression(("text",), examples, max_cost=3, max_signatures=100)
        self.assertFalse(result.found)
        self.assertIsNone(result.expression)
        self.assertGreater(result.candidates_evaluated, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
