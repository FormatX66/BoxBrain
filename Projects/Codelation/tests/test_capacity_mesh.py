from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from aurum_field import Field  # noqa: E402
from capacity_mesh import (  # noqa: E402
    Capability,
    Node,
    RewardSignal,
    WorkItem,
    assign_parallel,
    compose_capabilities,
    score_reward,
    semantic_recall,
    shadow_state,
)
from capability_growth import growth_field, plan_growth  # noqa: E402
from event_handoff import (  # noqa: E402
    CompletionEvent,
    continue_from_events,
    handoff_field,
)


class CapacityMeshTests(unittest.TestCase):
    def test_verified_generalized_capability_beats_unverified_success(self):
        mature = score_reward(
            RewardSignal(verified=True, reusable=True, generalized=True)
        )
        lucky = score_reward(RewardSignal(uncertainty_reduced=True))
        self.assertGreater(mature, lucky)

    def test_false_claim_and_unsafe_behavior_are_selection_negative(self):
        false = score_reward(RewardSignal(false_claim=True))
        unsafe = score_reward(
            RewardSignal(verified=True, unsafe_or_unauthorized=True)
        )
        self.assertLess(false, 0)
        self.assertLess(unsafe, false)

    def test_semantic_recall_finds_related_meaning(self):
        field = Field()
        field.add("fact", {"node": "BBPI4", "medium": "wifi", "state": "observed"})
        field.add("fact", {"node": "Morris", "medium": "audio", "state": "ready"})
        results = semantic_recall(field, "bbpi4 wifi")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].value["node"], "BBPI4")

    def test_capabilities_compose_without_program_ownership(self):
        caps = [
            Capability(
                "observe-radio",
                frozenset({"radio"}),
                frozenset({"signal-change"}),
            ),
            Capability(
                "correlate",
                frozenset({"signal-change", "history"}),
                frozenset({"identity-evidence"}),
            ),
            Capability(
                "verify",
                frozenset({"identity-evidence"}),
                frozenset({"identity-proof"}),
            ),
        ]
        plan = compose_capabilities(
            caps,
            initial={"radio", "history"},
            required={"identity-proof"},
        )
        self.assertTrue(plan.complete)
        self.assertEqual(
            plan.capabilities,
            ("observe-radio", "correlate", "verify"),
        )

    def test_parallel_assignment_uses_multiple_nodes(self):
        nodes = [
            Node("cpu-a", frozenset({"python"}), capacity=1),
            Node("cpu-b", frozenset({"python"}), capacity=1),
        ]
        work = [
            WorkItem("field", frozenset({"python"})),
            WorkItem("reward", frozenset({"python"})),
        ]
        plan = assign_parallel(work, nodes)
        self.assertEqual(set(plan.assignments), {"cpu-a", "cpu-b"})
        self.assertEqual(plan.unassigned, ())

    def test_missing_node_capability_is_explicit(self):
        plan = assign_parallel(
            [WorkItem("gpu-inference", frozenset({"gpu"}))],
            [Node("cpu", frozenset({"python"}))],
        )
        self.assertEqual(plan.unassigned, ("gpu-inference",))
        self.assertEqual(plan.missing_capabilities, frozenset({"gpu"}))

    def test_shadow_state_round_trip_preserves_meaning(self):
        source = {
            "node": "BBPI4",
            "status": "unconfirmed",
            "routes": ["usb", "wifi"],
        }
        field, rebuilt = shadow_state(source)
        self.assertEqual(rebuilt, source)
        self.assertEqual(field.missing_refs(), set())

    def test_shadow_projection_preserves_distinct_key_meaning(self):
        field, rebuilt = shadow_state({"a": 1, "b": 1})
        self.assertEqual(rebuilt, {"a": 1, "b": 1})
        self.assertEqual(len(field), 3)

    def test_event_completion_fans_out_without_a_clock(self):
        completion = CompletionEvent(
            "kernel-complete",
            "worker-source",
            RewardSignal(verified=True, reusable=True),
            (
                WorkItem("recall-next", frozenset({"python"}), weight=3),
                WorkItem("shadow-next", frozenset({"python"}), weight=3),
            ),
        )
        plan = continue_from_events(
            [completion],
            [
                Node("worker-a", frozenset({"python"}), capacity=1),
                Node("worker-b", frozenset({"python"}), capacity=1),
            ],
        )
        self.assertEqual(set(plan.assignments), {"worker-a", "worker-b"})
        self.assertEqual(plan.unassigned, ())

    def test_no_completion_event_produces_no_work(self):
        plan = continue_from_events(
            [],
            [Node("worker", frozenset({"python"}), capacity=1)],
        )
        self.assertEqual(plan.emitted, ())
        self.assertEqual(plan.assignments, {})

    def test_event_handoff_is_preserved_in_field(self):
        completion = CompletionEvent(
            "verified-result",
            "worker-a",
            RewardSignal(verified=True, generalized=True),
            (WorkItem("next-capability", frozenset({"python"}), weight=2),),
            ("deterministic-test-pass",),
        )
        plan = continue_from_events(
            [completion],
            [Node("worker-b", frozenset({"python"}), capacity=1)],
        )
        field = handoff_field([completion], plan)
        self.assertEqual(field.missing_refs(), set())
        self.assertGreaterEqual(len(field), 3)

    def test_missing_ability_turns_into_build_work(self):
        completion = CompletionEvent(
            "result",
            "worker-a",
            RewardSignal(verified=True),
            (WorkItem("accelerated-task", frozenset({"accelerator"}), weight=2),),
        )
        handoff = continue_from_events(
            [completion],
            [Node("ordinary", frozenset({"python"}), capacity=1)],
        )
        growth = plan_growth(
            [handoff],
            [Node("builder", frozenset({"capability-build"}), capacity=1)],
        )
        self.assertEqual(growth.needs[0].name, "accelerator")
        self.assertEqual(
            growth.assignments,
            {"builder": ("build-capability:accelerator",)},
        )

    def test_missing_builder_remains_explicit(self):
        completion = CompletionEvent(
            "result",
            "worker-a",
            RewardSignal(verified=True),
            (WorkItem("special-task", frozenset({"special-cap"}), weight=2),),
        )
        handoff = continue_from_events(
            [completion],
            [Node("ordinary", frozenset({"python"}), capacity=1)],
        )
        growth = plan_growth(
            [handoff],
            [Node("ordinary", frozenset({"python"}), capacity=1)],
        )
        self.assertEqual(
            growth.missing_builder_capabilities,
            frozenset({"capability-build"}),
        )

    def test_growth_intent_is_declarative_field_state(self):
        completion = CompletionEvent(
            "result",
            "worker-a",
            RewardSignal(verified=True),
            (WorkItem("special-task", frozenset({"special-cap"}), weight=2),),
        )
        handoff = continue_from_events(
            [completion],
            [Node("ordinary", frozenset({"python"}), capacity=1)],
        )
        growth = plan_growth(
            [handoff],
            [Node("builder", frozenset({"capability-build"}), capacity=1)],
        )
        field = growth_field(growth)
        self.assertEqual(field.missing_refs(), set())
        self.assertGreaterEqual(len(field), 3)


def load_tests(loader, tests, pattern):
    """Make convergence execute the event and Slush-media capability suites."""
    event_module = importlib.import_module("Projects.Codelation.tests.test_event_handoff")
    slush_module = importlib.import_module("Projects.Codelation.tests.test_slush_media")
    return unittest.TestSuite(
        [
            tests,
            loader.loadTestsFromModule(event_module),
            loader.loadTestsFromModule(slush_module),
        ]
    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
