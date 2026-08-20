from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
EVENT_BRIDGE = ROOT / '.github' / 'workflows' / 'aurum-event-bridge.yml'
AUTOBUILD = ROOT / '.github' / 'workflows' / 'aurum-autobuild.yml'


class EventDrivenContinuationTests(unittest.TestCase):
    def test_dual_seed_completion_is_a_continuation_source(self):
        text = EVENT_BRIDGE.read_text(encoding='utf-8')
        self.assertIn('- Aurum Dual Seed Lanes', text)
        self.assertIn('workflow_run:', text)
        self.assertIn("workflow='aurum-autobuild.yml'", text)
        self.assertIn('action=deduplicated', text)

    def test_event_bridge_change_wakes_main_autobuild(self):
        text = AUTOBUILD.read_text(encoding='utf-8')
        self.assertIn("- '.github/workflows/aurum-event-bridge.yml'", text)
        self.assertIn('push:', text)


if __name__ == '__main__':
    unittest.main()
