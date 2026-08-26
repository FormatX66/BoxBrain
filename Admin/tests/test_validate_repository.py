"""Regression checks for the BoxBrain repository validator."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Admin.validate_repository import (
    destructive_workflow_policy_errors,
    repository_markdown_files,
)


class RepositoryValidatorTests(unittest.TestCase):
    def test_generated_markdown_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            expected = root / "docs" / "kept.md"
            expected.parent.mkdir()
            expected.write_text("# Kept\n", encoding="utf-8")

            for directory in (".venv", ".pytest_cache", ".dart_tool", "build"):
                generated = root / directory / "generated.md"
                generated.parent.mkdir()
                generated.write_text("# Generated\n", encoding="utf-8")

            (root / "AGENTS.md").write_text("# Local instructions\n", encoding="utf-8")

            self.assertEqual(repository_markdown_files(root), [expected])

    def test_retired_pc01_media_workflows_cannot_regain_persistent_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workflow_dir = root / ".github" / "workflows"
            workflow_dir.mkdir(parents=True)
            unsafe = {
                "aurum-pc01-flash-authorized.yml": (
                    "on:\n  workflow_run:\nenv:\n  AURUM_FLASH_AUTHORIZATION: old-static-authority\n"
                    "jobs:\n  flash:\n    steps:\n      - run: echo \\\\.\\PhysicalDrive1 && diskpart.exe\n"
                ),
                "aurum-pc01-grub-flash-once.yml": (
                    "on:\n  push:\nenv:\n  AURUM_FLASH_AUTHORIZATION: old-grub-authority\n"
                    "jobs:\n  flash:\n    steps:\n      - run: diskpart.exe\n"
                ),
                "aurum-pc01-reflash-once.yml": (
                    "on:\n  push:\nenv:\n  AURUM_REFLASH_AUTHORIZATION: old-reflash-authority\n"
                    "jobs:\n  flash:\n    steps:\n      - run: diskpart.exe\n"
                ),
            }
            for name, text in unsafe.items():
                (workflow_dir / name).write_text(text, encoding="utf-8")

            errors = destructive_workflow_policy_errors(root)
            self.assertGreaterEqual(len(errors), 12)
            self.assertTrue(any("workflow_run:" in error for error in errors))
            self.assertTrue(any("push:" in error for error in errors))
            self.assertTrue(any("AURUM_FLASH_AUTHORIZATION:" in error for error in errors))
            self.assertTrue(any("AURUM_REFLASH_AUTHORIZATION:" in error for error in errors))
            self.assertTrue(any("aurum-pc01-grub-flash-once.yml" in error for error in errors))
            self.assertTrue(any("aurum-pc01-reflash-once.yml" in error for error in errors))
            self.assertTrue(any("persistent static authorization" in error for error in errors))

    def test_repo_wide_scan_rejects_unknown_static_raw_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workflow = root / ".github" / "workflows" / "unexpected-media-writer.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text(
                "on:\n  workflow_dispatch:\n"
                "env:\n  AURUM_MEDIA_AUTHORIZATION: bruce-old-static-token\n"
                "jobs:\n  write:\n    steps:\n      - run: echo \\\\.\\PhysicalDrive9\n",
                encoding="utf-8",
            )

            errors = destructive_workflow_policy_errors(root)
            self.assertEqual(len(errors), 1)
            self.assertIn("unexpected-media-writer.yml", errors[0])
            self.assertIn("persistent static authorization", errors[0])

    def test_retired_pc01_media_tombstones_are_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workflow_dir = root / ".github" / "workflows"
            workflow_dir.mkdir(parents=True)
            tombstone = (
                "name: retired\n"
                "on:\n"
                "  workflow_dispatch:\n"
                "jobs:\n"
                "  retired:\n"
                "    steps:\n"
                "      - run: exit 1\n"
            )
            for name in (
                "aurum-pc01-flash-authorized.yml",
                "aurum-pc01-grub-flash-once.yml",
                "aurum-pc01-reflash-once.yml",
            ):
                (workflow_dir / name).write_text(tombstone, encoding="utf-8")

            self.assertEqual(destructive_workflow_policy_errors(root), [])

    def test_usb_discovery_atomically_projects_canonical_future_branch_state(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = (root / ".github" / "workflows" / "aurum-usb-discovery.yml").read_text(
            encoding="utf-8"
        )
        required = (
            "Admin/sync_aurum_release_status.py",
            "Admin/sync_aurum_future_branch_evidence.py",
            "Admin/sync_aurum_fallback_evidence.py",
            "Admin/materialize_aurum_next_interaction.py",
            "Projects/Aurum/completion-plan.json",
            "Projects/Aurum/future-branches.json",
            "Projects/Aurum/next-interaction-packet.json",
        )
        for token in required:
            self.assertIn(token, workflow)

        preflight_refresh = workflow.index("AURUM_USB_DISCOVERY_RECEIPT preflight-refresh-failed")
        branch_sync = workflow.index("Admin/sync_aurum_future_branch_evidence.py")
        persisted_state = workflow.index("Projects/Aurum/next-interaction-packet.json")
        self.assertLess(preflight_refresh, branch_sync)
        self.assertLess(branch_sync, persisted_state)

    def test_recovery_refresh_projects_the_same_complete_handoff_surface(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = (
            root / ".github" / "workflows" / "aurum-hopper-recovery-readonly-refresh.yml"
        ).read_text(encoding="utf-8")
        required = (
            "Admin/sync_aurum_release_status.py",
            "Admin/sync_aurum_future_branch_evidence.py",
            "Admin/sync_aurum_fallback_evidence.py",
            "Admin/materialize_aurum_next_interaction.py",
            "Projects/Aurum/Recovery/latest-tinyseed-physical-preflight.json",
            "Projects/Aurum/completion-plan.json",
            "Projects/Aurum/future-branches.json",
            "Projects/Aurum/next-interaction-packet.json",
        )
        for token in required:
            self.assertIn(token, workflow)

    def test_integrity_receipt_race_cannot_mask_validator_result(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = (
            root / ".github" / "workflows" / "repository-integrity.yml"
        ).read_text(encoding="utf-8")

        required = (
            'validated_head="$(git rev-parse HEAD)"',
            "if git push origin HEAD:main; then",
            "unchanged_after_race=true",
            "deferred_reason=main-advanced",
            "deferred_reason=publication-failed",
            "steps.validate.outputs.rc",
        )
        for token in required:
            self.assertIn(token, workflow)

        self.assertNotIn("git pull --rebase origin main", workflow)
        publication = workflow.index("Publish changed diagnostic receipt")
        enforcement = workflow.index("Enforce validator result")
        self.assertLess(publication, enforcement)

    def test_completion_state_sync_reprojects_instead_of_rebasing_stale_state(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = (
            root / ".github" / "workflows" / "aurum-completion-plan-sync.yml"
        ).read_text(encoding="utf-8")

        required = (
            "for attempt in 1 2 3",
            'projected_head="$(git rev-parse HEAD)"',
            "if git push origin HEAD:main; then",
            "converged_after_race=true",
            "retrying_reason=main-advanced",
            "git checkout --detach origin/main",
            "project_latest_state",
            "waiting_reason=main-advanced retry_exhausted=true",
            "deferred_reason=publication-failed",
        )
        for token in required:
            self.assertIn(token, workflow)

        self.assertNotIn("git pull --rebase origin main", workflow)
        retry_checkout = workflow.index("git checkout --detach origin/main")
        retry_projection = workflow.rindex("project_latest_state")
        self.assertLess(retry_checkout, retry_projection)


if __name__ == "__main__":
    unittest.main()
