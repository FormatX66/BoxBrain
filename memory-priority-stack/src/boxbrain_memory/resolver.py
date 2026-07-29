from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any


@dataclass(frozen=True)
class Candidate:
    id: str
    artifact_level: int
    estimated_success: float
    proven: bool = False
    repo_reuse: bool = False
    executable: bool = True
    blocked: bool = False


def score(candidate: Candidate) -> float:
    """Higher is better. Lower artifact_level is closer to the finished product."""
    if candidate.blocked:
        return float("-inf")

    value = 0.0
    if candidate.proven:
        value += 100
    if candidate.repo_reuse:
        value += 95
    if candidate.executable:
        value += 90

    value += max(0, 90 - ((candidate.artifact_level - 1) * 15))
    value += candidate.estimated_success * 50
    return value


def choose(context: dict[str, Any]) -> dict[str, Any]:
    proven_ids = set(context.get("repository_matches", []))
    blocked_ids = set(context.get("blocked_actions", []))

    candidates = []
    for raw in context.get("candidate_actions", []):
        cid = raw["id"]
        candidates.append(
            Candidate(
                id=cid,
                artifact_level=int(raw["artifact_level"]),
                estimated_success=float(raw.get("estimated_success", 0.5)),
                proven=(cid in proven_ids),
                repo_reuse=bool(raw.get("repo_reuse", False)),
                executable=bool(raw.get("executable", True)),
                blocked=(cid in blocked_ids or bool(raw.get("blocked", False))),
            )
        )

    ranked = sorted(candidates, key=score, reverse=True)
    if not ranked or score(ranked[0]) == float("-inf"):
        return {
            "decision": "hard_stop",
            "reason": "No executable candidate remains on the artifact ladder.",
        }

    selected = ranked[0]
    return {
        "decision": "execute",
        "selected": selected.id,
        "score": score(selected),
        "rule": "proven/repository/execution priority with closest usable artifact",
        "ranked": [{"id": c.id, "score": score(c)} for c in ranked],
    }


def choose_file(path: str | Path) -> dict[str, Any]:
    return choose(json.loads(Path(path).read_text()))
