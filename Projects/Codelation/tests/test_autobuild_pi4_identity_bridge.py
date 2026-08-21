import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO / 'Projects' / 'AurumBridge' / 'aurum_autobuild_entry.py'
EVENT_BRIDGE = REPO / '.github' / 'workflows' / 'aurum-event-bridge.yml'
PI4_CONTINUATION = REPO / '.github' / 'workflows' / 'aurum-pi4-continuation-failsafe.yml'
spec = importlib.util.spec_from_file_location('aurum_autobuild_identity_test', MODULE_PATH)
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class Pi4IdentityBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.results = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def state(self):
        state = json.loads(json.dumps(entry.core.DEFAULT))
        state['targets']['Aurum-Morris']['outbound_enrollment_ready'] = True
        state['targets']['Aurum-Morris']['status'] = 'confirmed'
        state['targets']['BBPI4']['outbound_enrollment_ready'] = True
        return state

    def seed_receipt(self, run_id=100, state='PI4_SEED_OK'):
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

    @staticmethod
    def nodes(now, *, node_id='fresh-pi4-node', arch='aarch64', last_seen=None):
        return {
            'nodes': [
                {
                    'node_id': node_id,
                    'name': 'kali-raspberrypi',
                    'os': 'Linux',
                    'arch': arch,
                    'carrier': 'https-outbound',
                    'status': 'online',
                    'last_seen': now - 5 if last_seen is None else last_seen,
                }
            ]
        }

    def test_fresh_arm64_heartbeat_confirms_seeded_bbpi4(self):
        now = 2_000_000_000
        state = self.state()
        self.seed_receipt()
        entry.apply_verified_pi4_seed(state, self.results)
        self.assertTrue(
            entry.apply_verified_pi4_identity(
                state,
                self.results,
                node_payload=self.nodes(now),
                now=now,
            )
        )
        bb = state['targets']['BBPI4']
        self.assertEqual('confirmed', bb['status'])
        self.assertEqual('fresh-pi4-node', bb['node_id'])
        self.assertEqual('fresh-arkmatx-arm64-heartbeat', bb['confirmation'])
        self.assertEqual('slush-repo-ingest', entry.core.choose_next(state))

    def test_stale_heartbeat_cannot_confirm_bbpi4(self):
        now = 2_000_000_000
        state = self.state()
        self.seed_receipt()
        entry.apply_verified_pi4_seed(state, self.results)
        payload = self.nodes(now, last_seen=now - entry.FRESH_HEARTBEAT_SECONDS - 1)
        self.assertFalse(
            entry.apply_verified_pi4_identity(
                state,
                self.results,
                node_payload=payload,
                now=now,
            )
        )
        self.assertNotEqual('confirmed', state['targets']['BBPI4']['status'])

    def test_known_windows_identity_cannot_confirm_bbpi4(self):
        now = 2_000_000_000
        state = self.state()
        self.seed_receipt()
        entry.apply_verified_pi4_seed(state, self.results)
        payload = self.nodes(now, node_id='825e5a7b7d4a7aed', arch='x86_64')
        self.assertFalse(
            entry.apply_verified_pi4_identity(
                state,
                self.results,
                node_payload=payload,
                now=now,
            )
        )
        self.assertNotEqual('confirmed', state['targets']['BBPI4']['status'])

    def test_newer_failed_seed_blocks_identity_confirmation(self):
        now = 2_000_000_000
        state = self.state()
        self.seed_receipt(run_id=100, state='PI4_SEED_OK')
        self.seed_receipt(run_id=101, state='PI4_SEED_FAILURE')
        self.assertFalse(
            entry.apply_verified_pi4_identity(
                state,
                self.results,
                node_payload=self.nodes(now),
                now=now,
            )
        )
        self.assertNotEqual('confirmed', state['targets']['BBPI4']['status'])


class Pi4IdentityEventChainTests(unittest.TestCase):
    def test_verified_seed_wakes_existing_identity_lane_and_completion_wakes_autobuild(self):
        workflow = EVENT_BRIDGE.read_text(encoding='utf-8')
        self.assertIn('- Aurum Authorized Windows AP', workflow)
        self.assertIn("github.event.workflow_run.name == 'Aurum Dual Seed Lanes'", workflow)
        self.assertIn("workflow='aurum-authorized-windows-ap.yml'", workflow)
        self.assertIn('bbpi4_identity_lane=dispatched', workflow)
        self.assertIn("workflow='aurum-autobuild.yml'", workflow)

    def test_workflow_run_gate_accepts_repo_local_non_pr_completions_without_head_repository(self):
        workflow = EVENT_BRIDGE.read_text(encoding='utf-8')
        self.assertIn('github.event.repository.full_name == github.repository', workflow)
        self.assertIn("github.event.workflow_run.event != 'pull_request'", workflow)
        self.assertNotIn('github.event.workflow_run.head_repository.full_name == github.repository', workflow)

    def test_pi4_continuation_failsafe_is_narrow_deduplicated_and_direct(self):
        workflow = PI4_CONTINUATION.read_text(encoding='utf-8')
        self.assertIn('- Aurum Dual Seed Lanes', workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", workflow)
        self.assertIn("github.event.workflow_run.event != 'pull_request'", workflow)
        self.assertIn("workflow='aurum-autobuild.yml'", workflow)
        self.assertIn('action=deduplicated', workflow)
        self.assertIn("-f ref=main", workflow)
        self.assertNotIn('head_repository.full_name', workflow)


if __name__ == '__main__':
    unittest.main()
