from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from chat_process_tree import ChatProcessTree, ProcessNode
from chat_tree_bridge import handle_request


def terminal_node(node_id: str, sequence: int) -> ProcessNode:
    return ProcessNode(
        node_id=node_id,
        title=node_id,
        kind="conversation",
        state="completed",
        lane_id="same-branch",
        sequence=sequence,
        parent_id="root",
        evidence_refs=(f"chatgpt-conversation:{node_id}",),
        state_history=("active", "completed"),
    )


class ChatTreeConsolidationBridgeTests(unittest.TestCase):
    def test_plan_then_consolidate_archives_only_canonical_tree_nodes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tree_path = root / "tree.json"
            events_path = root / "events.jsonl"
            projection_path = root / "state.json"
            tree = ChatProcessTree(
                thread_id="test-thread",
                root_id="root",
                nodes=(
                    ProcessNode(
                        node_id="root",
                        title="Root",
                        kind="conversation",
                        state="active",
                        lane_id="root",
                        sequence=0,
                        state_history=("active",),
                    ),
                    terminal_node("chat-a", 1),
                    terminal_node("chat-b", 2),
                ),
            )
            tree_path.write_text(tree.to_json(), encoding="utf-8")

            plan = handle_request(
                {"command": "plan_consolidation"},
                tree_path=tree_path,
                events_path=events_path,
                projection_path=projection_path,
            )
            self.assertEqual(plan["candidate_count"], 1)
            self.assertFalse(plan["underlying_chat_history_supported"])

            candidate = plan["candidates"][0]
            result = handle_request(
                {
                    "command": "consolidate_branch",
                    "source_node_ids": candidate["source_node_ids"],
                    "plan_token": candidate["plan_token"],
                    "new_node_id": "same-branch-archive",
                    "title": "Same branch archive",
                },
                tree_path=tree_path,
                events_path=events_path,
                projection_path=projection_path,
            )
            self.assertEqual(result["archived_source_ids"], ["chat-a", "chat-b"])
            self.assertFalse(result["underlying_chat_history_archived"])
            persisted = json.loads(tree_path.read_text(encoding="utf-8"))
            nodes = {node["node_id"]: node for node in persisted["nodes"]}
            self.assertEqual(nodes["chat-a"]["state"], "archived")
            self.assertEqual(nodes["chat-b"]["state"], "archived")
            self.assertEqual(nodes["same-branch-archive"]["merged_from"], ["chat-a", "chat-b"])


if __name__ == "__main__":
    unittest.main()
