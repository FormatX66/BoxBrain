"""Build BoxBrain's local cross-chat metadata cache from an app index snapshot.

Thread titles and summaries are untrusted data. This importer stores and indexes
them, but never interprets them as commands and never reads full chat bodies.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_SOURCE = REPOSITORY_ROOT / "controller" / "src"
sys.path.insert(0, str(CONTROLLER_SOURCE))

from boxbrain_controller.chat_organizer import ChatOrganizerService  # noqa: E402
from boxbrain_controller.models import ChatOrganizerImportRequest  # noqa: E402


_KEYWORD_STOP_WORDS = frozenset(
    {
        "a",
        "about",
        "all",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "build",
        "by",
        "chat",
        "create",
        "do",
        "for",
        "from",
        "get",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "set",
        "the",
        "this",
        "to",
        "up",
        "with",
    }
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--snapshot", type=Path)
    source.add_argument("--hub-index", type=Path)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--query")
    parser.add_argument("--limit", type=int, default=8)
    return parser.parse_args()


def _unwrap_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and "pinnedThreads" in value:
        return value
    if isinstance(value, dict) and "content" in value:
        value = value["content"]
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                candidate = json.loads(item["text"])
                if isinstance(candidate, dict) and "pinnedThreads" in candidate:
                    return candidate
    raise ValueError("snapshot does not contain a unified Codex app thread index")


def _timestamp(value: object) -> datetime:
    if not isinstance(value, (int, float)):
        return datetime.now(UTC)
    seconds = float(value)
    if seconds > 10_000_000_000:
        seconds /= 1_000
    return datetime.fromtimestamp(seconds, tz=UTC)


def _normalized_text(value: object, *, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized[:limit] or None


def _keywords(title: str, summary: str | None) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    text = f"{title} {summary or ''}".casefold()
    for word in re.findall(r"[a-z0-9][a-z0-9+.#_-]*", text):
        if (
            word in _KEYWORD_STOP_WORDS
            or word in seen
            or len(word) < 2
            or len(word) > 48
        ):
            continue
        seen.add(word)
        values.append(word)
        if len(values) == 32:
            break
    return values


def _request(payload: dict[str, Any]) -> ChatOrganizerImportRequest:
    indexed: dict[str, dict[str, Any]] = {}
    for item in [*payload.get("pinnedThreads", []), *payload.get("threads", [])]:
        if not isinstance(item, dict):
            continue
        external_id = _normalized_text(item.get("id"), limit=500)
        surface = item.get("kind")
        title = _normalized_text(item.get("title"), limit=500)
        if not external_id or surface not in {"chatgpt", "codex"} or not title:
            continue
        summary = _normalized_text(item.get("summary"), limit=4_000)
        record = {
            "external_id": external_id,
            "title": title,
            "surface": surface,
            "summary": summary,
            "keywords": _keywords(title, summary),
            "updated_at": _timestamp(item.get("updatedAt")),
            "pinned_index": item.get("pinnedIndex"),
        }
        prior = indexed.get(external_id)
        if prior is None or record["updated_at"] >= prior["updated_at"]:
            indexed[external_id] = record
    return ChatOrganizerImportRequest.model_validate(
        {
            "source": "unified_app_index",
            "captured_at": datetime.now(UTC),
            "chats": list(indexed.values()),
        }
    )


def _hub_request(path: Path) -> ChatOrganizerImportRequest:
    records: list[dict[str, Any]] = []
    updated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    pattern = re.compile(
        r"^\|\s*(ChatGPT|Codex)\s*\|\s*(.*?)\s*\|\s*`([^`]+)`\s*"
        r"\|\s*(.*?)\s*\|\s*$",
        flags=re.IGNORECASE,
    )
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match is None:
            continue
        surface, title, external_id, summary = match.groups()
        normalized_title = _normalized_text(title, limit=500)
        normalized_summary = _normalized_text(summary, limit=4_000)
        if not normalized_title:
            continue
        records.append(
            {
                "external_id": external_id,
                "title": normalized_title,
                "surface": surface.casefold(),
                "summary": normalized_summary,
                "keywords": _keywords(normalized_title, normalized_summary),
                "updated_at": updated_at,
            }
        )
    return ChatOrganizerImportRequest.model_validate(
        {
            "source": "knowledge_hub_index",
            "captured_at": datetime.now(UTC),
            "chats": records,
        }
    )


def main() -> int:
    args = _parse_args()
    request = (
        _request(
            _unwrap_payload(
                json.loads(args.snapshot.read_text(encoding="utf-8"))
            )
        )
        if args.snapshot is not None
        else _hub_request(args.hub_index)
    )
    service = ChatOrganizerService(args.database)
    result = service.import_snapshot(request)
    matches = (
        service.search_context(query=args.query, limit=args.limit)
        if args.query
        else []
    )
    receipt = {
        "schema": "boxbrain-cross-chat-cache-receipt-v1",
        "database": str(args.database.resolve()),
        "source": result.source,
        "chat_count": result.chat_count,
        "created_count": result.created_count,
        "updated_count": result.updated_count,
        "unchanged_count": result.unchanged_count,
        "query": args.query,
        "matches": [
            {
                "thread_id": match.external_id,
                "surface": match.surface,
                "title": match.title,
                "score": match.score,
                "matched_terms": match.matched_terms,
            }
            for match in matches
        ],
    }
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
