from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "aurum-authorized-windows-ap.yml"


def test_bounded_local_lane_skip_codes_do_not_fail_the_workflow_step():
    text = WORKFLOW.read_text(encoding="utf-8")
    recovery = text.split("switch ($code) {", 1)[1].split(
        "- name: Locate authorized checkout and self-heal Aurum worker", 1
    )[0]

    assert "2 { Write-Host 'AURUM_LOCAL_LANE_RECOVERY bounded-repair=skipped reason=no-existing-approval' }" in recovery
    assert "3 { Write-Host 'AURUM_LOCAL_LANE_RECOVERY bounded-repair=skipped reason=broader-drift-review-required' }" in recovery
    assert 'default { throw "Bounded Aurum local-lane repair failed with exit code $code" }' in recovery
    assert "exit 0" in recovery


def test_authorized_worker_recovery_remains_after_bounded_repair_gate():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "Locate authorized checkout and self-heal Aurum worker" in text
    assert "AURUM_WORKER_RECOVERY heartbeat=true" in text
    assert "AURUM_AUTHORIZED_WINDOWS_AP_COMPLETE" in text
