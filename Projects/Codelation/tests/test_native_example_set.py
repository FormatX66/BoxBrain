from __future__ import annotations

import sys
import unittest
from pathlib import Path

FIELD = Path(__file__).resolve().parents[1] / "field"
sys.path.insert(0, str(FIELD))

from field_native_vm import NativeExample  # noqa: E402
from native_example_set import canonicalize_examples  # noqa: E402


class NativeExampleSetTests(unittest.TestCase):
    def test_exact_duplicates_are_removed(self):
        example = NativeExample({"text": "Field field"}, "field")
        result = canonicalize_examples((example, example, example))
        self.assertEqual(len(result.examples), 1)
        self.assertEqual(result.input_examples, 3)
        self.assertEqual(result.duplicate_examples_removed, 2)

    def test_identity_is_independent_of_input_order(self):
        a = NativeExample({"text": "a a b"}, "a b")
        b = NativeExample({"text": "c c"}, "c")
        first = canonicalize_examples((a, b))
        second = canonicalize_examples((b, a))
        self.assertEqual(first.identity, second.identity)
        self.assertEqual(first.examples, second.examples)

    def test_conflicting_expectations_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "conflicting expected outputs"):
            canonicalize_examples(
                (
                    NativeExample({"text": "same"}, "one"),
                    NativeExample({"text": "same"}, "two"),
                )
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
