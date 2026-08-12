import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from slush_work_queue import SlushWorkQueue,NodeCapability

class Clock:
    def __init__(self): self.t=1000
    def __call__(self): return self.t

class Tests(unittest.TestCase):
    def setUp(self): self.clock=Clock();self.q=SlushWorkQueue(now=self.clock)
    def test_capability_match(self):
        self.q.submit('python-test',{'x':1})
        self.assertIsNone(self.q.lease(NodeCapability('n',frozenset({'php'}))))
        self.assertEqual(self.q.lease(NodeCapability('n',frozenset({'python-test'})))['capability'],'python-test')
    def test_verified_completion(self):
        self.q.submit('python-test',{'x':1});w=self.q.lease(NodeCapability('n',frozenset({'python-test'})))
        done=self.q.complete(w['work_id'],'n',w['lease']['token'],{'ok':1},verified=True)
        self.assertEqual(done['status'],'complete');self.assertTrue(done['result']['verified'])
    def test_wrong_node_rejected(self):
        self.q.submit('x',{});w=self.q.lease(NodeCapability('n',frozenset({'x'})))
        with self.assertRaises(PermissionError): self.q.complete(w['work_id'],'other',w['lease']['token'],{},verified=True)
    def test_expired_lease_requeues(self):
        self.q.submit('x',{});self.q.lease(NodeCapability('a',frozenset({'x'})),ttl=5);self.clock.t+=6
        w=self.q.lease(NodeCapability('b',frozenset({'x'})))
        self.assertEqual(w['lease']['node_id'],'b')
    def test_nonreversible_rejected(self):
        with self.assertRaises(ValueError): self.q.submit('x',{},reversible=False)

if __name__=='__main__': unittest.main()
