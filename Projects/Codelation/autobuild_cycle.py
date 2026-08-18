#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / 'autobuild'
STATE = STATE_DIR / 'state.json'
EVENTS = STATE_DIR / 'events.jsonl'
CONTROLLER = 'https://arkmatx.com/aurum/index.php'
ERROR_BODY_LIMIT = 4096
LIMIT_HEADERS = (
    'Retry-After',
    'RateLimit-Limit',
    'RateLimit-Remaining',
    'RateLimit-Reset',
    'X-RateLimit-Limit',
    'X-RateLimit-Remaining',
    'X-RateLimit-Reset',
)

DEFAULT = {
    'schema': 1,
    'cycle': 0,
    'last_controller_status': None,
    'last_controller_ack': None,
    'semantic_fingerprint': None,
    'targets': {
        'BBPI4': {
            'status': 'unconfirmed',
            'outbound_enrollment_ready': False,
            'carriers': [
                '10.12.194.1',
                '10.42.194.1',
                'bbpi4.local',
                '192.168.0.194',
                'remote-desktop',
                'arkmatx-outbound',
            ],
            'preferred_bootstrap': [
                '10.12.194.1',
                '10.42.194.1',
                'bbpi4.local',
                'remote-desktop',
            ],
        },
        'Aurum-Morris': {
            'status': 'unconfirmed',
            'outbound_enrollment_ready': False,
            'carriers': ['winrm', 'arkmatx-outbound', 'local-windows-lane'],
            'preferred_bootstrap': ['winrm'],
        },
    },
    'next': 'probe-controller-and-target-plan',
}


def load_state():
    if not STATE.exists():
        return json.loads(json.dumps(DEFAULT))
    current = json.loads(STATE.read_text())
    for name, defaults in DEFAULT['targets'].items():
        target = current.setdefault('targets', {}).setdefault(name, {})
        target.setdefault('status', 'unconfirmed')
        target.setdefault('outbound_enrollment_ready', False)
        existing = list(target.get('carriers', []))
        target['carriers'] = list(dict.fromkeys(defaults['carriers'] + existing))
        target['preferred_bootstrap'] = defaults.get('preferred_bootstrap', [])
    return current


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')


def event(kind, payload):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with EVENTS.open('a', encoding='utf-8') as handle:
        handle.write(
            json.dumps(
                {'time': int(time.time()), 'kind': kind, 'payload': payload},
                sort_keys=True,
            )
            + '\n'
        )


