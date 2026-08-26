from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import main


class ChatTreeMCPTests(unittest.TestCase):
    def _paths(self, root: Path) -> tuple[Path, Path, Path]:
        tree = root / "chat-process-tree.json"
        events = root / "shared-state" / "events.jsonl"
        projection = root / "shared-state" / "CURRENT_STATE.json"
        tree.write_text(main.DEFAULT_TREE.read_text(encoding="utf-8"), encoding="utf-8")
        return tree, events, projection

    def _env(self, tree: Path, events: Path, projection: Path):
        return patch.dict(
            os.environ,
            {
                "CHAT_TREE_TREE_PATH": str(tree),
                "CHAT_TREE_EVENTS_PATH": str(events),
                "CHAT_TREE_PROJECTION_PATH": str(projection),
            },
            clear=False,
        )

    def test_tool_contract_exposes_four_tools_with_annotations(self):
        tools = asyncio.run(main._list_tools())
        self.assertEqual(
            {tool.name for tool in tools},
            {"get_tree", "get_state", "route_topic", "post_receipt"},
        )
        by_name = {tool.name: tool for tool in tools}
        self.assertTrue(by_name["get_tree"].annotations.readOnlyHint)
        self.assertTrue(by_name["get_state"].annotations.readOnlyHint)
        self.assertFalse(by_name["route_topic"].annotations.readOnlyHint)
        self.assertFalse(by_name["post_receipt"].annotations.destructiveHint)

    def test_get_tree_and_explicit_sibling_split(self):
        with tempfile.TemporaryDirectory() as folder:
            tree, events, projection = self._paths(Path(folder))
            with self._env(tree, events, projection):
                current = main.dispatch("get_tree", {"focus_id": "chat-tree"})
                self.assertTrue(current["ok"])

                routed = main.dispatch(
                    "route_topic",
                    {
                        "current_id": "chat-tree",
                        "new_node_id": "test-independent-topic",
                        "title": "Independent test topic",
                        "objective": "Exercise an unrelated sibling objective",
                        "relation_hint": "new",
                    },
                )
                self.assertEqual(routed["route"], "sibling_split")
                self.assertEqual(routed["focus_id"], "test-independent-topic")
                self.assertTrue(routed["tree_changed"])

                raw = json.loads(tree.read_text(encoding="utf-8"))
                nodes = {node["node_id"]: node for node in raw["nodes"]}
                self.assertEqual(
                    nodes["test-independent-topic"]["parent_id"],
                    nodes["chat-tree"]["parent_id"],
                )

    def test_verified_receipt_requires_evidence_and_projects_state(self):
        with tempfile.TemporaryDirectory() as folder:
            tree, events, projection = self._paths(Path(folder))
            with self._env(tree, events, projection):
                with self.assertRaises(Exception):
                    main.dispatch(
                        "post_receipt",
                        {
                            "subject_id": "pi3",
                            "subject_kind": "device",
                            "status": "running_verified",
                            "actor": "test-runner",
                            "source": "unit-test",
                        },
                    )

                posted = main.dispatch(
                    "post_receipt",
                    {
                        "subject_id": "pi3",
                        "subject_kind": "device",
                        "status": "running_verified",
                        "actor": "test-runner",
                        "source": "unit-test",
                        "node_id": "pi3-adaptive-driver-tests",
                        "evidence_refs": ["artifact:test-pi3-probe"],
                    },
                )
                self.assertTrue(posted["ok"])
                self.assertEqual(posted["state"]["status"], "running_verified")

                state = main.dispatch("get_state")
                self.assertEqual(
                    state["state"]["subjects"]["pi3"]["status"],
                    "running_verified",
                )
                self.assertTrue(events.exists())
                self.assertTrue(projection.exists())


if __name__ == "__main__":
    unittest.main()
