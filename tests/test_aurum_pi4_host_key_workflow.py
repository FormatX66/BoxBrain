from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "aurum-dual-seed-lanes.yml"
RECONCILER = ROOT / "installer" / "reconcile-existing-aurum-gold-seed-on-pi.ps1"


def test_pi4_usb_host_key_reuses_only_pretrusted_ed25519_key():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "usb-c-host-key-not-pretrusted" in text
    assert "ssh-keyscan.exe" in text
    assert "trustedKeyBlobs.Contains($blob)" in text
    assert "host_key_pretrusted = $true" in text
    assert "StrictHostKeyChecking=no" not in text
    assert "StrictHostKeyChecking=accept-new" not in text


def test_pi4_usb_host_key_alias_is_reversible():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "systemKnownHostsBackup" in text
    assert "[IO.File]::WriteAllBytes($systemKnownHosts, $systemKnownHostsBackup)" in text
    assert "Remove-Item -LiteralPath $systemKnownHosts" in text


def test_reconciler_still_requires_strict_host_key_checking():
    text = RECONCILER.read_text(encoding="utf-8")
    assert '"-o", "StrictHostKeyChecking=yes"' in text