def controller_status():
    request = urllib.request.Request(
        CONTROLLER,
        headers={'Cache-Control': 'no-cache', 'User-Agent': 'Aurum-Autobuild/2'},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def controller_emit(cycle, next_intent, targets):
    frame = {
        'schema': 'aurum.uaf.v0',
        'frame_id': uuid.uuid4().hex,
        'origin': 'Aurum-GitHub-Autobuild',
        'target': 'Aurum-Arkmatx',
        'intent': 'build_checkpoint',
        'state_delta': {
            'cycle': cycle,
            'next': next_intent,
            'builder': 'github-python',
            'targets': targets,
        },
        'provenance': {
            'node': 'Aurum-GitHub-Autobuild',
            'created': int(time.time()),
        },
        'verification': {'content_addressed': True, 'reversible': True},
    }
    body = json.dumps(frame, separators=(',', ':')).encode()
    request = urllib.request.Request(
        CONTROLLER,
        data=body,
        method='POST',
        headers={'Content-Type': 'application/json', 'User-Agent': 'Aurum-Autobuild/2'},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def _read_http_error_body(exc):
    try:
        raw = exc.read(ERROR_BODY_LIMIT)
    except Exception:
        return None
    if not raw:
        return None
    if isinstance(raw, bytes):
        return raw.decode('utf-8', errors='replace')
    return str(raw)


def _limit_headers(exc):
    headers = getattr(exc, 'headers', None)
    if not headers:
        return {}
    found = {}
    for name in LIMIT_HEADERS:
        value = headers.get(name)
        if value is not None:
            found[name] = value
    return found


def _classify_http_error(code, body):
    text = (body or '').lower()
    if code == 429:
        return 'rate-or-usage-limit'
    if code == 402:
        return 'billing-or-quota-limit'
    if code == 403 and any(word in text for word in ('quota', 'rate limit', 'usage limit', 'resource limit')):
        return 'usage-or-quota-limit'
    if code == 403:
        return 'authorization-or-policy'
    if 500 <= code <= 599:
        return 'controller-or-hosting-failure'
    if 400 <= code <= 499:
        return 'request-or-client-failure'
    return 'http-failure'


def _failure_action(classification):
    if classification in {
        'rate-or-usage-limit',
        'billing-or-quota-limit',
        'usage-or-quota-limit',
    }:
        return 'continue-independent-lanes-preserve-state-respect-retry-after'
    if classification == 'controller-or-hosting-failure':
        return 'continue-independent-lanes-preserve-state-backoff-and-reprobe'
    if classification == 'authorization-or-policy':
        return 'continue-independent-lanes-preserve-state-use-alternate-carrier'
    return 'continue-safe-independent-lanes-preserve-state'


def describe_exception(exc, observed_at):
    if isinstance(exc, urllib.error.HTTPError):
        body = _read_http_error_body(exc)
        classification = _classify_http_error(int(exc.code), body)
        return {
            'ok': False,
            'error': type(exc).__name__,
            'http_status': int(exc.code),
            'reason': str(exc.reason) if exc.reason is not None else None,
            'classification': classification,
            'action': _failure_action(classification),
            'limit_headers': _limit_headers(exc),
            'response_body': body,
            'time': observed_at,
        }
    if isinstance(exc, urllib.error.URLError):
        return {
            'ok': False,
            'error': type(exc).__name__,
            'reason': str(exc.reason),
            'classification': 'transport-or-dns-failure',
            'action': 'continue-independent-lanes-preserve-state-backoff-and-reprobe',
            'time': observed_at,
        }
    return {
        'ok': False,
        'error': type(exc).__name__,
        'reason': str(exc),
        'classification': 'unexpected-controller-failure',
        'action': 'continue-safe-independent-lanes-preserve-state',
        'time': observed_at,
    }


def choose_next(state):
    morris = state['targets']['Aurum-Morris']
    bb = state['targets']['BBPI4']
    if not morris.get('outbound_enrollment_ready') or not bb.get('outbound_enrollment_ready'):
        return 'deploy-and-verify-outbound-node-heartbeat'
    if morris['status'] != 'confirmed':
        return 'bootstrap-morris-via-winrm-then-enroll-arkmatx'
    if bb['status'] != 'confirmed':
        return 'bootstrap-bbpi4-via-usb-ap-mdns-or-rdp-then-enroll-arkmatx'
    return 'slush-repo-ingest'


def _controller_semantics(status):
    if not status:
        return None
    if status.get('ok') is False:
        return {
            'ok': False,
            'error': status.get('error'),
            'http_status': status.get('http_status'),
            'classification': status.get('classification'),
            'action': status.get('action'),
        }
    return {
        'ok': True,
        'node': status.get('node'),
        'status': status.get('status'),
        'capabilities': sorted(status.get('capabilities') or []),
    }


def semantic_projection(state):
    """Return only state that can change the actual capability/frontier.

    Heartbeat timestamps, controller event counters, run counters, diagnostic
    response bodies, limit headers and observation times are evidence, not progress.
    """
    return {
        'controller': _controller_semantics(state.get('last_controller_status')),
        'targets': state.get('targets', {}),
        'next': state.get('next'),
    }


def semantic_fingerprint(state):
    payload = json.dumps(
        semantic_projection(state),
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def _stored_fingerprint(state):
    # Migration-safe: older states did not persist a fingerprint. Derive one from
    # the existing semantic fields so deployment of this fix does not itself
    # manufacture a fake state advance.
    return state.get('semantic_fingerprint') or semantic_fingerprint(state)


def main():
    state = load_state()
    previous_fingerprint = _stored_fingerprint(state)

    observed_at = int(time.time())
    try:
        controller = controller_status()
        capabilities = sorted(controller.get('capabilities') or [])
        observed_controller = {
            'ok': True,
            'node': controller.get('node'),
            'status': controller.get('status'),
            'events': controller.get('events'),
            'capabilities': capabilities,
            'time': observed_at,
        }
        if 'node_enroll' in capabilities and 'node_heartbeat' in capabilities:
            state['targets']['BBPI4']['outbound_enrollment_ready'] = True
            state['targets']['Aurum-Morris']['outbound_enrollment_ready'] = True
    except Exception as exc:
        observed_controller = describe_exception(exc, observed_at)

    # Use the fresh observation to choose the frontier, but do not persist its
    # volatile counters/timestamp until we know the semantic state changed.
    state['last_controller_status'] = observed_controller
    state['next'] = choose_next(state)
    current_fingerprint = semantic_fingerprint(state)

    if current_fingerprint == previous_fingerprint:
        print(
            json.dumps(
                {
                    'schema': 'aurum-autobuild-cycle-result-v2',
                    'advanced': False,
                    'reason': 'no-new-semantic-state',
                    'next': state['next'],
                    'semantic_fingerprint': current_fingerprint,
                    'controller_observation': observed_controller,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    state['cycle'] = int(state.get('cycle', 0)) + 1
    event('controller-semantic-change', _controller_semantics(observed_controller))

    try:
        ack = controller_emit(state['cycle'], state['next'], state['targets'])
        state['last_controller_ack'] = {
            'ok': ack.get('status') == 'merged',
            'time': int(time.time()),
        }
    except Exception as exc:
        state['last_controller_ack'] = describe_exception(exc, int(time.time()))

    state['semantic_fingerprint'] = current_fingerprint
    state['updated_at'] = int(time.time())
    event(
        'cycle-checkpoint',
        {
            'cycle': state['cycle'],
            'next': state['next'],
            'targets': state['targets'],
            'semantic_fingerprint': current_fingerprint,
            'controller': _controller_semantics(observed_controller),
        },
    )
    save_state(state)
    print(json.dumps(state, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
