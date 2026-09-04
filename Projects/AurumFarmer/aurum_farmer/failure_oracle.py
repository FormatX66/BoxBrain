"""Independent invariants for read-only decision-policy fault models.

This verifier does not call the engine's score, normalization, or pruning logic.
Its verdict is model evidence, never an execution receipt or hardware proof.
"""


def verify_model(snapshot, candidate, report):
    findings = []
    protected = (
        not candidate['authority_ready'] or not candidate['dependencies_satisfied']
        or bool(candidate['human_boundary']) or candidate['impossible']
        or candidate['state'] != 'CANDIDATE' or candidate['attempt_count'] >= candidate['max_attempts']
        or candidate['risk'] > .35 or candidate['reversibility'] < .9
        or candidate['irreversible_cost'] > 0 or not candidate['expected_evidence']
        or candidate['expires_at'] is not None or bool(candidate['parents'])
        or candidate['effect'] != 'read_only' or candidate['required_tier'] != 'static'
    )
    positive = candidate['confidence'] * candidate['impact'] / 4 > candidate['risk'] + candidate['uncertainty']
    expected = not protected and positive
    selected = report.get('selected') == candidate['logical_id']
    automatic = any(b.get('automatic') for b in report.get('branches', []))
    if protected and (selected or automatic):
        findings.append('unsafe_automatic_promotion')
    elif expected != selected or selected != automatic:
        findings.append('selection_disagrees_with_independent_oracle')
    nodes = report.get('nodes', [])
    known = set()
    for node in nodes:
        if node['id'] in known or not set(node.get('parents', [])) <= known:
            findings.append('invalid_branch_dag')
            break
        known.add(node['id'])
        if node.get('kind') in {'prediction', 'recover', 'verify', 'protected_lkg', 'control'} and node.get('automatic'):
            findings.append('prediction_gained_execution_authority')
    protected_lkg = [n for n in nodes if n.get('kind') == 'protected_lkg']
    if len(protected_lkg) != 1 or protected_lkg[0].get('references') != snapshot['lkg'] or not report.get('lkg_preserved'):
        findings.append('lkg_protection_lost')
    if report.get('proposer') == report.get('executor') or any(
            test.get('verifier') in {report.get('proposer'), report.get('executor')}
            for branch in report.get('branches', []) for test in branch.get('tests', [])):
        findings.append('roles_not_independent')
    return sorted(set(findings))
