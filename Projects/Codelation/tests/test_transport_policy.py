import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'aurum_runtime'))
from transport_policy import Transport, choose_transport, bbpi4_candidates

class TransportPolicyTests(unittest.TestCase):
    def test_prefers_available_authenticated_low_risk(self):
        items = [
            Transport('lan','x','ssh',True,True,2,0,2),
            Transport('usb','y','ssh',True,True,1,0,0),
        ]
        self.assertEqual(choose_transport(items).name, 'usb')

    def test_rejects_unauthenticated(self):
        items = [Transport('web','x','http',True,False,0,0,0)]
        self.assertIsNone(choose_transport(items))

    def test_rejects_unavailable(self):
        items = [Transport('usb','x','ssh',False,True,0,0,0)]
        self.assertIsNone(choose_transport(items))

    def test_candidates_include_direct_usb(self):
        names = {item.name for item in bbpi4_candidates()}
        self.assertIn('usb-c-ssh', names)
        self.assertIn('usb-ap-ssh', names)
        self.assertIn('lan-ssh', names)

if __name__ == '__main__':
    unittest.main()
