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

SPEC = importlib.util.spec_from_file_location("aurum_autonomy_runtime", ROOT / "aurum_autonomy_runtime.py")
assert SPEC and SPEC.loader
aurum_autonomy_runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aurum_autonomy_runtime)


def graph_with(*nodes: dict) -> dict:
    return {
        "schema": "test-graph",
        "nodes": list(nodes),
        "index": {"by_capability": {}},
    }


class AutonomyRuntimeTests(unittest.TestCase):
    def test_reversible_local_recovery_is_auto(self) -> None:
        graph = graph_with(
            {
                "id": "input:event5",
                "label": "ELAN Touchpad",
                "source": "profile:input",
                "capabilities": ["actuate", "recover", "sense"],
                "properties": {"wake": "enabled"},
                "safety": "observe-only",
                "confidence": 0.9,
            }
        )
        intent = {
            "requires": ["actuate", "recover"],
            "action_class": "recover-reversible",
            "risk": "low",
            "irreversible": False,
            "destructive": False,
        }
        decision = aurum_autonomy_runtime.plan_with_envelope(graph, intent)
        self.assertEqual(decision["decision"], "AUTO")
        self.assertFalse(decision["human_interrupt_required"])
        self.assertEqual(decision["selected"]["node_id"], "input:event5")

    def test_unverified_network_actuation_escalates(self) -> None:
        graph = graph_with(
            {
                "id": "network:camera",
                "label": "Camera",
                "source": "network-discovery",
                "capabilities": ["actuate", "sense", "transport"],
                "properties": {"authorization": "unverified"},
                "safety": "observe-only",
                "confidence": 0.8,
            }
        )
        intent = {
            "requires": ["actuate"],
            "action_class": "recover-reversible",
            "risk": "low",
        }
        decision = aurum_autonomy_runtime.plan_with_envelope(graph, intent)
        self.assertEqual(decision["decision"], "ESCALATE")
        self.assertTrue(decision["human_interrupt_required"])
        self.assertIn(
            "authorization-boundary",
            decision["escalation_candidate"]["policy"]["reasons"],
        )

    def test_privacy_sensitive_sensor_read_escalates(self) -> None:
        node = {
            "id": "network:watch",
            "label": "Watch",
            "source": "network-discovery",
            "capabilities": ["sense", "transport"],
            "properties": {"authorization": "authorized"},
            "safety": "observe-only",
            "confidence": 0.9,
        }
        intent = {
            "requires": ["sense"],
            "action_class": "sensor-read-authorized",
            "risk": "low",
            "privacy_sensitive": True,
            "health_sensitive": True,
        }
        policy = aurum_autonomy_runtime.evaluate_candidate(node, intent)
        self.assertEqual(policy["decision"], "ESCALATE")
        self.assertIn("privacy-boundary", policy["reasons"])
        self.assertIn("health-data-boundary", policy["reasons"])

    def test_destructive_action_never_auto_by_default(self) -> None:
        node = {
            "id": "block:nvme0n1",
            "source": "profile:block",
            "capabilities": ["store"],
            "properties": {},
            "safety": "observe-only",
        }
        policy = aurum_autonomy_runtime.evaluate_candidate(
            node,
            {
                "requires": ["store"],
                "action_class": "state-replicate-authorized",
                "destructive": True,
                "risk": "high",
            },
        )
        self.assertEqual(policy["decision"], "ESCALATE")
        self.assertIn("destructive-boundary", policy["reasons"])

    def test_receipts_compound_into_future_ranking(self) -> None:
        graph = graph_with(
            {
                "id": "peer:a",
                "label": "Peer A",
                "source": "peer",
                "capabilities": ["compute", "transport"],
                "properties": {"authorization": "authorized"},
                "safety": "observe-only",
                "confidence": 0.8,
            },
            {
                "id": "peer:b",
                "label": "Peer B",
                "source": "peer",
                "capabilities": ["compute", "transport"],
                "properties": {"authorization": "authorized"},
                "safety": "observe-only",
                "confidence": 0.8,
            },
        )
        intent = {
            "requires": ["compute"],
            "prefers": ["transport"],
            "action_class": "compute-remote-authorized",
            "risk": "low",
        }
        history = aurum_autonomy_runtime.empty_history()
        for _ in range(5):
            history = aurum_autonomy_runtime.record_receipt(
                history,
                {
                    "node_id": "peer:b",
                    "action_class": "compute-remote-authorized",
                    "success": True,
                    "latency_ms": 20,
                    "queue_delay_ms": 4,
                    "execution_ms": 16,
                },
            )
        history = aurum_autonomy_runtime.record_receipt(
            history,
            {
                "node_id": "peer:a",
                "action_class": "compute-remote-authorized",
                "success": False,
                "latency_ms": 5000,
            },
        )
        decision = aurum_autonomy_runtime.plan_with_envelope(graph, intent, history=history)
        self.assertEqual(decision["decision"], "AUTO")
        self.assertEqual(decision["selected"]["node_id"], "peer:b")
        self.assertGreater(decision["selected"]["history_adjustment"], 0)


if __name__ == "__main__":
    unittest.main()
