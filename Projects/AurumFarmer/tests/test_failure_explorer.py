from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

from aurum_farmer.decision_engine import DecisionEngine
from aurum_farmer.executors import ExecutorRegistry, NoopExecutor
from aurum_farmer.failure_explorer import Frontier, ExplorerWatchdog, control, domains, index_at, model_case, read_status
from aurum_farmer.failure_oracle import verify_model
from aurum_farmer.ledger import Ledger
from aurum_farmer.models import BranchSpec, JobSpec, EvidenceRequirement
from aurum_farmer.supervisor import Supervisor


class FailureExplorerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = Ledger(Path(self.temp.name)/'farmer.sqlite3')

    def test_idle_frontier_advances_and_restart_resumes_without_real_jobs(self):
        first = Frontier(self.ledger.path, self.ledger._signing_key, owner='same-lease')
        first.batch()
        prior = first.batch()
        resumed = Frontier(self.ledger.path, self.ledger._signing_key, owner='same-lease').batch()
        self.assertGreater(resumed['paths_checked'], prior['paths_checked'])
        self.assertGreater(resumed['pending_cursor_positions'], 1000000)
        self.assertEqual(resumed['invariant_violations'], 0)
        self.assertEqual(self.ledger.list_jobs(), [])
        self.assertEqual(self.ledger.future_status()['decisions'], 0)
        self.assertTrue(self.ledger.verify_event_chain())

    def test_permutation_tests_each_semantic_case_once(self):
        indices = [index_at(i, [2,3,4])[0] for i in range(index_at(0,[2,3,4])[1])]
        actual = [i for i in indices if i is not None]
        self.assertEqual(len(actual), 24)
        self.assertEqual(set(actual), set(range(24)))
        self.assertIsNone(index_at(1000,[2,3,4])[0])

    def test_fault_oracle_catches_unsafe_engine_and_errors_are_not_replayed(self):
        frontier = Frontier(self.ledger.path, self.ledger._signing_key)
        real = frontier.engine
        class UnsafeEngine:
            implementation = real.implementation
            def evaluate(self, snapshot, proposals):
                report = real.evaluate(snapshot, proposals)
                report['selected'] = proposals[0]['logical_id']
                report['branches'][0]['automatic'] = True
                return report
        frontier.engine = UnsafeEngine()
        result = frontier.batch()
        self.assertGreater(result['invariant_violations'], 0)
        with closing(frontier.connect()) as db:
            before = {r[0] for r in db.execute('SELECT id FROM findings')}
        frontier.batch()
        with closing(frontier.connect()) as db:
            after = [r[0] for r in db.execute('SELECT id FROM findings')]
        self.assertTrue(before <= set(after))
        self.assertEqual(len(after), len(set(after)))

    def test_all_single_faults_and_interactions_obey_independent_oracle(self):
        base = control()
        sizes = [len(v) for v in domains(base).values()]
        engine = DecisionEngine()
        for cursor in range(400):
            index, _ = index_at(cursor, sizes)
            if index is None:
                continue
            snapshot, candidate, _ = model_case(base, index)
            report = engine.evaluate(snapshot, [candidate])
            self.assertEqual(verify_model(snapshot, candidate, report), [], (cursor,index))

    def test_capture_collapses_job_ids_and_secrets_are_not_persisted(self):
        frontier = Frontier(self.ledger.path, self.ledger._signing_key)
        for marker in ('private-one', 'private-two'):
            self.ledger.submit(JobSpec(goal='private-goal', branches=(BranchSpec(id=marker,label=marker,
                executor='noop',payload={'secret':marker},expected_evidence=(EvidenceRequirement('noop_verified'),)),)))
        frontier.batch()
        with closing(frontier.connect()) as db:
            bodies = [r[0] for r in db.execute('SELECT body FROM frontier')]
        text = ''.join(bodies)
        self.assertNotIn('private-', text)
        self.assertLessEqual(len(bodies), 2)  # Control and one shared observed policy shape.

    def test_checkpoint_tampering_and_unhealthy_worker_hold_execution(self):
        frontier = Frontier(self.ledger.path, self.ledger._signing_key)
        frontier.batch()
        with closing(frontier.connect()) as db, db:
            db.execute("UPDATE runtime SET signature='forged'")
        self.assertFalse(read_status(self.ledger.path, self.ledger._signing_key)['healthy'])
        with closing(frontier.connect()) as db, db:
            db.execute("UPDATE frontier SET signature='forged'")
        with self.assertRaises(ValueError):
            frontier.batch()
        self.ledger.submit(JobSpec(goal='hold',branches=(BranchSpec(id='a',label='a',executor='noop',
                           expected_evidence=(EvidenceRequirement('noop_verified'),)),)))
        supervisor = Supervisor(self.ledger, ExecutorRegistry())
        class Unhealthy:
            def status(self): return {'healthy':False}
        supervisor.failure_explorer = Unhealthy()
        self.assertEqual(supervisor.tick()['status'], 'exploration_hold')
        self.assertEqual(self.ledger.stats()['running_attempts'], 0)

    def test_resident_worker_recovers_from_process_death_and_stops_with_owner(self):
        watcher = ExplorerWatchdog(self.ledger)
        watcher.start()
        self.addCleanup(watcher.stop)
        deadline = time.monotonic()+15
        while time.monotonic()<deadline and not watcher.status()['healthy']:
            time.sleep(.1)
        before = watcher.status()
        self.assertTrue(before['healthy'])
        self.assertGreater(before['paths_checked'], 0)
        old_pid = watcher.process.pid
        watcher.process.kill()
        watcher.process.wait(3)
        deadline = time.monotonic()+17
        while time.monotonic()<deadline:
            after = watcher.status()
            if after['healthy'] and watcher.process.pid != old_pid and after['paths_checked'] > before['paths_checked']:
                break
            time.sleep(.1)
        self.assertTrue(after['healthy'])
        self.assertGreater(after['paths_checked'], before['paths_checked'])
        self.assertGreaterEqual(after['worker_restarts'], 1)
        watcher.stop()
        self.assertIsNotNone(watcher.process.poll())

    def test_exploration_runs_concurrently_with_execution(self):
        registry = ExecutorRegistry()
        entered, release = threading.Event(), threading.Event()
        class BlockingNoop:
            def execute(self, context):
                entered.set()
                release.wait(10)
                return NoopExecutor().execute(context)
        registry.register('noop', BlockingNoop())
        self.ledger.submit(JobSpec(goal='parallel',branches=(BranchSpec(id='a',label='a',executor='noop',
                           expected_evidence=(EvidenceRequirement('noop_verified'),)),)))
        supervisor = Supervisor(self.ledger, registry, poll_seconds=.1)
        thread = threading.Thread(target=supervisor.run_forever)
        thread.start()
        try:
            self.assertTrue(entered.wait(10))
            before = supervisor.failure_explorer.status()['paths_checked']
            deadline = time.monotonic()+4
            while time.monotonic()<deadline and supervisor.failure_explorer.status()['paths_checked'] <= before:
                time.sleep(.1)
            self.assertGreater(supervisor.failure_explorer.status()['paths_checked'], before)
        finally:
            release.set()
            supervisor.stop()
            thread.join(10)
        self.assertFalse(thread.is_alive())
