from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from chat_process_tree import ChatProcessTree, ProcessNode
from chat_topic_router import TopicContext, TopicSignal, classify_topic_change, route_into_tree
from chat_tree_bridge import handle_request
from shared_state_bus import SharedStateBus, SharedStateError, StateEvent


class ChatTreeRoutingTests(unittest.TestCase):
    def tree(self) -> ChatProcessTree:
        return ChatProcessTree(
            thread_id="aurum",
            root_id="root",
            nodes=(
                ProcessNode(
                    node_id="root",
                    title="Aurum work",
                    kind="conversation",
                    state="active",
                    lane_id="conversation",
                    sequence=0,
                    summary="Coordinate Aurum work",
                    state_history=("active",),
                ),
                ProcessNode(
                    node_id="chat-tree",
                    title="Chat Tree",
                    kind="process",
                    state="active",
                    lane_id="chat-tree",
                    sequence=1,
                    parent_id="root",
                    summary="Build topic routing and shared state",
                    concepts=("chat-tree", "shared-state"),
                    state_history=("active",),
                ),
            ),
        )

    def test_explicit_new_topic_becomes_sibling(self):
        changed, decision, focus = route_into_tree(
            self.tree(),
            current_id="chat-tree",
            new_node_id="pi3-adaptive-driver-tests",
            incoming=TopicSignal(
                title="Pi3 Adaptive Driver Tests",
                objective="Boot physical Pi3 and test adaptive kernel drivers",
                concepts=("pi3", "adaptive-kernel"),
                relation_hint="new",
            ),
        )
        self.assertEqual(decision.route, "sibling_split")
        self.assertEqual(changed.nodes["pi3-adaptive-driver-tests"].parent_id, "root")
        self.assertEqual(focus, "pi3-adaptive-driver-tests")
        self.assertIn("chat-tree", {node.node_id for node in changed.active_frontier()})

    def test_explicit_subproblem_becomes_child(self):
        changed, decision, _ = route_into_tree(
            self.tree(),
            current_id="chat-tree",
            new_node_id="gpt-bridge",
            incoming=TopicSignal(
                title="GPT bridge",
                objective="Expose Chat Tree state through a small GPT bridge",
                concepts=("chat-tree", "shared-state"),
                relation_hint="subproblem",
            ),
        )
        self.assertEqual(decision.route, "child_split")
        self.assertEqual(changed.nodes["gpt-bridge"].parent_id, "chat-tree")

    def test_fallback_high_overlap_continues(self):
        decision = classify_topic_change(
            TopicContext(
                node_id="chat-tree",
                title="Chat Tree shared state",
                objective="Build chat tree shared state routing",
                concepts=("chat-tree", "shared-state"),
            ),
            TopicSignal(
                title="Chat Tree state routing",
                objective="Keep building shared state chat routing",
                concepts=("chat-tree", "shared-state"),
            ),
        )
        self.assertEqual(decision.route, "continue")


