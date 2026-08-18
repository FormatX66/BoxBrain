#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / 'autobuild'
STATE = STATE_DIR / 'state.json'
EVENTS = STATE_DIR / 'events.jsonl'
CONTROLLER = 'https://arkmatx.com/aurum/index.php'

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
        }
    return {
        'ok': True,
        'node': status.get('node'),
        'status': status.get('status'),
        'capabilities': sorted(status.get('capabilities') or []),
    }


def semantic_projection(state):
    """Return only state that can change the actual capability/frontier.

    Heartbeat timestamps, controller event counters, run counters and observation
    times are deliberately excluded. They are evidence, not progress.
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
        observed_controller = {
            'ok': False,
            'error': type(exc).__name__,
            'time': observed_at,
        }

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
                    'volatile_controller_events': observed_controller.get('events'),
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
        state['last_controller_ack'] = {
            'ok': False,
            'error': type(exc).__name__,
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
        },
    )
    save_state(state)
    print(json.dumps(state, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
