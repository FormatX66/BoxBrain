from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "aurum-pi3-adaptive-driver.yml"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_pi3_transport_remains_strict_key_only_and_single_target():
    text = workflow_text()

    assert "$targets = @([string]$identity.pinned_ipv4)" in text
    assert "Test-NetConnection -ComputerName $target -Port 22" in text
    assert text.count("-o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes") == 2
    assert "-o UserKnownHostsFile=$knownHosts" in text
    assert "-o ConnectTimeout=5 -o ConnectionAttempts=1" in text
    assert "StrictHostKeyChecking=no" not in text
    assert "StrictHostKeyChecking=accept-new" not in text


def test_retrust_observation_is_machine_readable_but_never_promotes_trust():
    text = workflow_text()

    assert "aurum.pi3.adaptive-driver.control.v1" in text
    assert "identity_contract_sha256" in text
    assert "known_hosts_sha256" in text
    assert "expected_host_key_sha256" in text
    assert "observed_host_key_sha256" in text
    assert "host-key-confirmation-required" in text
    assert "confirmation_must_be_independent = [bool]$hostKeyChanged" in text
    assert "exact-host-key-fingerprint-confirmation" in text
    assert "untrusted_network_observation_is_not_confirmation = $true" in text
    assert "pi_console_typing_required = $false" in text
    assert "observed_key_source = $scanState" in text
    assert "persistent_trust_changed = $false" in text
    assert "Set-Content -LiteralPath $knownHosts" not in text
    assert "Move-Item -LiteralPath $temporary -Destination $knownHosts" not in text

    tcp = text.index("Test-NetConnection -ComputerName $target -Port 22")
    strict_ssh = text.index("$identityLines = @(& $ssh.Source")
    untrusted_observation = text.index("Get-Command ssh-keyscan")
    assert tcp < strict_ssh < untrusted_observation


def test_local_trust_contract_requires_one_exact_entry_and_exact_fingerprint():
    text = workflow_text()

    assert "$knownHostLines.Count -eq 1" in text
    assert "$knownHostParts.Count -eq 3" in text
    assert "[string]$knownHostParts[0] -eq [string]$identity.pinned_ipv4" in text
    assert "[string]$knownHostParts[1] -eq [string]$identity.host_key_algorithm" in text
    assert "$pinnedFingerprint -eq $expectedFingerprint" in text
    assert "local-pinned-trust-contract-invalid" in text


def test_farmer_receipt_captures_authoritative_post_resume_state():
    text = workflow_text()

    assert "aurum.pi3.adaptive-driver.farmer-progression.v1" in text
    assert "source_result_sha256" in text
    assert "pre_resume = $null" in text
    assert "post_resume = $null" in text
    assert "resume_requested = $false" in text
    assert "changed-dimension evidence" in text
    assert "event_chain_valid" in text
    assert "sealed_receipts" in text
    assert "adaptive_driver_physical_result" in text
    assert "progression_verified" in text
    assert "post-resume-terminal-evidence-gate-not-satisfied" in text
    assert "AURUM_FARMER_POST_RESUME state=observation-error" in text

    resume = text.index("resume --job 'AF-PI3-ADAPTIVE-DRIVER-001'")
    post_status = text.index("$postRaw = @(& $python -m aurum_farmer")
    health = text.index("http://127.0.0.1:19466/health")
    receipts = text.index("receipts --job 'AF-PI3-ADAPTIVE-DRIVER-001'")
    assert resume < post_status < health < receipts


def test_artifact_contains_semantic_control_and_farmer_receipts():
    text = workflow_text()

    assert "adaptive-driver-evidence/control-receipt.json" in text
    assert "adaptive-driver-evidence/farmer-state.json" in text
    assert "path: adaptive-driver-evidence/*.json" in text
