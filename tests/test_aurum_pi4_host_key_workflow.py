from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "aurum-dual-seed-lanes.yml"
RECONCILER = ROOT / "installer" / "reconcile-existing-aurum-gold-seed-on-pi.ps1"


def test_pi4_usb_host_key_reuses_only_pretrusted_ed25519_key():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "usb-c-host-key-not-pretrusted" in text
    assert "ssh-keyscan.exe" in text
    assert "trustedPiKeyBlobs.Contains($blob)" in text
    assert "sshKeygen.Source -F $trustedPiAlias" in text
    assert "kali-raspberrypi.mshome.net" in text
    assert "trusted_ed25519_key_count" not in text
    assert "host_key_pretrusted = $true" in text
    assert "host_key_fingerprint = $verifiedHostKeyFingerprint" in text
    assert "StrictHostKeyChecking=no" not in text
    assert "StrictHostKeyChecking=accept-new" not in text


def test_pi4_uses_one_compatible_openssh_toolchain_and_handles_keyscan_stderr():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "Git\\usr\\bin" in text
    assert "previousErrorActionPreference" in text
    assert "keyscanExitCode = $LASTEXITCODE" in text
    assert "-SshExecutable $selectedToolchain.Ssh" in text
    assert "-ScpExecutable $selectedToolchain.Scp" in text
    assert "-UserKnownHostsFile $systemKnownHosts" in text


def test_pi4_usb_host_key_alias_is_reversible():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "systemKnownHostsBackup" in text
    assert "[IO.File]::WriteAllBytes($systemKnownHosts, $systemKnownHostsBackup)" in text
    assert "Remove-Item -LiteralPath $systemKnownHosts" in text


def test_reconciler_still_requires_strict_host_key_checking():
    text = RECONCILER.read_text(encoding="utf-8")
    assert '"-o", "StrictHostKeyChecking=yes"' in text
    assert '"UserKnownHostsFile=$UserKnownHostsFile"' in text
    assert "StrictHostKeyChecking=no" not in text


def test_reconciler_transfers_bounded_script_instead_of_inline_payload():
    text = RECONCILER.read_text(encoding="utf-8")
    assert "WriteAllText($localRemoteScript" in text
    assert '"${target}:$transfer/aurum-reconcile.sh"' in text
    assert "Remove-Item -LiteralPath $localRemoteScript" in text
    assert "base64.b64decode" not in text


def test_reconciler_handles_native_stderr_but_enforces_exit_codes():
    text = RECONCILER.read_text(encoding="utf-8")
    assert "function Invoke-OpenSshNative" in text
    assert '$ErrorActionPreference = "Continue"' in text
    assert "nativeExitCode = $LASTEXITCODE" in text
    assert "reconcileResult.ExitCode -ne 0" in text
    assert "evidenceResult.ExitCode -ne 0" in text
