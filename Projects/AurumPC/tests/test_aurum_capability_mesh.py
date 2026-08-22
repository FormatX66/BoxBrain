from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("aurum_capability_mesh", ROOT / "aurum_capability_mesh.py")
assert SPEC and SPEC.loader
aurum_capability_mesh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aurum_capability_mesh)


class CapabilityMeshTests(unittest.TestCase):
    def test_local_and_network_nodes_share_one_field(self) -> None:
        local = {
            "schema": "aurum.capability-graph.v1",
            "nodes": [
                {
                    "id": "cpu:0",
                    "label": "CPU",
                    "source": "profile:cpu",
                    "capabilities": ["compute", "timing"],
                    "properties": {},
                    "safety": "observe-only",
                    "confidence": 1.0,
                }
            ],
        }
        network = {
            "schema": "aurum.network-capability-discovery.v1",
            "nodes": [
                {
                    "id": "network:aa-bb",
                    "label": "Authorized peer",
                    "source": "network-discovery",
                    "capabilities": ["compute", "transport"],
                    "properties": {"authorization": "authorized"},
                    "safety": "observe-only",
                    "confidence": 0.8,
                }
            ],
        }
        mesh = aurum_capability_mesh.build_mesh(local, network)
        self.assertEqual(mesh["node_count"], 2)
        self.assertIn("cpu:0", mesh["index"]["by_capability"]["compute"])
        self.assertIn("network:aa-bb", mesh["index"]["by_capability"]["compute"])
        self.assertIn("authorized-network", mesh["index"]["by_scope"])

    def test_duplicate_evidence_merges_capabilities(self) -> None:
        first = {
            "schema": "one",
            "nodes": [
                {
                    "id": "peer:x",
                    "source": "peer",
                    "capabilities": ["compute"],
                    "properties": {"authorization": "authorized", "evidence": ["a"]},
                    "safety": "observe-only",
                    "confidence": 0.6,
                }
            ],
        }
        second = {
            "schema": "two",
            "nodes": [
                {
                    "id": "peer:x",
                    "source": "aurum-peer",
                    "capabilities": ["transport", "store"],
                    "properties": {"evidence": ["b"]},
                    "safety": "guarded",
                    "confidence": 0.9,
                }
            ],
        }
        mesh = aurum_capability_mesh.build_mesh(first, second)
        node = mesh["nodes"][0]
        self.assertEqual(set(node["capabilities"]), {"compute", "transport", "store"})
        self.assertEqual(node["confidence"], 0.9)
        self.assertEqual(node["safety"], "guarded")
        self.assertEqual(set(node["properties"]["evidence"]), {"a", "b"})


if __name__ == "__main__":
    unittest.main()
