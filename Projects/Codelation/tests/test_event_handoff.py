from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from aurum_field import Field  # noqa: E402
from capacity_mesh import Node, RewardSignal, WorkItem  # noqa: E402
from event_handoff import (  # noqa: E402
    CompletionEvent,
    completion_id,
    continue_from_events,
    emit_handoffs,
    handoff_field,
)
from handoff_ledger import HandoffLedger, ledger_field, restore_ledger  # noqa: E402


class EventHandoffTests(unittest.TestCase):
    def test_no_event_means_no_continuation(self):
        plan = continue_from_events([], [Node("worker", frozenset({"python"}))])
        self.assertEqual(plan.emitted, ())
        self.assertEqual(plan.assignments, {})

    def test_completion_fans_out_independent_jobs(self):
        completion = CompletionEvent(
            "kernel",
            "builder",
            RewardSignal(verified=True, reusable=True),
            (
                WorkItem("recall", frozenset({"python"}), 4),
                WorkItem("shadow", frozenset({"python"}), 4),
            ),
        )
        plan = continue_from_events(
            [completion],
            [
                Node("worker-a", frozenset({"python"}), 1),
                Node("worker-b", frozenset({"python"}), 1),
            ],
        )
        self.assertEqual(set(plan.assignments), {"worker-a", "worker-b"})
        self.assertEqual(plan.unassigned, ())

    def test_one_capability_gap_does_not_block_other_work(self):
        completion = CompletionEvent(
            "fanout",
            "worker-a",
            RewardSignal(verified=True),
            (
                WorkItem("ordinary", frozenset({"python"}), 5),
                WorkItem("accelerated", frozenset({"accelerator"}), 5),
            ),
        )
        plan = continue_from_events(
            [completion],
            [Node("worker", frozenset({"python"}), 1)],
        )
        self.assertEqual(plan.assignments, {"worker": ("ordinary",)})
        self.assertEqual(plan.unassigned, ("accelerated",))
        self.assertEqual(plan.missing_capabilities, frozenset({"accelerator"}))

    def test_duplicate_followups_converge(self):
        followup = WorkItem("verify", frozenset({"python"}), 3)
        emitted = emit_handoffs(
            [
                CompletionEvent("a", "one", RewardSignal(verified=True), (followup,)),
                CompletionEvent("b", "two", RewardSignal(verified=True), (followup,)),
            ]
        )
        self.assertEqual(len(emitted), 1)

    def test_policy_rejected_completion_does_not_propagate(self):
        followup = (WorkItem("next", frozenset({"python"})),)
        rejected = CompletionEvent(
            "rejected",
            "worker",
            RewardSignal(false_claim=True),
            followup,
        )
        self.assertEqual(emit_handoffs([rejected]), ())

    def test_stronger_evidence_gets_more_selection_weight(self):
        followup = WorkItem("next", frozenset({"python"}), 1)
        strong = emit_handoffs(
            [CompletionEvent("strong", "w", RewardSignal(verified=True, reusable=True, generalized=True), (followup,))]
        )[0]
        weak = emit_handoffs(
            [CompletionEvent("weak", "w", RewardSignal(uncertainty_reduced=True), (followup,))]
        )[0]
        self.assertGreater(strong.work.weight, weak.work.weight)

    def test_completion_identity_is_deterministic(self):
        left = CompletionEvent(
            "done",
            "worker",
            RewardSignal(verified=True),
            (WorkItem("next", frozenset({"b", "a"}), 2),),
            ("z", "a"),
        )
        right = CompletionEvent(
            "done",
            "worker",
            RewardSignal(verified=True),
            (WorkItem("next", frozenset({"a", "b"}), 2),),
            ("a", "z"),
        )
        self.assertEqual(completion_id(left), completion_id(right))

    def test_work_can_move_to_another_matching_worker(self):
        completion = CompletionEvent(
            "observed",
            "source-worker",
            RewardSignal(verified=True),
            (WorkItem("analyze", frozenset({"python"}), 2),),
        )
        plan = continue_from_events(
            [completion],
            [Node("compute-worker", frozenset({"python"}), 1)],
        )
        self.assertEqual(plan.assignments, {"compute-worker": ("analyze",)})

    def test_field_projection_preserves_provenance(self):
        completion = CompletionEvent(
            "done",
            "worker-a",
            RewardSignal(verified=True, reusable=True),
            (WorkItem("next", frozenset({"python"}), 2),),
            ("test-pass",),
        )
        plan = continue_from_events(
            [completion],
            [Node("worker-b", frozenset({"python"}), 1)],
        )
        field = handoff_field([completion], plan)
        self.assertEqual(field.missing_refs(), set())
        self.assertGreaterEqual(len(field), 3)

    def test_no_gain_is_deprioritized_not_deleted(self):
        followup = WorkItem("retry-with-new-evidence", frozenset({"python"}), 10)
        repeated = emit_handoffs(
            [CompletionEvent("repeat", "w", RewardSignal(repeated_without_gain=True), (followup,))]
        )[0]
        neutral = emit_handoffs(
            [CompletionEvent("neutral", "w", RewardSignal(), (followup,))]
        )[0]
        self.assertLess(repeated.work.weight, neutral.work.weight)
        self.assertGreaterEqual(repeated.work.weight, 1)

    def test_durable_work_record_round_trip(self):
        completion = CompletionEvent(
            "source",
            "origin",
            RewardSignal(verified=True),
            (WorkItem("durable", frozenset({"python"}), 4),),
        )
        plan = continue_from_events([completion], [])
        original = HandoffLedger.from_plan(plan)
        persisted = Field.absorb(ledger_field(original).project())
        restored = restore_ledger(persisted)
        self.assertEqual(restored.entries(), original.entries())

    def test_matching_capacity_selects_durable_work(self):
        completion = CompletionEvent(
            "source",
            "origin",
            RewardSignal(verified=True),
            (WorkItem("durable", frozenset({"python"}), 4),),
        )
        ledger = HandoffLedger.from_plan(continue_from_events([completion], []))
        selected = ledger.claim(Node("worker", frozenset({"python"}), 1))
        self.assertIsNotNone(selected)
        self.assertEqual(selected.work.name, "durable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
