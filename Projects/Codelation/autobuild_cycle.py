#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / 'autobuild'
STATE = STATE_DIR / 'state.json'
EVENTS = STATE_DIR / 'events.jsonl'
DEFAULT_CONTROLLER = 'https://arkmatx.com/aurum/index.php'
CONTROLLER = os.environ.get('AURUM_CONTROLLER_PRIMARY') or DEFAULT_CONTROLLER
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


def _controller_urls():
    raw = os.environ.get('AURUM_CONTROLLER_FALLBACKS') or ''
    extras = []
    for line in raw.splitlines():
        extras.extend(part.strip() for part in line.split(',') if part.strip())
    return tuple(dict.fromkeys([CONTROLLER] + extras))


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


def controller_status(endpoint=None):
    endpoint = endpoint or CONTROLLER
    request = urllib.request.Request(
        endpoint,
        headers={'Cache-Control': 'no-cache', 'User-Agent': 'Aurum-Autobuild/3'},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def controller_emit(cycle, next_intent, targets, endpoint=None, frame_id=None):
    endpoint = endpoint or CONTROLLER
    frame = {
        'schema': 'aurum.uaf.v0',
        'frame_id': frame_id or uuid.uuid4().hex,
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
        endpoint,
        data=body,
        method='POST',
        headers={'Content-Type': 'application/json', 'User-Agent': 'Aurum-Autobuild/3'},
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
        return 'try-alternate-carrier-then-continue-independent-lanes-preserve-state-respect-retry-after'
    if classification == 'controller-or-hosting-failure':
        return 'try-alternate-carrier-then-continue-independent-lanes-preserve-state-backoff'
    if classification == 'authorization-or-policy':
        return 'try-alternate-authorized-carrier-then-continue-independent-lanes-preserve-state'
    if classification == 'transport-or-dns-failure':
        return 'try-alternate-carrier-then-continue-independent-lanes-preserve-state-backoff'
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
        classification = 'transport-or-dns-failure'
        return {
            'ok': False,
            'error': type(exc).__name__,
            'reason': str(exc.reason),
            'classification': classification,
            'action': _failure_action(classification),
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


def probe_controller():
    failures = []
    for endpoint in _controller_urls():
        try:
            return controller_status(endpoint), endpoint, failures
        except Exception as exc:
            failure = describe_exception(exc, int(time.time()))
            failure['endpoint'] = endpoint
            failures.append(failure)
    return None, None, failures


def _ordered_emit_endpoints(preferred_endpoint=None):
    urls = list(_controller_urls())
    if preferred_endpoint and preferred_endpoint in urls:
        urls.remove(preferred_endpoint)
        urls.insert(0, preferred_endpoint)
    elif preferred_endpoint:
        urls.insert(0, preferred_endpoint)
    return tuple(dict.fromkeys(urls))


def emit_with_failover(cycle, next_intent, targets, preferred_endpoint=None):
    failures = []
    frame_id = uuid.uuid4().hex
    for endpoint in _ordered_emit_endpoints(preferred_endpoint):
        try:
            return (
                controller_emit(
                    cycle,
                    next_intent,
                    targets,
                    endpoint=endpoint,
                    frame_id=frame_id,
                ),
                endpoint,
                failures,
            )
        except Exception as exc:
            failure = describe_exception(exc, int(time.time()))
            failure['endpoint'] = endpoint
            failures.append(failure)
    return None, None, failures


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

    Heartbeat timestamps, controller event counters, carrier selection, failed
    carrier diagnostics, response bodies, limit headers and observation times are
    evidence, not progress.
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
    return state.get('semantic_fingerprint') or semantic_fingerprint(state)


def main():
    state = load_state()
    previous_fingerprint = _stored_fingerprint(state)

    observed_at = int(time.time())
    controller, controller_endpoint, carrier_failures = probe_controller()
    if controller is not None:
        capabilities = sorted(controller.get('capabilities') or [])
        observed_controller = {
            'ok': True,
            'node': controller.get('node'),
            'status': controller.get('status'),
            'events': controller.get('events'),
            'capabilities': capabilities,
            'endpoint': controller_endpoint,
            'carrier_failures': carrier_failures,
            'time': observed_at,
        }
        if 'node_enroll' in capabilities and 'node_heartbeat' in capabilities:
            state['targets']['BBPI4']['outbound_enrollment_ready'] = True
            state['targets']['Aurum-Morris']['outbound_enrollment_ready'] = True
    else:
        if carrier_failures:
            observed_controller = dict(carrier_failures[-1])
            observed_controller['carrier_failures'] = carrier_failures
            observed_controller['all_carriers_failed'] = True
        else:
            observed_controller = {
                'ok': False,
                'error': 'NoControllerCarrier',
                'classification': 'unavailable-external-prerequisite',
                'action': 'continue-independent-lanes-preserve-state',
                'carrier_failures': [],
                'all_carriers_failed': True,
                'time': observed_at,
            }

    state['last_controller_status'] = observed_controller
    state['next'] = choose_next(state)
    current_fingerprint = semantic_fingerprint(state)

    if current_fingerprint == previous_fingerprint:
        print(
            json.dumps(
                {
                    'schema': 'aurum-autobuild-cycle-result-v3',
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

    if observed_controller.get('ok'):
        ack, ack_endpoint, ack_failures = emit_with_failover(
            state['cycle'],
            state['next'],
            state['targets'],
            preferred_endpoint=controller_endpoint,
        )
        if ack is not None:
            state['last_controller_ack'] = {
                'ok': ack.get('status') == 'merged',
                'endpoint': ack_endpoint,
                'carrier_failures': ack_failures,
                'time': int(time.time()),
            }
        elif ack_failures:
            state['last_controller_ack'] = dict(ack_failures[-1])
            state['last_controller_ack']['carrier_failures'] = ack_failures
            state['last_controller_ack']['all_carriers_failed'] = True
        else:
            state['last_controller_ack'] = {
                'ok': False,
                'error': 'NoControllerCarrier',
                'classification': 'unavailable-external-prerequisite',
                'action': 'checkpoint-local-await-carrier',
                'time': int(time.time()),
            }
    else:
        state['last_controller_ack'] = {
            'ok': False,
            'error': 'ControllerCarrierUnavailable',
            'classification': observed_controller.get('classification'),
            'action': 'checkpoint-local-continue-independent-lanes-await-carrier',
            'carrier_failures': observed_controller.get('carrier_failures', []),
            'time': int(time.time()),
        }

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
