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
        tools = asyncio.run(main.mcp.list_tools())
        self.assertEqual(
            {tool.name for tool in tools},
            {"get_tree", "get_state", "route_topic", "post_receipt"},
        )
        by_name = {tool.name: tool for tool in tools}
        self.assertTrue(by_name["get_tree"].annotations.read_only_hint)
        self.assertTrue(by_name["get_state"].annotations.read_only_hint)
        self.assertFalse(by_name["route_topic"].annotations.read_only_hint)
        self.assertFalse(by_name["route_topic"].annotations.destructive_hint)
        self.assertFalse(by_name["route_topic"].annotations.idempotent_hint)
        self.assertFalse(by_name["post_receipt"].annotations.destructive_hint)

    def test_streamable_http_app_has_mcp_and_health_routes(self):
        paths = {route.path for route in main.app.routes}
        self.assertIn("/mcp", paths)
        self.assertIn("/healthz", paths)

    def test_get_tree_and_explicit_sibling_split(self):
        with tempfile.TemporaryDirectory() as folder:
            tree, events, projection = self._paths(Path(folder))
            with self._env(tree, events, projection):
                current = main.get_tree("chat-tree")
                self.assertTrue(current["ok"])

                routed = main.route_topic(
                    current_id="chat-tree",
                    new_node_id="test-independent-topic",
                    title="Independent test topic",
                    objective="Exercise an unrelated sibling objective",
                    relation_hint="new",
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
                    main.post_receipt(
                        subject_id="pi3",
                        subject_kind="device",
                        status="running_verified",
                        actor="test-runner",
                        source="unit-test",
                    )

                posted = main.post_receipt(
                    subject_id="pi3",
                    subject_kind="device",
                    status="running_verified",
                    actor="test-runner",
                    source="unit-test",
                    node_id="pi3-adaptive-driver-tests",
                    evidence_refs=["artifact:test-pi3-probe"],
                )
                self.assertTrue(posted["ok"])
                self.assertEqual(posted["state"]["status"], "running_verified")

                state = main.get_state()
                self.assertEqual(
                    state["state"]["subjects"]["pi3"]["status"],
                    "running_verified",
                )
                self.assertTrue(events.exists())
                self.assertTrue(projection.exists())

    def test_confidence_validation_stays_at_adapter_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            tree, events, projection = self._paths(Path(folder))
            with self._env(tree, events, projection):
                with self.assertRaises(ValueError):
                    main.post_receipt(
                        subject_id="future-branch",
                        subject_kind="project",
                        status="queued",
                        actor="test",
                        source="unit-test",
                        confidence=1.5,
                    )


if __name__ == "__main__":
    unittest.main()
