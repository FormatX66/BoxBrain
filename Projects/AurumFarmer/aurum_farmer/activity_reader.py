"""Optional loopback observations can reduce this explorer's budget, never grant authority."""
import json
import math
import re
import time
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def validate_activity(data, now=None):
    now = time.time() if now is None else now
    if (not isinstance(data, dict) or data.get('schema') != 'aurum.workload-activity.v1'
            or data.get('read_only') is not True or data.get('authority_granted') is not False
            or not isinstance(data.get('snapshot_id'), str)
            or not re.fullmatch('[a-f0-9]{64}', data['snapshot_id'])):
        return {'available': False, 'reason': 'invalid_contract'}
    local = data.get('providers', {}).get('local', {})
    observed = local.get('observed_at')
    if (not isinstance(observed, (int, float)) or not math.isfinite(observed)
            or not -2 <= now-observed <= 10 or local.get('status') not in ('ok', 'empty')):
        return {'available': False, 'reason': 'local_activity_stale_or_disconnected'}
    summary = data.get('summary', {})
    percent, count = summary.get('local_heavy_cpu_percent'), summary.get('local_heavy_cpu_count')
    cloud_count = summary.get('github_active_observed')
    if (not isinstance(percent, (int, float)) or not math.isfinite(percent) or not 0 <= percent <= 100
            or not isinstance(count, int) or not 0 <= count <= 16384
            or not isinstance(cloud_count, int) or not 0 <= cloud_count <= 20000):
        return {'available': False, 'reason': 'invalid_metrics'}
    return {'available': True, 'snapshot_id': data['snapshot_id'], 'local_observed_at': observed,
            'local_heavy_cpu_percent': percent, 'local_heavy_cpu_count': count,
            'github_active_observed': cloud_count,
            'scope': 'Local contention may reduce explorer budget only; cloud activity is advisory',
            'authority_granted': False}


class ActivityReader:
    def __init__(self):
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.next_read = 0
        self.cached = None

    def sample(self):
        if time.monotonic() >= self.next_read:
            self.next_read = time.monotonic() + 3
            try:
                with self.opener.open('http://127.0.0.1:19467/api/activity', timeout=.25) as response:
                    raw = response.read(65537)
                if len(raw) > 65536:
                    raise ValueError('oversized observation')
                self.cached = json.loads(raw)
            except Exception:
                self.cached = None
        # Revalidate original source time even when reusing the cached response.
        try:
            return validate_activity(self.cached)
        except (TypeError, ValueError, AttributeError):
            return {'available': False, 'reason': 'invalid_contract'}
