from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]

HARDWARE_SPEC = importlib.util.spec_from_file_location("aurum_hardware", ROOT / "aurum_hardware.py")
assert HARDWARE_SPEC and HARDWARE_SPEC.loader
aurum_hardware = importlib.util.module_from_spec(HARDWARE_SPEC)
HARDWARE_SPEC.loader.exec_module(aurum_hardware)
sys.modules["aurum_hardware"] = aurum_hardware

GRAPH_SPEC = importlib.util.spec_from_file_location("aurum_capability_graph", ROOT / "aurum_capability_graph.py")
assert GRAPH_SPEC and GRAPH_SPEC.loader
aurum_capability_graph = importlib.util.module_from_spec(GRAPH_SPEC)
GRAPH_SPEC.loader.exec_module(aurum_capability_graph)
sys.modules["aurum_capability_graph"] = aurum_capability_graph

AUTONOMY_SPEC = importlib.util.spec_from_file_location("aurum_autonomy_runtime", ROOT / "aurum_autonomy_runtime.py")
assert AUTONOMY_SPEC and AUTONOMY_SPEC.loader
aurum_autonomy_runtime = importlib.util.module_from_spec(AUTONOMY_SPEC)
AUTONOMY_SPEC.loader.exec_module(aurum_autonomy_runtime)
sys.modules["aurum_autonomy_runtime"] = aurum_autonomy_runtime

SPEC = importlib.util.spec_from_file_location("aurum_pursuit_loop", ROOT / "aurum_pursuit_loop.py")
assert SPEC and SPEC.loader
aurum_pursuit_loop = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aurum_pursuit_loop)


def graph_with(*nodes: dict) -> dict:
    return {
        "schema": "test-mesh",
        "nodes": list(nodes),
        "index": {"by_capability": {}},
    }


def authorized_peer(node_id: str, confidence: float = 0.8) -> dict:
    return {
        "id": node_id,
        "label": node_id,
        "source": "peer",
        "capabilities": ["compute", "transport"],
        "properties": {"authorization": "authorized"},
        "safety": "observe-only",
        "confidence": confidence,
    }


class PursuitLoopTests(unittest.TestCase):
    def test_failure_rotates_to_another_path_and_keeps_going(self) -> None:
        mesh = graph_with(authorized_peer("peer:a", 0.9), authorized_peer("peer:b", 0.8))
        intent = {
            "requires": ["compute"],
            "prefers": ["transport"],
            "action_class": "compute-remote-authorized",
            "risk": "low",
        }
        calls: list[str] = []

        def actuator(candidate, _intent):
            node = candidate["node_id"]
            calls.append(node)
            return {"success": node == "peer:b", "latency_ms": 10 if node == "peer:b" else 500}

        checkpoint, history = aurum_pursuit_loop.pursue(
            lambda: mesh,
            intent,
            actuator,
            max_cycles=5,
        )

        self.assertEqual(checkpoint["status"], aurum_pursuit_loop.SUCCEEDED)
        self.assertEqual(calls[:2], ["peer:a", "peer:b"])
        self.assertEqual(checkpoint["attempts"], 2)
        self.assertEqual(history["paths"]["compute-remote-authorized|peer:a"]["failures"], 1)
        self.assertEqual(history["paths"]["compute-remote-authorized|peer:b"]["successes"], 1)

    def test_pre_satisfied_goal_does_not_actuate(self) -> None:
        mesh = graph_with(authorized_peer("peer:a"))
        intent = {"requires": ["compute"], "action_class": "compute-remote-authorized", "risk": "low"}
        calls = []

        def actuator(candidate, _intent):
            calls.append(candidate["node_id"])
            return {"success": True}

        checkpoint, _ = aurum_pursuit_loop.pursue(
            lambda: mesh,
            intent,
            actuator,
            goal_check=lambda _intent: True,
            max_cycles=2,
        )
        self.assertEqual(checkpoint["status"], aurum_pursuit_loop.SUCCEEDED)
        self.assertTrue(checkpoint["goal_observed"])
        self.assertEqual(calls, [])

    def test_boundary_stops_without_calling_actuator(self) -> None:
        mesh = graph_with(
            {
                "id": "network:camera",
                "label": "Camera",
                "source": "network-discovery",
                "capabilities": ["actuate", "transport"],
                "properties": {"authorization": "unverified"},
                "safety": "observe-only",
                "confidence": 0.9,
            }
        )
        intent = {
            "requires": ["actuate"],
            "action_class": "recover-reversible",
            "risk": "low",
        }
        calls = []

        def actuator(candidate, _intent):
            calls.append(candidate["node_id"])
            return {"success": True}

        checkpoint, _ = aurum_pursuit_loop.pursue(lambda: mesh, intent, actuator, max_cycles=2)
        self.assertEqual(checkpoint["status"], aurum_pursuit_loop.BOUNDARY)
        self.assertEqual(calls, [])
        self.assertIn("authorization-boundary", checkpoint["boundary"]["reason"])

    def test_actuator_exception_becomes_evidence_and_loop_continues(self) -> None:
        mesh = graph_with(authorized_peer("peer:a", 0.9), authorized_peer("peer:b", 0.8))
        intent = {
            "requires": ["compute"],
            "action_class": "compute-remote-authorized",
            "risk": "low",
        }
        calls = []

        def actuator(candidate, _intent):
            calls.append(candidate["node_id"])
            if candidate["node_id"] == "peer:a":
                raise RuntimeError("temporary failure")
            return {"success": True, "latency_ms": 15}

        checkpoint, history = aurum_pursuit_loop.pursue(lambda: mesh, intent, actuator, max_cycles=4)
        self.assertEqual(checkpoint["status"], aurum_pursuit_loop.SUCCEEDED)
        self.assertEqual(calls[:2], ["peer:a", "peer:b"])
        failed = history["paths"]["compute-remote-authorized|peer:a"]
        self.assertEqual(failed["failures"], 1)
        self.assertIn("RuntimeError", checkpoint.get("last_receipt", {}).get("error", "") if checkpoint.get("last_node_id") == "peer:a" else "")

    def test_attempt_budget_is_bounded(self) -> None:
        mesh = graph_with(authorized_peer("peer:a"))
        intent = {
            "requires": ["compute"],
            "action_class": "compute-remote-authorized",
            "risk": "low",
        }
        policy = aurum_pursuit_loop.default_policy()
        policy["max_total_attempts"] = 2
        policy["max_attempts_per_path"] = 10
        checkpoint = aurum_pursuit_loop.new_checkpoint(intent, policy=policy)

        def actuator(_candidate, _intent):
            return {"success": False}

        checkpoint, _ = aurum_pursuit_loop.pursue(
            lambda: mesh,
            intent,
            actuator,
            checkpoint=checkpoint,
            max_cycles=10,
        )
        self.assertEqual(checkpoint["status"], aurum_pursuit_loop.EXHAUSTED)
        self.assertEqual(checkpoint["attempts"], 2)


if __name__ == "__main__":
    unittest.main()
