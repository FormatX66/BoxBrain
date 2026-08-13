from __future__ import annotations

import sys
import unittest
from pathlib import Path

FIELD = Path(__file__).resolve().parents[1] / "field"
sys.path.insert(0, str(FIELD))

from field_native_bundle import bundle_programs, make_native_bundle, restore_native_bundle
from field_native_vm import compile_native, execute_native


class FieldNativeBundleTests(unittest.TestCase):
    def test_multiple_native_programs_round_trip_in_one_carrier(self):
        delta = compile_native(
            ("before", "after"),
            {
                "op": "length",
                "value": {
                    "op": "symmetric_difference",
                    "left": {"op": "split", "value": {"op": "input", "name": "before"}},
                    "right": {"op": "split", "value": {"op": "input", "name": "after"}},
                },
            },
        )
        overlap = compile_native(
            ("before", "after"),
            {
                "op": "length",
                "value": {
                    "op": "intersection",
                    "left": {"op": "split", "value": {"op": "input", "name": "before"}},
                    "right": {"op": "split", "value": {"op": "input", "name": "after"}},
                },
            },
        )
        wrapped = make_native_bundle({"delta": delta, "overlap": overlap})
        restored = restore_native_bundle(wrapped.carrier)
        self.assertEqual(restored.carrier_sha256, wrapped.carrier_sha256)
        programs = bundle_programs(restored)
        self.assertEqual(set(programs), {"delta", "overlap"})
        args = {"before": "field slush", "after": "field aurum slush"}
        self.assertEqual(execute_native(programs["delta"], args), 1)
        self.assertEqual(execute_native(programs["overlap"], args), 2)

    def test_bundle_is_deterministic_independent_of_input_mapping_order(self):
        first = compile_native(("text",), {"op": "length", "value": {"op": "split", "value": {"op": "input", "name": "text"}}})
        second = compile_native(("text",), {"op": "join", "separator": " ", "value": {"op": "sort", "value": {"op": "split", "value": {"op": "input", "name": "text"}}}})
        a = make_native_bundle({"a": first, "b": second})
        b = make_native_bundle({"b": second, "a": first})
        self.assertEqual(a.carrier, b.carrier)
        self.assertEqual(a.carrier_sha256, b.carrier_sha256)


if __name__ == "__main__":
    unittest.main(verbosity=2)
