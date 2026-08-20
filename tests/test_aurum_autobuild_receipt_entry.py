import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / 'Projects' / 'AurumBridge' / 'aurum_autobuild_entry.py'
spec = importlib.util.spec_from_file_location('aurum_autobuild_entry_test', MODULE_PATH)
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class AurumReceiptEntryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.results = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def state(self):
        state = json.loads(json.dumps(entry.core.DEFAULT))
        state['targets']['Aurum-Morris']['outbound_enrollment_ready'] = True
        state['targets']['BBPI4']['outbound_enrollment_ready'] = True
        state['targets']['Aurum-Morris']['status'] = 'confirmed'
        return state

    def receipt(self, run_id=100, state='PI4_SEED_OK'):
        payload = {
            'schema': 'aurum-pi4-seed-receipt-v1',
            'state': state,
            'github_workflow_run': run_id,
            'github_run_attempt': 1,
            'observed_at': '2026-08-20T12:18:19Z',
            'data': {
                'aurum_live_verified': True,
                'peer_self_test_verified': True,
                'gold_seed_preserved': True,
                'host_key_pretrusted': True,
                'architecture': 'arm64',
                'transport': 'usb-c-ssh',
                'address': '10.12.194.1',
                'seed_sha256': 'a' * 64,
                'source_commit': 'b' * 40,
            },
        }
        path = self.results / f'pi4-seed-{run_id}-attempt-1.json'
        path.write_text(json.dumps(payload), encoding='utf-8')
        return payload

    def test_strict_verified_seed_is_consumed(self):
        state = self.state()
        self.receipt()
        self.assertTrue(entry.apply_verified_pi4_seed(state, self.results))
        bb = state['targets']['BBPI4']
        self.assertTrue(bb['physical_seed_verified'])
        self.assertEqual('usb-c-ssh', bb['physical_seed_transport'])
        self.assertEqual('arm64', bb['physical_seed_architecture'])
        self.assertNotEqual('confirmed', bb['status'])

    def test_bridge_advances_only_from_bootstrap_to_enrollment(self):
        state = self.state()
        self.receipt()
        entry.apply_verified_pi4_seed(state, self.results)
        original = entry.core.choose_next
        try:
            entry.install_receipt_bridge(entry.core, self.results)
            self.assertEqual(
                'enroll-bbpi4-arkmatx-and-verify-heartbeat',
                entry.core.choose_next(state),
            )
            self.assertNotEqual('confirmed', state['targets']['BBPI4']['status'])
        finally:
            entry.core.choose_next = original

    def test_newer_failure_cannot_manufacture_success(self):
        state = self.state()
        self.receipt(run_id=100, state='PI4_SEED_OK')
        self.receipt(run_id=101, state='PI4_SEED_FAILURE')
        self.assertFalse(entry.apply_verified_pi4_seed(state, self.results))
        self.assertFalse(state['targets']['BBPI4'].get('physical_seed_verified', False))

    def test_untrusted_transport_is_rejected(self):
        state = self.state()
        payload = self.receipt(run_id=102)
        payload['data']['transport'] = 'wifi'
        (self.results / 'pi4-seed-102-attempt-1.json').write_text(json.dumps(payload), encoding='utf-8')
        self.assertFalse(entry.apply_verified_pi4_seed(state, self.results))

    def test_receipt_metadata_does_not_change_semantic_fingerprint(self):
        state = self.state()
        self.receipt(run_id=100)
        entry.apply_verified_pi4_seed(state, self.results)
        first = entry.core.semantic_fingerprint(state)
        self.receipt(run_id=101)
        entry.apply_verified_pi4_seed(state, self.results)
        second = entry.core.semantic_fingerprint(state)
        self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
