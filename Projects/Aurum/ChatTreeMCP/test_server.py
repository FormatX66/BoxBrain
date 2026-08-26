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

    def test_tool_contract_exposes_live_sync_and_consolidation_tools_with_annotations(self):
        tools = asyncio.run(main.mcp.list_tools())
        self.assertEqual(
            {tool.name for tool in tools},
            {
                "get_tree",
                "get_state",
                "plan_consolidation",
                "consolidate_branch",
                "route_topic",
                "post_receipt",
                "publish_live_state",
                "read_live_state",
                "dispatch_farmer_objective",
            },
        )
        by_name = {tool.name: tool for tool in tools}
        self.assertTrue(by_name["get_tree"].annotations.read_only_hint)
        self.assertTrue(by_name["get_state"].annotations.read_only_hint)
        self.assertTrue(by_name["read_live_state"].annotations.read_only_hint)
        self.assertTrue(by_name["plan_consolidation"].annotations.read_only_hint)
        self.assertFalse(by_name["consolidate_branch"].annotations.read_only_hint)
        self.assertTrue(by_name["consolidate_branch"].annotations.destructive_hint)
        self.assertFalse(by_name["route_topic"].annotations.read_only_hint)
        self.assertFalse(by_name["route_topic"].annotations.destructive_hint)
        self.assertFalse(by_name["route_topic"].annotations.idempotent_hint)
        self.assertFalse(by_name["post_receipt"].annotations.destructive_hint)
        self.assertFalse(by_name["publish_live_state"].annotations.read_only_hint)
        self.assertFalse(by_name["publish_live_state"].annotations.destructive_hint)
        self.assertFalse(by_name["dispatch_farmer_objective"].annotations.read_only_hint)
        self.assertTrue(by_name["dispatch_farmer_objective"].annotations.open_world_hint)

    def test_farmer_dispatch_is_objective_only_and_returns_ingress_receipt(self):
        class Response:
            status = 204
            headers = {"x-github-request-id": "REQ_TEST"}

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, _limit):
                return b""

        with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}, clear=False):
            with patch.object(main.urlrequest, "urlopen", return_value=Response()) as opened:
                result = main.dispatch_farmer_objective("farmer-test", "Reach verified completion.")
        self.assertEqual(result["status"], "dispatch_accepted")
        self.assertEqual(result["github_request_id"], "REQ_TEST")
        self.assertEqual(len(result["dispatch_receipt"]), 32)
        payload = json.loads(opened.call_args.args[0].data)
        self.assertEqual(payload["event_type"], "aurum_farmer_event")
        self.assertEqual(payload["client_payload"]["objective_id"], "farmer-test")

    def test_farmer_missing_credential_remains_machine_only(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "", "AURUM_FARMER_GITHUB_TOKEN_FILE": ""}, clear=False):
            result = main.dispatch_farmer_objective("farmer-test", "Continue.")
        self.assertEqual(result["status"], "machine_blocked")
        self.assertFalse(result["human_required"])

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

    def test_publish_and_read_live_state_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            tree, events, projection = self._paths(Path(folder))
            with self._env(tree, events, projection):
                with self.assertRaises(Exception):
                    main.publish_live_state(
                        subject_id="chat:mcp-test",
                        status="running_verified",
                        current_action="Exercise the MCP publisher",
                        blocker="No public deployment in this fixture",
                        evidence=[],
                        next_action="Read through the MCP consumer",
                        actor="chat:mcp-test",
                        source="mcp-unit-test",
                    )

                published = main.publish_live_state(
                    subject_id="chat:mcp-test",
                    status="running_verified",
                    current_action="Exercise the MCP publisher",
                    blocker="No public deployment in this fixture",
                    evidence=["test:test_server.py"],
                    next_action="Read through the MCP consumer",
                    actor="chat:mcp-test",
                    source="mcp-unit-test",
                    node_id="cross-chat-context-cache",
                    event_id="evt-mcp-live-sync-e2e",
                )
                consumed = main.read_live_state(
                    subject_id="chat:mcp-test",
                    include_history=True,
                )

                self.assertFalse(published["authority_granted"])
                state = consumed["live_state"]["subjects"]["chat:mcp-test"]
                self.assertEqual(state["event_id"], "evt-mcp-live-sync-e2e")
                self.assertEqual(state["current_action"], "Exercise the MCP publisher")
                self.assertEqual(state["blocker"], "No public deployment in this fixture")
                self.assertEqual(state["evidence"], ["test:test_server.py"])
                self.assertEqual(state["next_action"], "Read through the MCP consumer")
                self.assertFalse(state["grants_execution_authority"])
                self.assertEqual(consumed["live_state"]["event_count"], 1)


if __name__ == "__main__":
    unittest.main()
