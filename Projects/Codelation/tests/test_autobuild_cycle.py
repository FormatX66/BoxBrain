import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / 'autobuild_cycle.py'
spec = importlib.util.spec_from_file_location('autobuild_cycle', MODULE_PATH)
autobuild = importlib.util.module_from_spec(spec)
spec.loader.exec_module(autobuild)


class AutobuildSemanticConvergenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state_dir = root / 'autobuild'
        self.state = self.state_dir / 'state.json'
        self.events = self.state_dir / 'events.jsonl'
        self.path_patch = mock.patch.multiple(
            autobuild,
            STATE_DIR=self.state_dir,
            STATE=self.state,
            EVENTS=self.events,
        )
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.tmp.cleanup()

    @staticmethod
    def controller(events=None):
        return {
            'node': 'Aurum-Arkmatx',
            'status': 'active-edge-web-node',
            'capabilities': [
                'uaf_receive',
                'node_heartbeat',
                'node_enroll',
            ],
            'events': events or {'merged': 10, 'outbox': 10},
        }

    def seed_state(self):
        state = json.loads(json.dumps(autobuild.DEFAULT))
        state['cycle'] = 7
        state['targets']['BBPI4']['outbound_enrollment_ready'] = True
        state['targets']['Aurum-Morris']['outbound_enrollment_ready'] = True
        state['targets']['Aurum-Morris']['status'] = 'confirmed'
        state['next'] = 'bootstrap-bbpi4-via-usb-ap-mdns-or-rdp-then-enroll-arkmatx'
        state['last_controller_status'] = {
            'ok': True,
            'node': 'Aurum-Arkmatx',
            'status': 'active-edge-web-node',
            'capabilities': ['node_enroll', 'node_heartbeat', 'uaf_receive'],
            'events': {'merged': 9, 'outbox': 9},
            'time': 100,
        }
        state['last_controller_ack'] = {'ok': True, 'time': 100}
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
        return state

    def test_heartbeat_counters_and_time_do_not_create_progress(self):
        original = self.seed_state()
        before = self.state.read_bytes()
        with mock.patch.object(
            autobuild, 'controller_status', return_value=self.controller({'merged': 999, 'outbox': 999})
        ), mock.patch.object(autobuild, 'controller_emit') as emit:
            autobuild.main()
        self.assertEqual(before, self.state.read_bytes())
        self.assertFalse(self.events.exists())
        emit.assert_not_called()
        self.assertEqual(original['cycle'], json.loads(self.state.read_text())['cycle'])

    def test_real_frontier_change_advances_once_then_converges(self):
        state = self.seed_state()
        state['targets']['BBPI4']['outbound_enrollment_ready'] = False
        state['targets']['Aurum-Morris']['outbound_enrollment_ready'] = False
        state['next'] = 'deploy-and-verify-outbound-node-heartbeat'
        state['last_controller_status']['capabilities'] = ['uaf_receive']
        self.state.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')

        with mock.patch.object(autobuild, 'controller_status', return_value=self.controller()), mock.patch.object(
            autobuild, 'controller_emit', return_value={'status': 'merged'}
        ) as emit:
            autobuild.main()
            first = json.loads(self.state.read_text())
            self.assertEqual(8, first['cycle'])
            self.assertTrue(first.get('semantic_fingerprint'))
            emit.assert_called_once()

            persisted = self.state.read_bytes()
            autobuild.main()
            self.assertEqual(persisted, self.state.read_bytes())
            self.assertEqual(1, emit.call_count)


if __name__ == '__main__':
    unittest.main()
