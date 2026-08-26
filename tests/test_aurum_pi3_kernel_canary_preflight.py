from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "aurum-pi3-kernel-canary-preflight.yml"


def test_posix_scripts_are_normalized_before_base64_transport():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert '$probeScript = $probeScript.Replace("`r`n", "`n")' in text
    assert '$moduleScript = $moduleScript.Replace("`r`n", "`n")' in text
    assert text.index("$probeScript.Replace") < text.index("$probeEncoded")
    assert text.index("$moduleScript.Replace") < text.index("$moduleEncoded")
