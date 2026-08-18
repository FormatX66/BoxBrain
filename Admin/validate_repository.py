"""Validate the canonical BoxBrain repository structure and Markdown links."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
PROJECTS = (
    "Aurum",
    "AurumBridge",
    "BrainConnect",
    "WebsiteBuilder",
    "Arkmatx",
    "AgentFramework",
    "WebsiteCluster",
    "Automation",
    "Security",
    "Research",
    "Codelation",
)
AGENTS = (
    "Architect",
    "Engineer",
    "Librarian",
    "KnowledgeManager",
    "Executor",
    "Reviewer",
    "Scout",
    "Quartermaster",
    "Security",
    "Media",
)
SESSION_FILES = (
    "HumanHandoff.md",
    "AgentHandoff.md",
    "DecisionLog.md",
    "ChangeLog.md",
    "ProjectUpdates.md",
    "Questions.md",
    "Ideas.md",
    "VerificationChecklist.md",
    "ExecutionPlan.md",
)
REQUIRED_FILES = (
    "README.md",
    "Admin/RepositoryIndex.md",
    "Admin/Roadmap.md",
    "Admin/MasterTODO.md",
    "Admin/Decisions.md",
    "Admin/ChangeLog.md",
    "Admin/SessionIndex.md",
    "Architecture/SystemArchitecture.md",
    "Architecture/AgentArchitecture.md",
    "Architecture/DataFlow.md",
    "Architecture/Integrations.md",
    "Projects/README.md",
    "Agents/README.md",
    "PromptLibrary/README.md",
    "PromptLibrary/RepositoryOrganization.md",
    "Templates/README.md",
    "SessionHandoffs/README.md",
    "Archive/README.md",
)
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
SESSION_DIRECTORY_PATTERN = re.compile(
    r"^BB-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{3}$"
)
IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".dart_tool",
        ".git",
        ".idea",
        ".mypy_cache",
        ".pytest_cache",
        ".pub",
        ".pub-cache",
        ".ruff_cache",
        ".venv",
        ".vscode",
        "__pycache__",
        "artifacts",
        "build",
        "captures",
        "coverage",
        "data",
        "dist",
        "logs",
        "venv",
    }
)
# Operational GitHub templates are discovered by GitHub rather than by the
# documentation graph, so requiring an artificial inbound documentation link
# creates a false repository-integrity failure.
IGNORED_FILE_NAMES = frozenset({"AGENTS.md", "pull_request_template.md"})


def repository_markdown_files(root: Path = ROOT) -> list[Path]:
    """Return project Markdown while excluding generated and ignored trees."""
    return sorted(
        path
        for path in root.rglob("*.md")
        if path.name not in IGNORED_FILE_NAMES
        if not any(
            part in IGNORED_DIRECTORY_NAMES
            for part in path.relative_to(root).parts[:-1]
        )
    )


def local_link_target(document: Path, raw_target: str) -> Path | None:
    target = raw_target.strip().strip("<>")
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    path_text = unquote(target.split("#", 1)[0])
    if not path_text:
        return None
    return (document.parent / path_text).resolve()


def main() -> int:
    errors: list[str] = []
    required = list(REQUIRED_FILES)
    required.extend(f"Projects/{project}/ProjectIndex.md" for project in PROJECTS)
    required.extend(f"Agents/{agent}/Role.md" for agent in AGENTS)
    session_directories = sorted(
        path
        for path in (ROOT / "SessionHandoffs").iterdir()
        if path.is_dir()
        and SESSION_DIRECTORY_PATTERN.fullmatch(path.name)
    )
    if not session_directories:
        errors.append("No session handoff directories found")
    for session_directory in session_directories:
        required.extend(
            f"SessionHandoffs/{session_directory.name}/{filename}"
            for filename in SESSION_FILES
        )

    for relative_path in required:
        if not (ROOT / relative_path).is_file():
            errors.append(f"Missing required file: {relative_path}")

    markdown_files = repository_markdown_files()
    linked_files: set[Path] = set()
    for document in markdown_files:
        text = document.read_text(encoding="utf-8")
        for raw_target in LINK_PATTERN.findall(text):
            target = local_link_target(document, raw_target)
            if target is None:
                continue
            if not target.exists():
                errors.append(
                    f"Broken link in {document.relative_to(ROOT)}: {raw_target}"
                )
            elif target.is_file() and ROOT in target.parents:
                linked_files.add(target)

    root_readme = (ROOT / "README.md").resolve()
    for document in markdown_files:
        resolved = document.resolve()
        if resolved != root_readme and resolved not in linked_files:
            errors.append(f"Orphan Markdown file: {document.relative_to(ROOT)}")

    if errors:
        print("BoxBrain validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "BoxBrain validation passed: "
        f"{len(required)} required files and {len(markdown_files)} Markdown files."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
