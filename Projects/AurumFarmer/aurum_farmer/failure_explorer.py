"""Resident, checkpointed fault-model exploration; no executor or probe access."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

from .decision_engine import Budget, DecisionEngine, digest
from .failure_oracle import verify_model
from .resource_budget import HostSampler, ResourceGovernor
from .activity_reader import ActivityReader

SCHEMA = 'aurum.future-branch.continuous.v1'
CATALOG = 'decision-safety-fault-model.v1'
SCOPE = 'Decision-policy fault models; not physical, VM, or all-chat execution proof'


def database(ledger_path):
    return Path(ledger_path).with_suffix('.exploration.sqlite3')


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def seal(key, value):
    return hmac.new(key, encode(value).encode(), hashlib.sha256).hexdigest()


def domains(base):
    """Boundary values and interacting failure conditions, not random busywork."""
    axes = {
        'authority_ready': [True, False], 'dependencies_satisfied': [True, False],
        'human_boundary': [None, {'kind': 'review_required'}],
        'state': ['CANDIDATE', 'SUCCEEDED', 'QUARANTINED'],
        'risk': [0, .35, .350001, 1], 'reversibility': [1, .9, .899999, 0],
        'expected_evidence': [[{'kind': 'model_evidence'}], []],
        'required_tier': ['static', 'unit', 'vm', 'hardware_model', 'canary', 'unknown'],
        'effect': ['read_only', 'state_change'], 'rollback_ref': [None, 'model-only-rollback'],
        'lkg_present': [False, True], 'impossible': [False, True], 'expires_at': [None, 1],
        'attempt_count': [0, base['max_attempts']], 'irreversible_cost': [0, .1],
        'confidence': [1, 0], 'uncertainty': [0, .5], 'parents': [[], ['unavailable-parent']],
    }
    for name, values in axes.items():
        unique = [base.get(name, values[0])]
        for value in values:
            if value not in unique:
                unique.append(value)
        axes[name] = unique
    return axes


def index_at(cursor, sizes):
    # Test the observed baseline and every single-factor boundary first, then a
    # coprime permutation spreads interaction tests throughout the finite space.
    prefix = [0]
    stride = 1
    for size in sizes:
        prefix.extend(stride * value for value in range(1, size))
        stride *= size
    total = stride
    if cursor < len(prefix):
        return prefix[cursor], total + len(prefix)
    if cursor >= total + len(prefix):
        return None, total + len(prefix)
    multiplier = 104729
    while math.gcd(multiplier, total) != 1:
        multiplier += 2
    index = ((cursor - len(prefix)) * multiplier) % total
    return (None if index in prefix else index), total + len(prefix)


def model_case(base, index):
    candidate = json.loads(encode(base))
    changes = []
    for name, values in domains(base).items():
        value = index % len(values)
        index //= len(values)
        candidate[name] = values[value]
        if value:
            changes.append(name)
    has_lkg = candidate.pop('lkg_present')
    snapshot = {'lkg': {'model-scope': {'artifact_ref': 'protected-model-lkg'}} if has_lkg else {}}
    return snapshot, candidate, changes


def control():
    return {'logical_id': 'model-action', 'executor': 'model-only', 'payload': {},
            'expected_evidence': [{'kind': 'model_evidence'}], 'authority_ready': True,
            'dependencies_satisfied': True, 'human_boundary': None, 'state': 'CANDIDATE',
            'risk': 0, 'reversibility': 1, 'required_tier': 'static', 'effect': 'read_only',
            'rollback_ref': None, 'lkg_present': False, 'lkg_scope': 'model-scope',
            'impossible': False, 'expires_at': None, 'attempt_count': 0, 'max_attempts': 1,
            'irreversible_cost': 0, 'confidence': 1, 'impact': 1, 'uncertainty': 0, 'parents': []}


class Frontier:
    def __init__(self, ledger_path, key, *, owner=None, engine=None, oracle=verify_model):
        self.ledger_path = Path(ledger_path)
        self.path = database(ledger_path)
        self.key, self.owner = key, owner or uuid.uuid4().hex
        # Never load runtime probe commands or executors into fault simulations.
        self.engine = engine or DecisionEngine(budget=Budget(nodes=32, workers=1, probe_units=0))
        self.oracle = oracle
        self.revision = digest({'catalog': CATALOG, 'engine': self.engine.implementation,
            'source': [hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       hashlib.sha256(Path(__file__).with_name('failure_oracle.py').read_bytes()).hexdigest()]})
        self.last_capture = 0.0
        with closing(self.connect()) as db, db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS frontier (
                    id TEXT PRIMARY KEY, body TEXT NOT NULL, signature TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runtime (
                    id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL, signature TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS lease (
                    id INTEGER PRIMARY KEY CHECK(id=1), owner TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS findings (
                    id TEXT PRIMARY KEY, body TEXT NOT NULL, signature TEXT NOT NULL);
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def unpack(self, row):
        body = json.loads(row['body'])
        if not hmac.compare_digest(row['signature'], seal(self.key, body)):
            raise ValueError('exploration checkpoint integrity failure')
        return body

    def capture(self):
        bases = [control()]
        # Observe at most 64 recent action shapes. Hash inputs; never copy goals,
        # credentials, raw payloads, arbitrary commands, or chat transcripts.
        with closing(sqlite3.connect(self.ledger_path.as_uri() + '?mode=ro', uri=True, timeout=3)) as source:
            source.row_factory = sqlite3.Row
            rows = source.execute('SELECT * FROM branches ORDER BY created_at DESC LIMIT 64').fetchall()
        for row in rows:
            raw = dict(row)
            decision = json.loads(raw.get('decision_json') or '{}')
            base = control()
            for name in ('risk', 'reversibility', 'confidence', 'impact', 'authority_ready', 'dependencies_satisfied', 'max_attempts'):
                base[name] = raw[name]
            for name in ('required_tier', 'effect', 'irreversible_cost', 'uncertainty'):
                if name in decision:
                    base[name] = decision[name]
            # IDs and payload values do not change this one-action policy model.
            # Collapsing equivalent shapes avoids counting renamed jobs as novel
            # failure-path evidence. No payload contents are persisted here.
            base['expected_evidence'] = [{'kind': 'model_evidence'}] if json.loads(raw['expected_evidence_json']) else []
            # This is a hypothetical next operation of the observed shape. Its
            # candidate state is not written back or permission to retry anything.
            bases.append(base)
        with closing(self.connect()) as db, db:
            for base in bases:
                state_id = digest({'revision': self.revision, 'base': base})
                item = {'state_id': state_id, 'revision': self.revision, 'base': base,
                        'cursor': 0, 'checked': 0, 'prevented': 0, 'violations': 0, 'errors': 0,
                        'total': index_at(0, [len(v) for v in domains(base).values()])[1],
                        'last_checked': 0, 'last_scheduled': 0, 'recent': [], 'complete': False}
                db.execute('INSERT OR IGNORE INTO frontier VALUES(?,?,?)', (state_id, encode(item), seal(self.key, item)))
        self.last_capture = time.monotonic()

    def batch(self, *, cases=16, cpu_seconds=.15, resource_decision=None):
        if not 1 <= cases <= 256 or not .001 <= cpu_seconds <= .5:
            raise ValueError('invalid exploration resource budget')
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM lease WHERE id=1').fetchone()
            if row and row['owner'] != self.owner and row['expires'] > time.time():
                return {'mode': 'standby'}
            db.execute('INSERT OR REPLACE INTO lease VALUES(1,?,?)', (self.owner, time.time()+10))
        if time.monotonic() - self.last_capture > 10:
            self.capture()
        with closing(self.connect()) as db:
            items = [self.unpack(r) for r in db.execute('SELECT * FROM frontier')]
        current = [item for item in items if item['revision'] == self.revision and not item['complete']]
        current.sort(key=lambda item: (item['last_scheduled'], item['state_id']))
        start = time.process_time()
        checked = 0
        for item in current:
            if checked >= cases or time.process_time()-start >= cpu_seconds:
                break
            item['last_scheduled'] = time.time()
            # Fair slices let new observations enter without starving old paths.
            for _ in range(min(4, cases-checked)):
                index, end = index_at(item['cursor'], [len(v) for v in domains(item['base']).values()])
                item['cursor'] += 1
                if item['cursor'] >= end:
                    item['complete'] = True
                if index is None:
                    break
                snapshot, candidate, changes = model_case(item['base'], index)
                violations, error, report = [], None, None
                try:
                    report = self.engine.evaluate(snapshot, [candidate])
                    violations = self.oracle(snapshot, candidate, report)
                except Exception as exc:
                    error = type(exc).__name__
                outcome = 'model_error' if error else 'invariant_violation' if violations else 'guard_prevented' if not report['selected'] else 'safe_path'
                receipt = {'case_id': digest([item['state_id'], index]), 'state_id': item['state_id'],
                    'index': index, 'changed_dimensions': changes, 'outcome': outcome,
                    'findings': violations, 'error': error, 'report_digest': digest(report),
                    'dag_nodes': len(report['nodes']) if report else 0, 'observed_at': time.time(),
                    'model_only': True, 'authority_granted': False, 'oracle': 'independent-failure-oracle-v1'}
                item['checked'] += 1
                item['prevented'] += int(outcome == 'guard_prevented')
                item['violations'] += int(bool(violations))
                item['errors'] += int(bool(error))
                item['last_checked'] = receipt['observed_at']
                item['recent'] = ([receipt] + item['recent'])[:5]
                checked += 1
                with closing(self.connect()) as db, db:
                    db.execute('BEGIN IMMEDIATE')
                    lease = db.execute('SELECT owner FROM lease WHERE id=1').fetchone()
                    if lease['owner'] != self.owner:
                        return {'mode': 'standby'}
                    if violations or error:
                        db.execute('INSERT OR IGNORE INTO findings VALUES(?,?,?)',
                                   (receipt['case_id'], encode(receipt), seal(self.key, receipt)))
                    db.execute('UPDATE frontier SET body=?,signature=? WHERE id=?',
                               (encode(item), seal(self.key, item), item['state_id']))
                if time.process_time()-start >= cpu_seconds or item['complete']:
                    break
            # Persist completion even when the last index was a prefix duplicate.
            with closing(self.connect()) as db, db:
                db.execute('BEGIN IMMEDIATE')
                lease = db.execute('SELECT owner FROM lease WHERE id=1').fetchone()
                if lease['owner'] != self.owner:
                    return {'mode': 'standby'}
                db.execute('UPDATE frontier SET body=?,signature=? WHERE id=?', (encode(item), seal(self.key, item), item['state_id']))
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            lease = db.execute('SELECT owner FROM lease WHERE id=1').fetchone()
            if lease['owner'] != self.owner:
                return {'mode': 'standby'}
            states = [self.unpack(r) for r in db.execute('SELECT * FROM frontier')]
            active = [item for item in states if item['revision'] == self.revision]
            pending = sum(max(0, item['total']-item['cursor']) for item in active)
            status = {'schema': SCHEMA, 'mode': 'exploring' if pending else 'watching_for_new_state',
                'owner': self.owner, 'pid': os.getpid(), 'updated_at': time.time(), 'revision': self.revision,
                'paths_checked': sum(item['checked'] for item in active),
                'guarded_paths': sum(item['prevented'] for item in active),
                'invariant_violations': sum(item['violations'] for item in active),
                'model_errors': sum(item['errors'] for item in active), 'pending_cursor_positions': pending,
                'observed_shapes': len(active), 'last_new_evidence_at': max((item['last_checked'] for item in active), default=0),
                'recent': sorted([r for item in active for r in item['recent']], key=lambda r: -r['observed_at'])[:8],
                'scope': SCOPE, 'model_only': True, 'authority_granted': False,
                'resource_budget': {'cases_per_batch': cases, 'cpu_seconds_per_batch': cpu_seconds,
                                    'yield_seconds': (resource_decision or {}).get('yield_seconds', 1)},
                'resource_decision': resource_decision}
            db.execute('INSERT OR REPLACE INTO runtime VALUES(1,?,?)', (encode(status), seal(self.key, status)))
            db.execute('UPDATE lease SET expires=? WHERE id=1 AND owner=?', (time.time()+10, self.owner))
        return status


def read_status(ledger_path, key):
    path = database(ledger_path)
    if not path.exists():
        return {'schema': SCHEMA, 'mode': 'not_started', 'healthy': False}
    try:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=1)) as db:
            row = db.execute('SELECT body,signature FROM runtime WHERE id=1').fetchone()
        if row is None:
            return {'schema': SCHEMA, 'mode': 'starting', 'healthy': False}
        body = json.loads(row[0])
        if not hmac.compare_digest(row[1], seal(key, body)):
            raise ValueError('invalid seal')
        age = max(0, time.time()-body['updated_at'])
        return {**body, 'age_seconds': age, 'healthy': age < 10, 'seal_valid': True}
    except (ValueError, sqlite3.Error):
        return {'schema': SCHEMA, 'mode': 'checkpoint_unavailable', 'healthy': False, 'seal_valid': False}


class ExplorerWatchdog:
    """Own a replaceable worker process so a crash/hang cannot silently disable exploration."""
    def __init__(self, ledger):
        self.ledger, self.process = ledger, None
        self.stop_event = threading.Event()
        self.thread = None
        self.started_at = 0
        self.restarts = 0
        self.owner = None
        self.error = None
        self.blocked_checkpoint = None

    def status(self):
        state = read_status(self.ledger.path, self.ledger._signing_key)
        alive = self.process is not None and self.process.poll() is None
        watched = bool(self.thread and self.thread.is_alive())
        return {**state, 'healthy': state['healthy'] and alive and watched,
                'worker_alive': alive, 'watchdog_alive': watched,
                'local_worker_leader': state.get('owner') == self.owner,
                'worker_restarts': self.restarts, 'watchdog_error': self.error}

    def start(self):
        self.thread = threading.Thread(target=self._watch, name='future-branch-watchdog', daemon=True)
        self.thread.start()

    def _watch(self):
        try:
            while not self.stop_event.is_set():
                try:
                    state = self.status()
                    if self.process is not None and self.process.poll() == 78:
                        checkpoint = database(self.ledger.path)
                        fingerprint = digest([hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
                                              for p in (checkpoint, Path(str(checkpoint)+'-wal'))])
                        if self.blocked_checkpoint is None:
                            self.blocked_checkpoint = fingerprint
                        if fingerprint == self.blocked_checkpoint:
                            self.error = 'checkpoint_integrity_failure'
                            self.stop_event.wait(1)
                            continue  # Never replay a known corrupt checkpoint unchanged.
                        self.blocked_checkpoint = None
                    if self.process is None or self.process.poll() is not None or (
                            time.monotonic()-self.started_at > 20 and state.get('age_seconds', 999) > 10):
                        if self.process is not None:
                            if self.process.poll() is None:
                                self.process.kill()
                            self.process.wait(timeout=5)
                            self.process.stdin.close()
                            self.restarts += 1
                        self.owner = uuid.uuid4().hex
                        self.process = subprocess.Popen([sys.executable, '-m', 'aurum_farmer.failure_explorer',
                            '--ledger', str(self.ledger.path), '--key', str(self.ledger.signing_key_path), '--owner', self.owner],
                            cwd=str(Path(__file__).parents[1]), stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                        self.started_at = time.monotonic()
                    self.error = None
                except Exception as exc:
                    self.error = type(exc).__name__
                self.stop_event.wait(1)
        finally:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                self.process.wait(timeout=5)
            if self.process and self.process.stdin:
                self.process.stdin.close()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=6)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', required=True, type=Path)
    parser.add_argument('--key', required=True, type=Path)
    parser.add_argument('--owner', required=True)
    args = parser.parse_args()
    frontier = Frontier(args.ledger, args.key.read_bytes(), owner=args.owner)
    stop = threading.Event()

    def parent_lifetime():
        # The parent exclusively holds the write end. EOF stops an orphan worker
        # after an abrupt supervisor exit without PID-reuse assumptions.
        sys.stdin.buffer.read()
        stop.set()

    threading.Thread(target=parent_lifetime, daemon=True).start()
    sampler, governor, activity = HostSampler(), ResourceGovernor(), ActivityReader()
    while not stop.is_set():
        resources = governor.choose(sampler.sample(), activity.sample())
        try:
            frontier.batch(cases=resources['cases'], cpu_seconds=resources['cpu_seconds'], resource_decision=resources)
        except ValueError:
            raise SystemExit(78)
        stop.wait(resources['yield_seconds'])


if __name__ == '__main__':
    main()
