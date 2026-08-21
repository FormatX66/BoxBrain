from pathlib import Path


SCRIPT = Path("installer/repair-aurum-local-lane.ps1").read_text(encoding="utf-8")


def test_clean_divergent_history_is_preserved_before_alignment():
    assert 'status", "--porcelain", "--untracked-files=no"' in SCRIPT
    assert 'merge-base", "--is-ancestor"' in SCRIPT
    assert 'refs/heads/aurum/recovery-backup-' in SCRIPT
    assert '"update-ref", $historyBackupRef, $localHeadBeforeSync' in SCRIPT
    assert '"reset", "--hard", "refs/remotes/origin/main"' in SCRIPT
    assert "backup-and-reset-to-origin-main" in SCRIPT


def test_divergence_recovery_is_observable_and_reversible():
    assert "history_recovery = $historyRecovery" in SCRIPT
    assert "history_backup_ref = $historyBackupRef" in SCRIPT
    assert 'reset", "--hard", $localHeadBeforeSync' in SCRIPT
    assert "Could not preserve divergent Aurum lane history before alignment." in SCRIPT


def test_dirty_tracked_state_still_blocks_automatic_alignment():
    dirty_guard = SCRIPT.index('Existing Aurum lane repository has unrelated local changes.')
    backup_logic = SCRIPT.index('refs/heads/aurum/recovery-backup-')
    assert dirty_guard < backup_logic
