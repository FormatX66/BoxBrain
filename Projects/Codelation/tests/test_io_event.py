from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from io_event import IOEventError, event_field, make_event  # noqa: E402


class IOEventTests(unittest.TestCase):
    def test_identity_ignores_payload_retention_and_carrier(self):
        left = make_event(
            "sample",
            "in",
            b"abc",
            sequence=1,
            monotonic_ns=10,
            semantics={"sample"},
            retain_inline=True,
            carrier="one",
        )
        right = make_event(
            "sample",
            "in",
            b"abc",
            sequence=1,
            monotonic_ns=10,
            semantics={"sample"},
            retain_inline=False,
            carrier="two",
        )
        self.assertEqual(left.identity, right.identity)

    def test_raw_payload_is_not_persisted_to_field(self):
        event = make_event(
            "sample",
            "in",
            b"private-bytes",
            sequence=0,
            monotonic_ns=1,
            retain_inline=True,
        )
        field = event_field([event])
        carrier = field.project()
        self.assertNotIn(b"private-bytes", carrier)
        self.assertEqual(field.missing_refs(), set())

    def test_invalid_event_bounds_are_rejected(self):
        with self.assertRaises(IOEventError):
            make_event("", "in", b"x", sequence=0, monotonic_ns=0)
        with self.assertRaises(IOEventError):
            make_event("x", "bad", b"x", sequence=0, monotonic_ns=0)

    def test_same_event_is_deterministic(self):
        kwargs = dict(
            channel="sample",
            direction="in",
            payload=b"123",
            sequence=7,
            monotonic_ns=99,
            semantics={"b", "a"},
            permission="scope",
            provenance={"z", "a"},
        )
        self.assertEqual(make_event(**kwargs).identity, make_event(**kwargs).identity)


if __name__ == "__main__":
    unittest.main(verbosity=2)
