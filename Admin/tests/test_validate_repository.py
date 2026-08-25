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

    def test_retired_pc01_flash_workflow_cannot_regain_persistent_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workflow = root / ".github" / "workflows" / "aurum-pc01-flash-authorized.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text(
                "on:\n"
                "  workflow_run:\n"
                "env:\n"
                "  AURUM_FLASH_AUTHORIZATION: old-static-authority\n"
                "jobs:\n"
                "  flash:\n"
                "    steps:\n"
                "      - run: echo \\\\.\\PhysicalDrive1 && diskpart.exe\n",
                encoding="utf-8",
            )

            errors = destructive_workflow_policy_errors(root)
            self.assertGreaterEqual(len(errors), 4)
            self.assertTrue(any("workflow_run:" in error for error in errors))
            self.assertTrue(any("AURUM_FLASH_AUTHORIZATION:" in error for error in errors))

    def test_retired_pc01_flash_tombstone_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workflow = root / ".github" / "workflows" / "aurum-pc01-flash-authorized.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text(
                "name: retired\n"
                "on:\n"
                "  workflow_dispatch:\n"
                "jobs:\n"
                "  retired:\n"
                "    steps:\n"
                "      - run: exit 1\n",
                encoding="utf-8",
            )

            self.assertEqual(destructive_workflow_policy_errors(root), [])


if __name__ == "__main__":
    unittest.main()