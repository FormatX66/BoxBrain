from __future__ import annotations

import json
import unittest
from unittest import mock

from Projects.Codelation.run_native_frontier import (
    STATE_SCHEMA,
    _bootstrap_frontier,
    _strip_sequence_semantics,
    advance_frontier,
)


class NativeFrontierTests(unittest.TestCase):
    def test_legacy_sequence_labels_never_enter_authoritative_frontier_state(self) -> None:
        legacy = {
            "next_gap": "capability-a",
            "completed_generations": 64,
            "generations": [{"generation": 64, "gap": "old"}],
            "_checkpoint": {
                "schema": "aurum-native-chain-resume-v1",
                "learned_expressions": {"old": {"op": "literal", "value": 1}},
                "verified_local_capabilities": [],
            },
        }
        state = _bootstrap_frontier(legacy)
        serialized = json.dumps(state, sort_keys=True).lower()
        self.assertEqual(state["schema"], STATE_SCHEMA)
        self.assertEqual(state["frontier"], ["capability-a"])
        self.assertNotIn("generation", serialized)

    def test_sequence_sanitizer_removes_nested_legacy_labels(self) -> None:
        cleaned = _strip_sequence_semantics(
            {
                "generation": 7,
                "source_generation_used": False,
                "nested": {"attempted_generation": 8, "keep": "yes"},
                "keep": 42,
            }
        )
        self.assertEqual(cleaned, {"nested": {"keep": "yes"}, "keep": 42})

    def test_frontier_advances_by_capability_until_compute_burst_yields(self) -> None:
        state = _bootstrap_frontier(None)
        state["frontier"] = ["capability-a"]

        calls = []

        def fake_run_chain(*, start_gap, max_generations, evidence_now=None, seed_state=None):
            calls.append((start_gap, max_generations))
            next_gap = "capability-b" if start_gap == "capability-a" else "capability-c"
            return {
                "next_gap": next_gap,
                "blocked_reason": "generation-bound-reached",
                "reasoning_required": False,
                "reasoning_request": None,
                "external_evidence": None,
                "generations": [
                    {
                        "generation": 999,
                        "gap": start_gap,
                        "next_gap": next_gap,
                        "state": "verified",
                        "source_generation_used": False,
                    }
                ],
                "_checkpoint": {
                    "schema": "aurum-native-chain-resume-v1",
                    "learned_expressions": {start_gap: {"op": "literal", "value": 1}},
                    "verified_local_capabilities": [],
                },
            }

        with mock.patch(
            "Projects.Codelation.run_native_frontier.legacy_executor.run_chain",
            side_effect=fake_run_chain,
        ):
            advanced = advance_frontier(state, work_budget=2)

        self.assertEqual(calls, [("capability-a", 1), ("capability-b", 1)])
        self.assertEqual(advanced["frontier"], ["capability-c"])
        self.assertEqual(advanced["yield_reason"], "work-budget-yield")
        self.assertIsNone(advanced["blocked_reason"])
        self.assertEqual(advanced["work_done_this_burst"], 2)
        self.assertEqual(len(advanced["verified_work"]), 2)
        self.assertNotIn("generation", json.dumps(advanced, sort_keys=True).lower())

    def test_actual_block_is_not_confused_with_compute_budget(self) -> None:
        state = _bootstrap_frontier(None)
        state["frontier"] = ["needs-evidence"]

        with mock.patch(
            "Projects.Codelation.run_native_frontier.legacy_executor.run_chain",
            return_value={
                "next_gap": "needs-evidence",
                "blocked_reason": "external-prerequisite-blocked",
                "reasoning_required": False,
                "reasoning_request": None,
                "external_evidence": {"applied": False},
                "generations": [],
                "_checkpoint": state["executor_checkpoint"],
            },
        ):
            advanced = advance_frontier(state, work_budget=8)

        self.assertEqual(advanced["frontier"], ["needs-evidence"])
        self.assertEqual(advanced["blocked_reason"], "external-prerequisite-blocked")
        self.assertEqual(advanced["yield_reason"], "blocked-on-evidence-or-capability")
        self.assertEqual(advanced["work_done_this_burst"], 0)


if __name__ == "__main__":
    unittest.main()
