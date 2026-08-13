from __future__ import annotations

import sys
import unittest
from pathlib import Path

FIELD = Path(__file__).resolve().parents[1] / "field"
sys.path.insert(0, str(FIELD))

from field_native_cache import NativeBuildCache
from field_native_vm import NativeExample


class FieldNativeCacheTests(unittest.TestCase):
    def test_identical_compile_and_verification_are_reused(self):
        cache = NativeBuildCache()
        expression = {
            "op": "length",
            "value": {"op": "split", "value": {"op": "input", "name": "text"}},
        }
        examples = (NativeExample({"text": "a b"}, 2),)

        first = cache.resolve(("text",), expression, examples)
        second = cache.resolve(("text",), expression, examples)

        self.assertFalse(first.compile_cache_hit)
        self.assertFalse(first.verification_cache_hit)
        self.assertTrue(second.compile_cache_hit)
        self.assertTrue(second.verification_cache_hit)
        self.assertEqual(first.program, second.program)
        self.assertEqual(first.verification, second.verification)

    def test_new_examples_reuse_program_but_not_verification(self):
        cache = NativeBuildCache()
        expression = {
            "op": "length",
            "value": {"op": "split", "value": {"op": "input", "name": "text"}},
        }
        cache.resolve(("text",), expression, (NativeExample({"text": "a b"}, 2),))
        changed = cache.resolve(
            ("text",),
            expression,
            (NativeExample({"text": "a b c"}, 3),),
        )
        self.assertTrue(changed.compile_cache_hit)
        self.assertFalse(changed.verification_cache_hit)
        self.assertTrue(changed.verification.verified)

    def test_new_expression_is_a_compile_miss(self):
        cache = NativeBuildCache()
        first_expression = {
            "op": "length",
            "value": {"op": "split", "value": {"op": "input", "name": "text"}},
        }
        second_expression = {
            "op": "length",
            "value": {
                "op": "unique",
                "value": {"op": "split", "value": {"op": "input", "name": "text"}},
            },
        }
        cache.resolve(("text",), first_expression, (NativeExample({"text": "a a"}, 2),))
        second = cache.resolve(
            ("text",),
            second_expression,
            (NativeExample({"text": "a a"}, 1),),
        )
        self.assertFalse(second.compile_cache_hit)
        self.assertFalse(second.verification_cache_hit)


if __name__ == "__main__":
    unittest.main(verbosity=2)
