"""Regression checks for the BoxBrain repository validator."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Admin.validate_repository import repository_markdown_files


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


if __name__ == "__main__":
    unittest.main()
