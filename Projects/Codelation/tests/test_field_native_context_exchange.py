from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

FIELD = Path(__file__).resolve().parents[1] / "field"
sys.path.insert(0, str(FIELD))

from context_exchange import advance_context_state, parse_context_state  # noqa: E402


class ContextExchangeTests(unittest.TestCase):
    def digest(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def test_serialized_exchange_is_ordered_isolated_and_content_free(self) -> None:
        first = advance_context_state(
            None,
            context_id="context-a",
            sequence=1,
            input_sha256=self.digest("private input one"),
            output_sha256=self.digest("private output one"),
        )
        first_state = parse_context_state(first)
        second = advance_context_state(
            first,
            context_id="context-a",
            sequence=2,
            input_sha256=self.digest("private input two"),
            output_sha256=self.digest("private output two"),
        )
        second_state = parse_context_state(second)
        self.assertEqual(first_state.sequence, 1)
        self.assertEqual(second_state.sequence, 2)
        self.assertEqual(second_state.previous_chain_sha256, first_state.chain_sha256)
        for raw in (
            "private input one",
            "private output one",
            "private input two",
            "private output two",
        ):
            self.assertNotIn(raw, first)
            self.assertNotIn(raw, second)

        with self.assertRaisesRegex(ValueError, "monotonic"):
            advance_context_state(
                second,
                context_id="context-a",
                sequence=2,
                input_sha256="a" * 64,
                output_sha256="b" * 64,
            )
        with self.assertRaisesRegex(ValueError, "isolation"):
            advance_context_state(
                second,
                context_id="context-b",
                sequence=3,
                input_sha256="a" * 64,
                output_sha256="b" * 64,
            )

    def test_restart_parse_detects_corruption(self) -> None:
        serialized = advance_context_state(
            None,
            context_id="context-restart",
            sequence=1,
            input_sha256="a" * 64,
            output_sha256="b" * 64,
        )
        restored = parse_context_state(serialized)
        self.assertEqual(restored.context_id, "context-restart")
        tampered = json.loads(serialized)
        tampered["output_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "integrity"):
            parse_context_state(json.dumps(tampered, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    unittest.main()
