"""Bounded read-only observations. No process controls, command lines or tokens."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

SCHEMA = 'aurum.workload-activity.v1'
REPO = 'FormatX66/BoxBrain'
ENVIRONMENT = 'https://chatgpt.com/codex/cloud/settings/environment/6a9a39b127a08191805cf70927ce8629'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def timestamp(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except (TypeError, ValueError, AttributeError):
        return None


def windows_processes():
    """Enumerate with query/read-only rights; inaccessible metrics remain absent."""
    import ctypes as c
    from ctypes import wintypes as w
    kernel, psapi = c.WinDLL('kernel32', use_last_error=True), c.WinDLL('psapi', use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.GetProcessTimes.argtypes = [w.HANDLE] + [c.POINTER(w.FILETIME)] * 4
    kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)]
    class Memory(c.Structure):
        _fields_ = [('cb', w.DWORD), ('faults', w.DWORD)] + [(key, c.c_size_t) for key in
            ('peak_ws', 'ws', 'peak_pool', 'pool', 'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile')]
    psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, c.POINTER(Memory), w.DWORD]
    ids, needed = (w.DWORD * 16384)(), w.DWORD()
    if not psapi.EnumProcesses(ids, c.sizeof(ids), c.byref(needed)) or needed.value >= c.sizeof(ids):
        raise OSError('process enumeration incomplete')
    ticks = lambda t: t.dwLowDateTime + (t.dwHighDateTime << 32)
    rows = []
    for pid in ids[:needed.value // c.sizeof(w.DWORD)]:
        if not pid:  # idle thread is not a workload
            continue
        handle = kernel.OpenProcess(0x1000 | 0x0010, False, pid)
        if not handle:
            handle = kernel.OpenProcess(0x1000, False, pid)
        row = {'pid': pid, 'name': 'PID ' + str(pid), 'created': None, 'cpu_seconds': None, 'memory_mb': None}
        if handle:
            try:
                name, size = c.create_unicode_buffer(32768), w.DWORD(32768)
                if kernel.QueryFullProcessImageNameW(handle, 0, name, c.byref(size)):
                    row['name'] = name.value.replace('\\', '/').rsplit('/', 1)[-1]
                created, exited, system, user = (w.FILETIME() for _ in range(4))
                if kernel.GetProcessTimes(handle, c.byref(created), c.byref(exited), c.byref(system), c.byref(user)):
                    row.update(created=ticks(created) / 1e7 - 11644473600,
                               cpu_seconds=(ticks(system) + ticks(user)) / 1e7)
                mem = Memory()
                mem.cb = c.sizeof(mem)
                if psapi.GetProcessMemoryInfo(handle, c.byref(mem), mem.cb):
                    row['memory_mb'] = round(mem.ws / 1024**2, 1)
            finally:
                kernel.CloseHandle(handle)
        rows.append(row)
    return rows


def linux_processes():
    rows = []
    ticks = os.sysconf('SC_CLK_TCK')
    boot = float(next(line.split()[1] for line in Path('/proc/stat').read_text().splitlines() if line.startswith('btime ')))
    for folder in Path('/proc').iterdir():
        if not folder.name.isdigit():
            continue
        try:
            raw = (folder / 'stat').read_text()
            end = raw.rfind(')')
            fields = raw[end+2:].split()
            rows.append({'pid': int(folder.name), 'name': raw[raw.find('(')+1:end][:120],
                         'created': boot + int(fields[19]) / ticks,
                         'cpu_seconds': (int(fields[11]) + int(fields[12])) / ticks,
                         'memory_mb': round(int(fields[21]) * os.sysconf('SC_PAGE_SIZE') / 1024**2, 1)})
        except (OSError, ValueError, IndexError):
            continue  # process ended during enumeration
    return rows


class LocalCollector:
    interval = 3
    def __init__(self, enumerate_processes=None, cpu_count=None):
        self.enumerate = enumerate_processes or (windows_processes if os.name == 'nt' else linux_processes)
        self.cpu_count = cpu_count or os.cpu_count() or 1
        self.previous = {}
        self.last_mono = None
        self.ended = {}

    def collect(self, now=None, mono=None):
        now = time.time() if now is None else now
        mono = time.monotonic() if mono is None else mono
        rows, current = [], {}
        elapsed = mono - self.last_mono if self.last_mono is not None else 0
        for raw in self.enumerate():
            # Unknown start time cannot establish PID continuity; never compute its delta.
            key = f"local:{raw['pid']}:{raw['created']}"
            old = self.previous.get(key)
            cpu = None
            if old and raw['created'] is not None and elapsed > 0 and raw['cpu_seconds'] is not None and old[0] is not None:
                cpu = round(max(0, min(100, (raw['cpu_seconds'] - old[0]) / elapsed / self.cpu_count * 100)), 2)
            row = {'id': key, 'kind': 'process', 'provider': 'local', 'name': raw['name'], 'pid': raw['pid'],
                   'owner': 'Future Branch monitor' if raw['pid'] == os.getpid() else 'Unknown',
                   'location': 'This computer', 'state': 'running', 'cpu_percent': cpu,
                   'cpu_denominator': f'This host, {self.cpu_count} logical CPUs', 'memory_mb': raw['memory_mb'],
                   'memory_scope': 'Working set / RSS; shared pages may overlap', 'started_at': raw['created'],
                   'completed_at': None, 'step': None, 'observed_at': now, 'url': None,
                   'controls': [], 'control_note': 'Observation only; no process control authority'}
            current[key] = (raw['cpu_seconds'], row)
            rows.append(row)
        for key, (_, row) in self.previous.items():
            if key not in current:
                self.ended[key] = {**row, 'state': 'ended', 'completed_at': now, 'observed_at': now,
                                   'cpu_percent': None, 'memory_mb': None}
        self.ended = {key: row for key, row in self.ended.items() if now-row['completed_at'] < 30 and key not in current}
        self.previous, self.last_mono = current, mono
        return {'rows': rows + list(self.ended.values()), 'logical_cpus': self.cpu_count,
                'scope': 'Local OS process inventory; guest VM internals and ownership are not inferred',
                'status': 'ok' if rows else 'empty'}


class ProviderError(Exception):
    def __init__(self, kind, code=None, retry_after=60):
        self.kind, self.code, self.retry_after = kind, code, retry_after
        super().__init__(kind)


class GitHubAPI:
    """Use the user's existing gh authentication, without reading or emitting tokens."""
    def __init__(self):
        self.executable = shutil.which('gh')
        self.requests = 0

    def get(self, path):
        if not self.executable:
            raise ProviderError('cli_unavailable', retry_after=300)
        if not path.startswith(f'repos/{REPO}/actions/'):
            raise ValueError('unapproved API path')
        self.requests += 1
        try:
            result = subprocess.run([self.executable, 'api', '--hostname', 'github.com', '--method', 'GET', '--include',
                '-H', 'Accept: application/vnd.github+json', '-H', 'X-GitHub-Api-Version: 2026-03-10', path],
                capture_output=True, timeout=12, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired:
            raise ProviderError('timeout', retry_after=60) from None
        if len(result.stdout) > 2_000_000:
            raise ProviderError('response_too_large', retry_after=300)
        raw = result.stdout.decode('utf-8', errors='replace').replace('\r\n', '\n')
        header, separator, body = raw.partition('\n\n')
        match = re.match(r'HTTP/\S+ (\d+)', header)
        code = int(match.group(1)) if match else None
        headers = {line.split(':', 1)[0].lower(): line.split(':', 1)[1].strip()
                   for line in header.splitlines()[1:] if ':' in line}
        if result.returncode or code != 200:
            retry = 60
            try:
                retry = max(retry, float(headers.get('retry-after', 0)))
                if headers.get('x-ratelimit-remaining') == '0':
                    retry = max(retry, float(headers.get('x-ratelimit-reset', 0)) - time.time() + 1)
            except ValueError:
                pass
            kind = 'rate_limited' if code == 429 or (code == 403 and ('retry-after' in headers or headers.get('x-ratelimit-remaining') == '0')) else (
                'access_denied' if code in (401, 403, 404) else 'disconnected' if code is None else 'provider_error')
            raise ProviderError(kind, code, min(86400, retry))
        try:
            value = json.loads(body)
            if not isinstance(value, dict):
                raise ValueError('object required')
            return value
        except ValueError:
            raise ProviderError('invalid_response', code, 300) from None


def github_row(job, run, now):
    is_job = job is not run
    state = job.get('conclusion') if job.get('status') == 'completed' else job.get('status')
    steps = job.get('steps', [])
    step = next((s.get('name') for s in steps if s.get('status') == 'in_progress'), None)
    if step is None and steps:
        step = next((s.get('name') for s in reversed(steps) if s.get('status') == 'completed'), None)
    labels = job.get('labels', [])
    location = 'GitHub · self-hosted runner' if 'self-hosted' in labels else (
        'GitHub cloud' if any(str(label).startswith(('ubuntu-', 'windows-', 'macos-')) for label in labels) else 'GitHub · runner unconfirmed')
    row_id = f"github:{REPO}:{run['id']}:{run.get('run_attempt', 1)}:{'job' if is_job else 'run'}:{job['id']}"
    # Build links from validated numeric IDs, never provider-supplied URL schemes.
    run_url = f"https://github.com/{REPO}/actions/runs/{int(run['id'])}"
    return {'id': row_id, 'provider': 'github', 'run_id': int(run['id']), 'kind': 'job' if is_job else 'run',
            'name': str(job.get('name') or 'Workflow')[:200], 'owner': REPO,
            'location': location, 'state': state or 'unknown', 'runner': str(job.get('runner_name') or 'Unassigned')[:120],
            'cpu_percent': None, 'memory_mb': None, 'cpu_denominator': 'Remote host metrics unavailable',
            'memory_scope': 'Remote RAM unavailable; never part of local RAM',
            'started_at': timestamp(job.get('started_at') or run.get('run_started_at')),
            'completed_at': timestamp(job.get('completed_at')) if is_job else timestamp(run.get('updated_at')) if job.get('status') == 'completed' else None,
            'step': step, 'observed_at': now, 'head_sha': str(run.get('head_sha', ''))[:40],
            'url': run_url + (f"/job/{int(job['id'])}" if is_job else ''),
            'controls': [{'label': 'Open run / controls', 'url': run_url, 'kind': 'provider_link'}],
            'control_note': 'Cancel or re-run in GitHub, subject to sign-in, permission and run state; no pause API'}


class GitHubCollector:
    interval = 30
    def __init__(self, api=None):
        self.api = api or GitHubAPI()
        self.completed = {}

    def collect(self, now=None):
        supplied_now = now
        runs = self.api.get(f'repos/{REPO}/actions/runs?per_page=20')['workflow_runs']
        now = time.time() if supplied_now is None else supplied_now
        active = [r for r in runs if r.get('status') != 'completed']
        completed = [r for r in runs if r.get('status') == 'completed']
        selected = (active + completed)[:4]
        rows, details = [], 0
        for run in selected:
            key = (run['id'], run.get('run_attempt', 1))
            cached = self.completed.get(key)
            if cached is not None:
                rows.extend(cached)
                continue
            data = self.api.get(f"repos/{REPO}/actions/runs/{int(run['id'])}/attempts/{int(run.get('run_attempt', 1))}/jobs?per_page=100")
            details += 1
            jobs = data['jobs']
            job_observed_at = time.time() if supplied_now is None else supplied_now
            normalized = [github_row(j, run, job_observed_at) for j in jobs] or [github_row(run, run, now)]
            if data.get('total_count', len(jobs)) > len(jobs):
                normalized.append({**github_row(run, run, now), 'name': str(run.get('name', 'Workflow')) + ' · more jobs at provider'})
            if run.get('status') == 'completed' and jobs and all(j.get('status') == 'completed' for j in jobs):
                self.completed[key] = normalized
            rows.extend(normalized)
        for run in (active + completed)[4:]:
            rows.append(github_row(run, run, now))
        keys = {(r['id'], r.get('run_attempt', 1)) for r in completed}
        self.completed = {key: value for key, value in self.completed.items() if key in keys}
        return {'rows': rows, 'status': 'ok' if runs else 'empty', 'detail_requests': details,
                'scope': 'Newest 20 BoxBrain runs; jobs for up to 4 prioritized runs, max 100 jobs each. Completed details cached.',
                'limits': 'GitHub status/steps/log links only; CPU/RAM unavailable without job instrumentation',
                'next_poll_seconds': 30 if active else 60}


def provider_sample(collector, previous=None, now=None):
    supplied_now = now
    now = time.time() if now is None else now
    start, cpu_start = time.perf_counter(), time.process_time()
    previous = previous or {}
    try:
        data = collector.collect(now=supplied_now)
        received_at = time.time() if supplied_now is None else supplied_now
        result = {**data, 'observed_at': received_at, 'last_attempt_at': now, 'error': None,
                  'consecutive_errors': 0, 'next_poll_seconds': data.get('next_poll_seconds', collector.interval)}
    except Exception as error:
        # Preserve last evidence with its original timestamps, explicitly disconnected.
        count = previous.get('consecutive_errors', 0) + 1
        kind = error.kind if isinstance(error, ProviderError) else type(error).__name__
        delay = error.retry_after if isinstance(error, ProviderError) else collector.interval
        result = {**previous, 'observed_at': previous.get('observed_at'), 'rows': previous.get('rows', []), 'status': 'disconnected' if kind in ('timeout', 'disconnected') else 'error',
                  'last_attempt_at': now, 'error': kind, 'http_status': getattr(error, 'code', None),
                  'consecutive_errors': count, 'next_poll_seconds': min(86400, max(delay, collector.interval * 2**min(count, 6)))}
    result['collector_wall_ms'] = round((time.perf_counter()-start)*1000, 2)
    result['collector_cpu_ms'] = round((time.process_time()-cpu_start)*1000, 2)
    result['overhead_scope'] = 'Monitor process CPU only; gh subprocess excluded, request wall time included'
    return result


def activity_snapshot(providers, now=None):
    now = time.time() if now is None else now
    out, rows = {}, []
    for name, source in providers.items():
        observed = source.get('observed_at')
        age = max(0, now-observed) if observed is not None else None
        threshold = 10 if name == 'local' else 90
        stale = age is None or age > threshold
        out[name] = {k: v for k, v in source.items() if k != 'rows'}
        out[name].update(age_seconds=age, stale=stale)
        for raw in source.get('rows', []):
            terminal = raw['state'] in ('ended', 'success', 'failure', 'cancelled', 'skipped', 'timed_out', 'neutral', 'action_required', 'stale')
            row = {**raw, 'age_seconds': max(0, now-raw['observed_at']),
                   'freshness': 'disconnected' if source.get('status') not in ('ok', 'empty') else
                                'stale' if stale else 'historical' if terminal else
                                'fresh' if now-raw['observed_at'] <= threshold else 'stale'}
            rows.append(row)
    local = [r for r in rows if r['provider'] == 'local' and r['state'] == 'running' and r['freshness'] == 'fresh']
    heavy = [r for r in local if r.get('cpu_percent') is not None and r['cpu_percent'] >= 25]
    summary = {'local_running': len(local), 'local_heavy_cpu_count': len(heavy),
               'local_heavy_cpu_percent': max((r['cpu_percent'] for r in heavy), default=0),
               'local_heavy_ids': [r['id'] for r in heavy],
               'github_active_observed': sum(r['provider'] == 'github' and r['state'] in ('in_progress', 'queued', 'waiting', 'requested', 'pending') and r['freshness'] == 'fresh' for r in rows)}
    # Stable for the same source evidence; a browser refresh is not a new observation.
    identifier = digest({name: {'observed_at': source.get('observed_at'), 'last_attempt_at': source.get('last_attempt_at'),
                               'status': source.get('status')} for name, source in providers.items()})
    return {'schema': SCHEMA, 'snapshot_id': identifier, 'observed_at': now, 'read_only': True,
            'authority_granted': False, 'providers': out, 'rows': rows, 'summary': summary,
            'capability_gaps': [{'provider': 'Codex cloud', 'status': 'telemetry_unavailable', 'url': ENVIRONMENT,
                'detail': 'Saved environment only. No supported live workload telemetry is connected; activity and CPU/RAM are unknown.'}],
            'limits': 'Observed inventory only. Unknown ownership stays unknown. No process termination, migration or automatic cloud dispatch.'}
