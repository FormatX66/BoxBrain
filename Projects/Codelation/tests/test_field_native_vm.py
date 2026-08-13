from __future__ import annotations

import sys
import unittest
from pathlib import Path

FIELD = Path(__file__).resolve().parents[1] / "field"
sys.path.insert(0, str(FIELD))

from field_native_vm import NativeExample, compile_native, execute_native, verify_native


class FieldNativeVMTests(unittest.TestCase):
    def test_learning_token_normalization_without_source_generation(self):
        expression = {
            "op": "join",
            "separator": " ",
            "value": {
                "op": "sort",
                "value": {
                    "op": "unique",
                    "value": {
                        "op": "split",
                        "value": {
                            "op": "casefold",
                            "value": {
                                "op": "strip",
                                "value": {"op": "input", "name": "text"},
                            },
                        },
                    },
                },
            },
        }
        program = compile_native(("text",), expression)
        verification = verify_native(
            program,
            (
                NativeExample({"text": " Field field SLUSH "}, "field slush"),
                NativeExample({"text": "Pi3 Morris GitHub Pi3"}, "github morris pi3"),
            ),
        )
        self.assertTrue(verification.verified)
        self.assertEqual(
            execute_native(program, {"text": "SLUSH Field field Aurum slush"}),
            "aurum field slush",
        )

    def test_delta_score_reuses_native_set_and_length_operations(self):
        expression = {
            "op": "length",
            "value": {
                "op": "symmetric_difference",
                "left": {"op": "split", "value": {"op": "casefold", "value": {"op": "input", "name": "before"}}},
                "right": {"op": "split", "value": {"op": "casefold", "value": {"op": "input", "name": "after"}}},
            },
        }
        program = compile_native(("before", "after"), expression)
        verification = verify_native(
            program,
            (
                NativeExample({"before": "field slush", "after": "field aurum slush"}, 1),
                NativeExample({"before": "a b", "after": "a c"}, 2),
            ),
        )
        self.assertTrue(verification.verified)
        self.assertEqual(execute_native(program, {"before": "field slush", "after": "field aurum slush"}), 1)

    def test_overlap_union_and_safe_divide_compose_without_python_generation(self):
        overlap = {
            "op": "length",
            "value": {
                "op": "intersection",
                "left": {"op": "split", "value": {"op": "input", "name": "before"}},
                "right": {"op": "split", "value": {"op": "input", "name": "after"}},
            },
        }
        union = {
            "op": "length",
            "value": {
                "op": "union",
                "left": {"op": "split", "value": {"op": "input", "name": "before"}},
                "right": {"op": "split", "value": {"op": "input", "name": "after"}},
            },
        }
        expression = {"op": "safe_divide", "left": overlap, "right": union}
        program = compile_native(("before", "after"), expression)
        self.assertEqual(execute_native(program, {"before": "a b", "after": "a b c"}), 2 / 3)
        self.assertEqual(execute_native(program, {"before": "", "after": ""}), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
