import unittest
import tempfile
from pathlib import Path
from aurum_farmer.ledger import Ledger
from aurum_farmer.failure_explorer import Frontier
from aurum_farmer.resource_budget import HostSampler, ResourceGovernor


class ResourceBudgetTests(unittest.TestCase):
    def test_sustained_pressure_reduces_own_budget_then_recovers_with_hysteresis(self):
        governor = ResourceGovernor()
        busy = {'available':True,'cpu_percent':90,'available_memory_mb':2100,
                'physical_load_percent':85,'commit_headroom_percent':9}
        clear = {**busy,'cpu_percent':30,'available_memory_mb':4000,
                 'physical_load_percent':65,'commit_headroom_percent':35}
        self.assertEqual(governor.choose(busy)['mode'], 'normal')
        governor.choose(busy)
        constrained = governor.choose(busy)
        self.assertEqual(constrained['mode'], 'sustained_pressure')
        self.assertEqual(constrained['cases'], 1)
        self.assertEqual(constrained['external_process_control'], 'not_configured')
        for _ in range(4):
            self.assertEqual(governor.choose(clear)['mode'], 'sustained_pressure')
        self.assertEqual(governor.choose(clear)['mode'], 'normal')

    def test_critical_or_unknown_capacity_is_conservative_but_not_fabricated(self):
        governor = ResourceGovernor()
        self.assertEqual(governor.choose({'available':False})['mode'], 'conservative_unknown')
        low = governor.choose({'available':True,'cpu_percent':10,'available_memory_mb':100,
                              'physical_load_percent':99,'commit_headroom_percent':1})
        self.assertEqual(low['mode'], 'critical_pressure')
        self.assertGreater(low['cases'], 0)
        self.assertEqual(low['cloud_routing'], 'not_configured')

    def test_host_observation_has_no_control_side_effects(self):
        sample = HostSampler().sample()
        self.assertIn('available', sample)
        if sample['available']:
            self.assertGreater(sample['available_memory_mb'], 0)
            self.assertGreaterEqual(sample['physical_load_percent'], 0)
            self.assertLessEqual(sample['physical_load_percent'], 100)

    def test_selected_budget_changes_actual_work_and_records_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = Ledger(Path(root)/'farmer.sqlite3')
            frontier = Frontier(ledger.path, ledger._signing_key)
            normal = frontier.batch()
            governor = ResourceGovernor()
            choice = governor.choose({'available':False})
            reduced = frontier.batch(cases=choice['cases'], cpu_seconds=choice['cpu_seconds'], resource_decision=choice)
            self.assertEqual(reduced['paths_checked']-normal['paths_checked'], 1)
            self.assertEqual(reduced['resource_decision']['selected'], 'reduced_local_budget')
            self.assertEqual(reduced['resource_budget']['yield_seconds'], 3)
            self.assertEqual(ledger.list_jobs(), [])
