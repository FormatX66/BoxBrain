"""Observe host pressure and control only the explorer's own resource budget."""
import os
from pathlib import Path
import time


class HostSampler:
    def __init__(self):
        self.previous = None

    def sample(self):
        try:
            if os.name == 'nt':
                import ctypes as c
                from ctypes import wintypes as w
                class Memory(c.Structure):
                    _fields_ = [('length', w.DWORD), ('load', w.DWORD)] + [
                        (name, c.c_ulonglong) for name in ('total', 'available', 'commit_limit',
                        'commit_available', 'virtual_total', 'virtual_available', 'extended')]
                mem = Memory()
                mem.length = c.sizeof(mem)
                kernel = c.WinDLL('kernel32', use_last_error=True)
                if not kernel.GlobalMemoryStatusEx(c.byref(mem)):
                    raise OSError('memory sampler unavailable')
                idle, system, user = w.FILETIME(), w.FILETIME(), w.FILETIME()
                if not kernel.GetSystemTimes(c.byref(idle), c.byref(system), c.byref(user)):
                    raise OSError('CPU sampler unavailable')
                ticks = lambda t: t.dwLowDateTime + (t.dwHighDateTime << 32)
                total, idle_ticks = ticks(system)+ticks(user), ticks(idle)
                result = {'available_memory_mb': round(mem.available/1024**2),
                          'physical_load_percent': mem.load,
                          # This may be process-limited; use as conservative
                          # headroom, not a claim of system-wide commit usage.
                          'commit_headroom_percent': round(100*mem.commit_available/max(1,mem.commit_limit),1),
                          'source': 'GlobalMemoryStatusEx/GetSystemTimes'}
            elif Path('/proc/meminfo').exists():
                memory = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
                cpu = [int(n) for n in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
                total, idle_ticks = sum(cpu), cpu[3]+cpu[4]
                result = {'available_memory_mb': round(memory['MemAvailable']/1024),
                          'physical_load_percent': round(100*(1-memory['MemAvailable']/memory['MemTotal']),1),
                          'commit_headroom_percent': None, 'source': '/proc/meminfo and /proc/stat'}
            else:
                raise OSError('host sampler unavailable')
            cpu_percent = None
            if self.previous and total > self.previous[0]:
                cpu_percent = round(max(0,min(100,100*(1-(idle_ticks-self.previous[1])/(total-self.previous[0])))),1)
            self.previous = (total, idle_ticks)
            return {**result, 'cpu_percent': cpu_percent, 'available': True, 'observed_at': time.time()}
        except (OSError, ValueError, KeyError):
            return {'available': False, 'observed_at': time.time()}


class ResourceGovernor:
    def __init__(self):
        self.mode, self.high_samples, self.clear_samples = 'normal', 0, 0

    def choose(self, sample, activity=None):
        cpu, available, load = sample.get('cpu_percent'), sample.get('available_memory_mb'), sample.get('physical_load_percent')
        headroom = sample.get('commit_headroom_percent')
        unknown = not sample.get('available')
        activity = activity or {'available': False, 'reason': 'not_connected'}
        # Remote CPU/RAM never enters local pressure. A fresh process observation
        # may only constrain this explorer when independent host CPU corroborates it.
        contention = bool(activity.get('available') and activity.get('local_heavy_cpu_count', 0) > 0
                          and activity.get('local_heavy_cpu_percent', 0) >= 25 and cpu is not None and cpu >= 50)
        critical = not unknown and (available < 256 or (headroom is not None and headroom < 3))
        high = not unknown and (contention or available < 1024 or load >= 90 or (cpu is not None and cpu >= 85)
                               or (headroom is not None and headroom < 10))
        clear = not unknown and not contention and available > 1536 and load < 85 and cpu is not None and cpu < 70 and (headroom is None or headroom > 15)
        self.high_samples = self.high_samples+1 if high else 0
        self.clear_samples = self.clear_samples+1 if clear else 0
        if unknown:
            self.mode = 'conservative_unknown'
        elif critical:
            self.mode = 'critical_pressure'
        elif self.high_samples >= 3:
            self.mode = 'sustained_pressure'
        elif self.clear_samples >= 5:
            self.mode = 'normal'
        if self.mode == 'normal':
            cases, cpu_seconds, delay = 16, .15, 1
        elif self.mode == 'critical_pressure':
            cases, cpu_seconds, delay = 1, .001, 5
        else:
            cases, cpu_seconds, delay = 1, .005, 3
        return {'mode': self.mode, 'cases': cases, 'cpu_seconds': cpu_seconds, 'yield_seconds': delay,
                'selected': 'normal_local_budget' if self.mode == 'normal' else 'reduced_local_budget',
                'observed_host': sample, 'owner': 'Future Branch failure explorer only',
                'activity_evidence': activity, 'activity_contention': contention,
                'candidates': ['normal_local_budget', 'reduced_local_budget'],
                'external_process_control': 'not_configured', 'cloud_routing': 'not_configured',
                'recovery': 'Restore normal budget after five clear samples; preserve all external workloads'}
