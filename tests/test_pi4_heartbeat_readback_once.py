import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / '.github' / 'workflows' / 'aurum-pi4-heartbeat-readback-once.yml'


class Pi4HeartbeatReadbackOnceTests(unittest.TestCase):
    def test_readback_is_one_shot_and_hosted(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn("runs-on: ubuntu-latest", text)
        self.assertNotIn('schedule:', text)
        self.assertNotIn('workflow_dispatch:', text)
        self.assertIn("'.github/workflows/aurum-pi4-heartbeat-readback-once.yml'", text)

    def test_only_fresh_linux_arm64_outbound_nodes_qualify(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn("carrier == 'https-outbound'", text)
        self.assertIn("os_name == 'linux'", text)
        self.assertIn("arch in {'arm64', 'aarch64'}", text)
        self.assertIn("age_seconds <= 900", text)
        self.assertIn("825e5a7b7d4a7aed", text)
        self.assertIn("85404f41d5507372", text)

    def test_main_autobuild_is_deduplicated_and_only_woken_on_fresh_proof(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn("aurum-autobuild.yml", text)
        self.assertIn("active_main", text)
        self.assertIn("if fresh_node and active_main == 0", text)
        self.assertIn("HEARTBEAT_VERIFIED", text)
        self.assertIn("NO_FRESH_HEARTBEAT", text)


if __name__ == '__main__':
    unittest.main()
