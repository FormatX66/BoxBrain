import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "seed"))
from aurum_live import (  # noqa: E402
    READ_ONLY_CAPABILITIES,
    add_evidence,
    build_graph,
    load_graph,
    loopback_self_test,
    save_graph,
    verify_graph,
)


class AurumLiveTests(unittest.TestCase):
    def graph(self):
        return build_graph(
            node_name="BBPI4/Aurum",
            hostname="bbpi4",
            python_version="3.13.12",
            architecture="aarch64",
            install_path="/opt/boxbrain/codelation",
            seed_version=1,
        )

    def test_minimum_live_graph_has_only_bounded_capabilities(self):
        graph = self.graph()
        self.assertEqual([], verify_graph(graph))
        capabilities = [
            node["name"] for node in graph["nodes"] if node.get("type") == "capability"
        ]
        self.assertEqual(list(READ_ONLY_CAPABILITIES), capabilities)
        self.assertFalse(any("shell" in item or "exec" in item or "write" in item for item in capabilities))

    def test_graph_round_trip_and_tamper_detection(self):
        graph = self.graph()
        add_evidence(graph, name="unit-test", result="passed")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aurum-live.json"
            save_graph(path, graph)
            restored = load_graph(path)
            self.assertEqual(graph["digest"], restored["digest"])
            restored["nodes"][0]["name"] = "tampered"
            self.assertIn("digest", verify_graph(restored))

    def test_loopback_heartbeat_is_bounded_and_updates_sequence(self):
        graph = self.graph()
        result = loopback_self_test(graph)
        self.assertEqual(1, result["sequence"])
        self.assertEqual("127.0.0.1", result["peer_host"])
        self.assertEqual(204, result["status"])
        self.assertEqual(1, graph["heartbeat_sequence"])
        self.assertEqual([], verify_graph(graph))


if __name__ == "__main__":
    unittest.main()