class SharedStateTests(unittest.TestCase):
    def test_verified_status_requires_evidence(self):
        event = StateEvent(
            subject_id="pi3",
            subject_kind="device",
            status="running_verified",
            actor="pi3-runner",
            source="probe",
        )
        with self.assertRaises(SharedStateError):
            event.validate()

    def test_receipt_projects_latest_state_and_preserves_history(self):
        bus = SharedStateBus()
        first = StateEvent(
            event_id="evt-1",
            timestamp="2026-08-25T20:00:00Z",
            subject_id="pi3",
            subject_kind="device",
            status="running_unverified",
            actor="runner",
            source="boot",
        )
        second = StateEvent(
            event_id="evt-2",
            timestamp="2026-08-25T20:01:00Z",
            subject_id="pi3",
            subject_kind="device",
            status="running_verified",
            actor="runner",
            source="probe",
            evidence_refs=("artifact:pi3-probe",),
        )
        bus.apply(first)
        bus.apply(second)
        self.assertEqual(len(bus.events), 2)
        self.assertEqual(bus.latest("pi3").status, "running_verified")
        self.assertEqual(bus.latest("pi3").evidence_refs, ("artifact:pi3-probe",))
        self.assertFalse(bus.to_projection_dict()["invariants"]["chat_memory_is_source_of_truth"])

    def test_jsonl_round_trip(self):
        bus = SharedStateBus(
            (
                StateEvent(
                    event_id="evt-1",
                    timestamp="2026-08-25T20:00:00Z",
                    subject_id="chat-tree",
                    subject_kind="project",
                    status="queued",
                    actor="future-branch",
                    source="chat",
                ),
            )
        )
        loaded = SharedStateBus.from_jsonl(bus.to_jsonl())
        self.assertEqual(loaded.latest("chat-tree").status, "queued")

    def test_stale_writers_reload_under_lock_and_keep_both_events(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            events_path = root / "events.jsonl"
            projection_path = root / "CURRENT_STATE.json"
            first_writer = SharedStateBus.load(events_path)
            second_writer = SharedStateBus.load(events_path)

            first_writer.append_file(
                events_path,
                StateEvent(
                    event_id="evt-writer-1",
                    timestamp="2026-08-26T12:00:00Z",
                    subject_id="cross-chat-live-sync",
                    subject_kind="process",
                    status="running_unverified",
                    actor="chat-a",
                    source="unit-test",
                ),
                projection_path=projection_path,
            )
            first_journal_bytes = events_path.read_bytes()
            second_writer.append_file(
                events_path,
                StateEvent(
                    event_id="evt-writer-2",
                    timestamp="2026-08-26T12:01:00Z",
                    subject_id="cross-chat-live-sync",
                    subject_kind="process",
                    status="running_verified",
                    actor="chat-b",
                    source="unit-test",
                    evidence_refs=("test:writer-2-readback",),
                ),
                projection_path=projection_path,
            )

            loaded = SharedStateBus.load(events_path)
            projection = json.loads(projection_path.read_text(encoding="utf-8"))
            self.assertTrue(events_path.read_bytes().startswith(first_journal_bytes))
            self.assertEqual(len(loaded.events), 2)
            self.assertEqual(loaded.latest("cross-chat-live-sync").event_id, "evt-writer-2")
            self.assertEqual(projection["event_count"], 2)
            self.assertEqual(
                projection["subjects"]["cross-chat-live-sync"]["event_id"],
                "evt-writer-2",
            )


class BridgeTests(unittest.TestCase):
    def test_bridge_routes_topic_and_posts_verified_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tree_path = root / "tree.json"
            events_path = root / "events.jsonl"
            projection_path = root / "CURRENT_STATE.json"
            tree = ChatProcessTree(
                thread_id="aurum",
                root_id="root",
                nodes=(
                    ProcessNode(
                        node_id="root",
                        title="Aurum",
                        kind="conversation",
                        state="active",
                        lane_id="root",
                        sequence=0,
                        state_history=("active",),
                    ),
                    ProcessNode(
                        node_id="chat-tree",
                        title="Chat Tree",
                        kind="process",
                        state="active",
                        lane_id="chat-tree",
                        sequence=1,
                        parent_id="root",
                        summary="Shared chat state",
                        state_history=("active",),
                    ),
                ),
            )
            tree_path.write_text(tree.to_json(focus_id="chat-tree"), encoding="utf-8")

            routed = handle_request(
                {
                    "command": "route_topic",
                    "current_id": "chat-tree",
                    "new_node_id": "pi3",
                    "title": "Pi3",
                    "objective": "Boot and test the physical Pi3",
                    "relation_hint": "new",
                },
                tree_path=tree_path,
                events_path=events_path,
                projection_path=projection_path,
            )
            self.assertEqual(routed["route"], "sibling_split")
            self.assertTrue(routed["tree_changed"])

            posted = handle_request(
                {
                    "command": "post_receipt",
                    "subject_id": "pi3",
                    "subject_kind": "device",
                    "status": "running_verified",
                    "actor": "pi3-runner",
                    "source": "physical-probe",
                    "node_id": "pi3",
                    "evidence_refs": ["artifact:physical-probe"],
                },
                tree_path=tree_path,
                events_path=events_path,
                projection_path=projection_path,
            )
            self.assertEqual(posted["state"]["status"], "running_verified")
            projected = json.loads(projection_path.read_text(encoding="utf-8"))
            self.assertEqual(projected["subjects"]["pi3"]["status"], "running_verified")

    def test_live_state_publish_and_readback_preserve_required_fields_and_invariants(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tree_path = root / "tree.json"
            events_path = root / "events.jsonl"
            projection_path = root / "CURRENT_STATE.json"
            tree_path.write_text(self._minimal_tree().to_json(focus_id="live-sync"), encoding="utf-8")

            request = {
                "command": "publish_live_state",
                "event_id": "evt-live-sync-e2e",
                "subject_id": "chat:test-publisher",
                "subject_kind": "chat",
                "status": "running_verified",
                "current_action": "Publish the live state contract",
                "blocker": "Public connector not deployed yet",
                "evidence": ["test:test_chat_tree_shared_state.py"],
                "next_action": "Read the event through the consumer action",
                "actor": "chat:test-publisher",
                "source": "unit-test:e2e",
                "node_id": "live-sync",
            }
            without_evidence = dict(request, event_id="evt-missing-evidence", evidence=[])
            with self.assertRaises(SharedStateError):
                handle_request(
                    without_evidence,
                    tree_path=tree_path,
                    events_path=events_path,
                    projection_path=projection_path,
                )

            published = handle_request(
                request,
                tree_path=tree_path,
                events_path=events_path,
                projection_path=projection_path,
            )
            consumed = handle_request(
                {
                    "command": "read_live_state",
                    "subject_id": "chat:test-publisher",
                    "include_history": True,
                },
                tree_path=tree_path,
                events_path=events_path,
                projection_path=projection_path,
            )

            self.assertEqual(published["event_count"], 1)
            self.assertFalse(published["authority_granted"])
            live = consumed["live_state"]["subjects"]["chat:test-publisher"]
            self.assertEqual(live["status"], "running_verified")
            self.assertEqual(live["current_action"], request["current_action"])
            self.assertEqual(live["blocker"], request["blocker"])
            self.assertEqual(live["evidence"], request["evidence"])
            self.assertEqual(live["next_action"], request["next_action"])
            self.assertTrue(live["verified_runtime"])
            self.assertFalse(live["grants_execution_authority"])
            self.assertEqual(consumed["live_state"]["events"][0]["event_id"], "evt-live-sync-e2e")
            self.assertFalse(consumed["chat_memory_used_as_source"])

    @staticmethod
    def _minimal_tree() -> ChatProcessTree:
        return ChatProcessTree(
            thread_id="aurum",
            root_id="root",
            nodes=(
                ProcessNode(
                    node_id="root",
                    title="Aurum",
                    kind="conversation",
                    state="active",
                    lane_id="root",
                    sequence=0,
                    state_history=("active",),
                ),
                ProcessNode(
                    node_id="live-sync",
                    title="Cross-Chat Live Sync",
                    kind="process",
                    state="active",
                    lane_id="live-sync",
                    sequence=1,
                    parent_id="root",
                    state_history=("active",),
                ),
            ),
        )


if __name__ == "__main__":
    unittest.main()
