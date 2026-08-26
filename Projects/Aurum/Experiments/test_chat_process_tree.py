from __future__ import annotations

import json
from pathlib import Path
import unittest

from chat_process_tree import ChatProcessTree, ChatProcessTreeError, ProcessNode


ROOT = Path(__file__).resolve().parents[3]


def node(node_id: str, *, parent_id: str | None, lane_id: str, sequence: int, **changes) -> ProcessNode:
    values = {
        "node_id": node_id,
        "title": node_id.replace("-", " ").title(),
        "kind": "process" if parent_id else "conversation",
        "state": "active",
        "lane_id": lane_id,
        "sequence": sequence,
        "parent_id": parent_id,
        "state_history": ("active",),
    }
    values.update(changes)
    return ProcessNode(**values)


class ChatProcessTreeTests(unittest.TestCase):
    def base_tree(self) -> ChatProcessTree:
        return ChatProcessTree(
            thread_id="parallel-work",
            root_id="root",
            nodes=(node("root", parent_id=None, lane_id="conversation", sequence=0),),
        )

    def two_lanes(self) -> ChatProcessTree:
        tree = self.base_tree()
        tree = tree.add(
            node(
                "hopper",
                parent_id="root",
                lane_id="hopper",
                sequence=1,
                concepts=("physical-evidence", "reachability"),
            )
        )
        return tree.add(
            node(
                "kernel",
                parent_id="root",
                lane_id="kernel",
                sequence=1,
                concepts=("canary", "physical-evidence"),
                boundary="physical-promotion",
            )
        )

    def test_sibling_lanes_stay_active_when_human_focuses_one(self):
        tree = self.two_lanes()
        self.assertEqual([item.node_id for item in tree.focus_path("hopper")], ["root", "hopper"])
        self.assertEqual(
            {item.node_id for item in tree.active_frontier()},
            {"root", "hopper", "kernel"},
        )

    def test_completing_one_lane_does_not_collapse_the_other(self):
        tree = self.two_lanes().transition("hopper", "completed", evidence_ref="receipt:hopper")
        self.assertEqual(tree.nodes["hopper"].state_history, ("active", "completed"))
        self.assertIn("kernel", {item.node_id for item in tree.active_frontier()})
        self.assertIn("physical-evidence", tree.concept_index())
        self.assertEqual(tree.concept_index()["physical-evidence"], ("hopper", "kernel"))

    def test_merge_preserves_concepts_evidence_sources_and_boundary(self):
        tree = self.two_lanes().transition("hopper", "completed", evidence_ref="receipt:hopper")
        tree = tree.transition("kernel", "completed", evidence_ref="ci:kernel")
        tree = tree.merge_lanes(
            ("hopper", "kernel"),
            node_id="verified-system",
            title="Verified system checkpoint",
            lane_id="integration",
            concepts=("combined-proof",),
        )
        merged = tree.nodes["verified-system"]
        self.assertEqual(merged.merged_from, ("hopper", "kernel"))
        self.assertEqual(
            set(merged.concepts),
            {"combined-proof", "physical-evidence", "reachability", "canary"},
        )
        self.assertEqual(set(merged.evidence_refs), {"receipt:hopper", "ci:kernel"})
        self.assertEqual(merged.boundary, "physical-promotion")
        self.assertFalse(merged.effect_allowed)
        self.assertIsNone(merged.authority_ref)

    def test_consolidation_candidates_require_exact_group_branch_and_terminal_state(self):
        tree = self.base_tree()
        tree = tree.add(
            node(
                "chat-a",
                parent_id="root",
                lane_id="support",
                sequence=1,
                state="completed",
                state_history=("active", "completed"),
            )
        )
        tree = tree.add(
            node(
                "chat-b",
                parent_id="root",
                lane_id="support",
                sequence=2,
                state="failed",
                state_history=("active", "failed"),
            )
        )
        tree = tree.add(
            node(
                "other-lane",
                parent_id="root",
                lane_id="other",
                sequence=3,
                state="completed",
                state_history=("active", "completed"),
            )
        )
        tree = tree.add(node("still-active", parent_id="root", lane_id="support", sequence=4))

        candidates = tree.consolidation_candidates()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["parent_id"], "root")
        self.assertEqual(candidates[0]["lane_id"], "support")
        self.assertEqual(candidates[0]["source_node_ids"], ["chat-a", "chat-b"])
        self.assertEqual(len(candidates[0]["plan_token"]), 64)

    def test_consolidation_archives_sources_and_preserves_provenance(self):
        tree = self.base_tree()
        tree = tree.add(
            node(
                "chat-a",
                parent_id="root",
                lane_id="support",
                sequence=1,
                state="completed",
                state_history=("active", "completed"),
                concepts=("billing",),
                evidence_refs=("chatgpt-conversation:chat-a",),
            )
        )
        tree = tree.add(
            node(
                "chat-b",
                parent_id="root",
                lane_id="support",
                sequence=2,
                state="completed",
                state_history=("active", "completed"),
                concepts=("billing", "refund"),
                evidence_refs=("receipt:chat-b",),
            )
        )
        plan = tree.consolidation_candidates()[0]
        changed = tree.consolidate_branch(
            plan["source_node_ids"],
            plan_token=plan["plan_token"],
            node_id="support-archive",
            title="Support archive",
        )

        self.assertEqual(changed.nodes["chat-a"].state, "archived")
        self.assertEqual(changed.nodes["chat-b"].state, "archived")
        self.assertEqual(changed.nodes["support-archive"].state, "completed")
        self.assertEqual(changed.nodes["support-archive"].merged_from, ("chat-a", "chat-b"))
        self.assertEqual(set(changed.nodes["support-archive"].concepts), {"billing", "refund"})
        self.assertIn("consolidation:support-archive", changed.nodes["chat-a"].evidence_refs)
        self.assertTrue(changed.to_dict()["invariants"]["tree_archive_changes_chatgpt_history"] is False)

    def test_consolidation_rejects_stale_plan_and_mixed_branches(self):
        tree = self.base_tree()
        for node_id, lane_id, sequence in (("chat-a", "one", 1), ("chat-b", "two", 2)):
            tree = tree.add(
                node(
                    node_id,
                    parent_id="root",
                    lane_id=lane_id,
                    sequence=sequence,
                    state="completed",
                    state_history=("active", "completed"),
                )
            )
        with self.assertRaisesRegex(ChatProcessTreeError, "same group and branch"):
            tree.consolidate_branch(
                ("chat-a", "chat-b"),
                plan_token="not-a-valid-plan",
                node_id="bad-archive",
                title="Bad archive",
            )

        same_lane = self.base_tree()
        for node_id, sequence in (("chat-a", 1), ("chat-b", 2)):
            same_lane = same_lane.add(
                node(
                    node_id,
                    parent_id="root",
                    lane_id="one",
                    sequence=sequence,
                    state="completed",
                    state_history=("active", "completed"),
                )
            )
        with self.assertRaisesRegex(ChatProcessTreeError, "stale"):
            same_lane.consolidate_branch(
                ("chat-a", "chat-b"),
                plan_token="not-a-valid-plan",
                node_id="bad-archive",
                title="Bad archive",
            )

    def test_json_round_trip_keeps_nodes_and_safety_invariants(self):
        tree = self.two_lanes()
        payload = tree.to_json(focus_id="hopper")
        loaded = ChatProcessTree.from_json(payload)
        raw = json.loads(payload)
        self.assertEqual(set(loaded.nodes), set(tree.nodes))
        self.assertEqual(raw["focus_path"], ["root", "hopper"])
        self.assertFalse(raw["invariants"]["human_focus_collapses_machine_lanes"])
        self.assertFalse(raw["invariants"]["tree_grants_execution_authority"])

    def test_missing_parent_and_forward_reference_fail_closed(self):
        with self.assertRaises(ChatProcessTreeError):
            ChatProcessTree(
                thread_id="bad",
                root_id="root",
                nodes=(
                    node("root", parent_id=None, lane_id="root", sequence=0),
                    node("lost", parent_id="missing", lane_id="lost", sequence=1),
                ),
            )
        with self.assertRaises(ChatProcessTreeError):
            ChatProcessTree(
                thread_id="bad",
                root_id="root",
                nodes=(
                    node("root", parent_id=None, lane_id="root", sequence=0),
                    node("first", parent_id="root", lane_id="one", sequence=1, dependency_ids=("later",)),
                    node("later", parent_id="root", lane_id="two", sequence=2),
                ),
            )

    def test_invalid_transition_and_authority_inference_fail_closed(self):
        tree = self.two_lanes().transition("hopper", "completed")
        with self.assertRaises(ChatProcessTreeError):
            tree.transition("hopper", "running")
        with self.assertRaises(ChatProcessTreeError):
            ProcessNode(
                node_id="unsafe",
                title="Unsafe",
                kind="process",
                state="active",
                lane_id="unsafe",
                sequence=1,
                parent_id="root",
                effect_allowed=True,
            ).validate_local()

    def test_repository_snapshot_and_dashboard_surface_match_contract(self):
        snapshot = ROOT / "Projects" / "Aurum" / "chat-process-tree.json"
        tree = ChatProcessTree.from_json(snapshot.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(tree.active_frontier()), 3)
        dashboard = (ROOT / "Web" / "Aurum-Arkmatx" / "dashboard.html").read_text(encoding="utf-8")
        surface = (ROOT / "Web" / "Aurum-Arkmatx" / "chat-process-tree-v1.js").read_text(encoding="utf-8")
        self.assertIn("chat-process-tree-v1.js", dashboard)
        self.assertIn("humanFocusCollapsesMachineLanes:false", surface)
        self.assertIn("treeGrantsExecutionAuthority:false", surface)


if __name__ == "__main__":
    unittest.main()
