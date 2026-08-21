#!/usr/bin/env python3
"""Receipt-aware entry point for Aurum's bounded autonomous build cycle.

This adapter keeps the existing autobuild core intact while teaching the event
loop to consume strict, already-published physical Pi4 seed evidence. A verified
seed advances only from bootstrap to enrollment/heartbeat verification. BBPI4 is
confirmed only after a fresh ARM64 heartbeat is independently visible in the
Arkmatx node directory.
"""
from __future__ import annotations

import importlib.util
import json
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_PATH = REPO_ROOT / 'Projects' / 'Codelation' / 'autobuild_cycle.py'
PI4_RESULTS = REPO_ROOT / 'Projects' / 'AurumBridge' / 'results'
KNOWN_NON_PI_NODE_IDS = {'825e5a7b7d4a7aed', '85404f41d5507372'}
FRESH_HEARTBEAT_SECONDS = 15 * 60


def _load_core():
    spec = importlib.util.spec_from_file_location('aurum_autobuild_core', CORE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Aurum autobuild core from {CORE_PATH}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = _load_core()


def latest_pi4_seed_receipt(results_dir: Path = PI4_RESULTS):
    receipts = []
    if not results_dir.exists():
        return None
    for path in results_dir.glob('pi4-seed-*-attempt-*.json'):
        try:
            receipt = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError, TypeError):
            continue
        if receipt.get('schema') != 'aurum-pi4-seed-receipt-v1':
            continue
        try:
            run_id = int(receipt.get('github_workflow_run') or 0)
            attempt = int(receipt.get('github_run_attempt') or 0)
        except (TypeError, ValueError):
            continue
        receipts.append((run_id, attempt, path.name, receipt))
    if not receipts:
        return None
    return max(receipts, key=lambda item: (item[0], item[1], item[2]))[3]


def verified_pi4_seed(receipt):
    if not receipt or receipt.get('state') != 'PI4_SEED_OK':
        return False
    data = receipt.get('data') or {}
    return bool(
        data.get('aurum_live_verified') is True
        and data.get('peer_self_test_verified') is True
        and data.get('gold_seed_preserved') is True
        and data.get('host_key_pretrusted') is True
        and data.get('architecture') == 'arm64'
        and data.get('transport') == 'usb-c-ssh'
        and data.get('address') in {'10.12.194.1', '10.42.194.1'}
    )


def apply_verified_pi4_seed(state, results_dir: Path = PI4_RESULTS):
    receipt = latest_pi4_seed_receipt(results_dir)
    if not verified_pi4_seed(receipt):
        return False

    data = receipt.get('data') or {}
    bb = state.setdefault('targets', {}).setdefault('BBPI4', {})
    changed = (
        bb.get('physical_seed_verified') is not True
        or bb.get('physical_seed_transport') != 'usb-c-ssh'
        or bb.get('physical_seed_architecture') != 'arm64'
    )
    bb['physical_seed_verified'] = True
    bb['physical_seed_transport'] = 'usb-c-ssh'
    bb['physical_seed_architecture'] = 'arm64'

    # Receipt IDs and timestamps are evidence, not semantic progress. Keep them
    # under observations so a newer equivalent proof cannot create an endless
    # continuation loop.
    state.setdefault('observations', {})['pi4_seed_receipt'] = {
        'state': receipt.get('state'),
        'workflow_run': int(receipt.get('github_workflow_run') or 0),
        'run_attempt': int(receipt.get('github_run_attempt') or 0),
        'observed_at': receipt.get('observed_at'),
        'address': data.get('address'),
        'seed_sha256': data.get('seed_sha256'),
        'source_commit': data.get('source_commit'),
    }
    return changed


def controller_nodes():
    """Read the public node directory through an already-authorized controller carrier."""
    endpoints = core._controller_urls() if hasattr(core, '_controller_urls') else (core.CONTROLLER,)
    for endpoint in endpoints:
        url = endpoint.rstrip('/') + '/nodes'
        request = urllib.request.Request(
            url,
            headers={'Cache-Control': 'no-cache', 'User-Agent': 'Aurum-Autobuild/3'},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.load(response)
        except Exception:
            continue
        if isinstance(payload, dict) and isinstance(payload.get('nodes'), list):
            return payload
    return None


def verified_pi4_heartbeat(receipt, node_payload, now=None):
    """Return the freshest strict ARM64 Pi heartbeat, or None.

    A physical seed receipt is a prerequisite. Windows/controller identities are
    explicitly excluded, and only a recent Linux ARM64 outbound heartbeat can
    confirm BBPI4.
    """
    if not verified_pi4_seed(receipt) or not isinstance(node_payload, dict):
        return None
    now = int(time.time()) if now is None else int(now)
    minimum_seen = now - FRESH_HEARTBEAT_SECONDS
    candidates = []
    for node in node_payload.get('nodes') or []:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get('node_id') or '')
        if not node_id or node_id in KNOWN_NON_PI_NODE_IDS:
            continue
        if str(node.get('status') or '').lower() != 'online':
            continue
        if str(node.get('carrier') or '').lower() != 'https-outbound':
            continue
        if str(node.get('os') or '').lower() != 'linux':
            continue
        if str(node.get('arch') or '').lower() not in {'arm64', 'aarch64'}:
            continue
        try:
            last_seen = int(node.get('last_seen') or 0)
        except (TypeError, ValueError):
            continue
        if last_seen < minimum_seen or last_seen > now + 60:
            continue
        candidates.append((last_seen, node_id, node))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def apply_verified_pi4_identity(state, results_dir: Path = PI4_RESULTS, node_payload=None, now=None):
    receipt = latest_pi4_seed_receipt(results_dir)
    if node_payload is None:
        node_payload = controller_nodes()
    node = verified_pi4_heartbeat(receipt, node_payload, now=now)
    if node is None:
        return False

    bb = state.setdefault('targets', {}).setdefault('BBPI4', {})
    changed = (
        bb.get('status') != 'confirmed'
        or bb.get('node_id') != str(node.get('node_id'))
        or bb.get('confirmation') != 'fresh-arkmatx-arm64-heartbeat'
    )
    bb['status'] = 'confirmed'
    bb['node_id'] = str(node.get('node_id'))
    bb['confirmation'] = 'fresh-arkmatx-arm64-heartbeat'
    state.setdefault('observations', {})['bbpi4_identity_heartbeat'] = {
        'node_id': str(node.get('node_id')),
        'name': node.get('name'),
        'os': node.get('os'),
        'arch': node.get('arch'),
        'carrier': node.get('carrier'),
        'last_seen': int(node.get('last_seen') or 0),
    }
    return changed


def install_receipt_bridge(core_module=core, results_dir: Path = PI4_RESULTS):
    original_load_state = core_module.load_state
    original_choose_next = core_module.choose_next

    def load_state():
        state = original_load_state()
        apply_verified_pi4_seed(state, results_dir=results_dir)
        apply_verified_pi4_identity(state, results_dir=results_dir)
        return state

    def choose_next(state):
        next_intent = original_choose_next(state)
        bb = state.get('targets', {}).get('BBPI4', {})
        if (
            next_intent == 'bootstrap-bbpi4-via-usb-ap-mdns-or-rdp-then-enroll-arkmatx'
            and bb.get('physical_seed_verified') is True
            and bb.get('status') != 'confirmed'
        ):
            return 'enroll-bbpi4-arkmatx-and-verify-heartbeat'
        return next_intent

    core_module.load_state = load_state
    core_module.choose_next = choose_next
    return core_module


def main():
    install_receipt_bridge()
    core.main()


if __name__ == '__main__':
    main()
