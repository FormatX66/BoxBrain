import json
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
SOURCE = REPO / 'Web' / 'Aurum-Arkmatx' / 'index.php'


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def frame(intent, node_id):
    now = int(time.time())
    delta = {'node_id': node_id, 'carrier': 'https-outbound'}
    if intent == 'node_enroll':
        delta.update({'name': 'test-node', 'os': 'test-os', 'arch': 'test-arch'})
    return {
        'schema': 'aurum.uaf.v0',
        'frame_id': f'{intent}-{node_id}-{now}',
        'origin': f'Aurum-Node-{node_id}',
        'target': 'Aurum-Arkmatx',
        'intent': intent,
        'state_delta': delta,
        'provenance': {'node': f'Aurum-Node-{node_id}', 'created': now},
        'verification': {'content_addressed': True, 'reversible': True},
    }


class ArkmatxNodeHeartbeatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which('php') is None:
            raise unittest.SkipTest('php is unavailable')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copy2(SOURCE, self.root / 'index.php')
        self.port = free_port()
        self.proc = subprocess.Popen(
            ['php', '-S', f'127.0.0.1:{self.port}', '-t', str(self.root)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.url = f'http://127.0.0.1:{self.port}/index.php'
        for _ in range(30):
            try:
                with urllib.request.urlopen(self.url, timeout=1) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(0.05)
        else:
            self.fail('local Aurum controller did not start')

    def tearDown(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.temp.cleanup()

    def post(self, payload):
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload, separators=(',', ':')).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.load(response)

    def test_heartbeat_requires_enrollment_then_updates_node(self):
        node_id = 'test-bbpi4'
        with self.assertRaises(urllib.error.HTTPError) as rejected:
            self.post(frame('node_heartbeat', node_id))
        self.assertEqual(rejected.exception.code, 409)

        status, enrolled = self.post(frame('node_enroll', node_id))
        self.assertEqual(status, 202)
        self.assertEqual(enrolled['receipt']['state_delta']['intent'], 'node_enroll')

        node_path = self.root / 'state' / 'nodes' / f'{node_id}.json'
        first = json.loads(node_path.read_text())
        self.assertEqual(first['status'], 'online')
        self.assertEqual(first['carrier'], 'https-outbound')
        first_seen = first['first_seen']

        time.sleep(1)
        status, beat = self.post(frame('node_heartbeat', node_id))
        self.assertEqual(status, 202)
        self.assertEqual(beat['receipt']['state_delta']['intent'], 'node_heartbeat')

        updated = json.loads(node_path.read_text())
        self.assertEqual(updated['first_seen'], first_seen)
        self.assertGreaterEqual(updated['last_seen'], first['last_seen'])
        self.assertEqual(updated['status'], 'online')

        with urllib.request.urlopen(self.url, timeout=3) as response:
            controller = json.load(response)
        self.assertIn('node_heartbeat', controller['capabilities'])
        self.assertEqual(controller['events']['nodes'], 1)


if __name__ == '__main__':
    unittest.main()
