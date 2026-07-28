"""Read-only access to computers that authorized a BoxBrain SSH link."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_links(state_directory: str) -> list[dict[str, Any]]:
    links_directory = Path(state_directory) / "links"
    links: list[dict[str, Any]] = []
    try:
        paths = sorted(links_directory.glob("*.json"))
    except OSError:
        return links

    for path in paths:
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(item, dict):
            links.append(item)
    return links
