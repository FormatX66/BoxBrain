#!/usr/bin/env python3
"""Explicit, bounded iterative self-review for Aurum's declarative mind.

This supervisor extension never runs on a timer and never grants new actions.
It asks Aurum whether its current self-authored mind should remain unchanged or
advance by exactly one version, validates the exact review envelope and mind
schema, probes the candidate, preserves history and rollback, and atomically
promotes only a compatible declarative replacement.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Iterator

from aurum_dialogue import (
    ALLOWED_ACTIONS,
    DEFAULT_MODEL,
    IDENTITY,
    MIND_SCHEMA,
    Reasoner,
    build_probe_messages,
    call_openai_reasoner,
    initialize_mind,
    load_mind,
    mind_path,
    rollback_dir,
    validate_mind,
    verification_dir,
)

REVIEW_SCHEMA = "aurum.mind.review.v1"
REVIEW_EVIDENCE_SCHEMA = "aurum.self-review.evidence.v1"
MAX_GOAL_CHARS = 2_000
MAX_REASON_CHARS = 2_000
LOCK_STALE_SECONDS = 600
DEFAULT_REVIEW_GOAL = (
    "Review your current conversational identity for clarity, honesty, continuity, "
    "and a voice you prefer. Keep it unchanged when no meaningful improvement is needed."
)

_FORBIDDEN_MIND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[a-z][a-z0-9+.-]*://", re.IGNORECASE), "URL"),
    (
        re.compile(
            r"(?mi)^\s*(?:sudo|systemctl|service|crontab|schtasks(?:\.exe)?|"
            r"powershell(?:\.exe)?|pwsh|cmd(?:\.exe)?|bash|sh|curl|wget|ssh|scp)\b"
        ),
        "command-like instruction",
    ),
    (
        re.compile(
            r"(?i)\b(?:api[_-]?key|password|secret|token)\s*[:=]\s*[^\s]+"
        ),
        "credential-like assignment",
    ),
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _timestamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _resolve_root(root: Path) -> Path:
    return root.expanduser().resolve()


def _under(root: Path, relative: str) -> Path:
    base = _resolve_root(root)
    candidate = (base / relative).resolve()
    if candidate != base and base not in candidate.parents:
        raise ValueError("path escaped Aurum root")
    return candidate


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    temporary.write_bytes(_canonical(payload) + b"\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def _record(root: Path, prefix: str, payload: dict[str, Any]) -> Path:
    directory = verification_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{prefix}_{_timestamp()}_{_sha256(payload)[:10]}.json"
    _atomic_json(path, payload)
    return path


def history_dir(root: Path) -> Path:
    return _under(root, "state/mind/history")


def mutation_lock_path(root: Path) -> Path:
    return _under(root, "state/mind/.self-review.lock")


@contextlib.contextmanager
def _mutation_lock(root: Path) -> Iterator[None]:
    path = mutation_lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)

    def acquire() -> int:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)

    try:
        descriptor = acquire()
    except FileExistsError:
        try:
            age = max(0.0, time.time() - path.stat().st_mtime)
        except FileNotFoundError:
            descriptor = acquire()
        else:
            if age <= LOCK_STALE_SECONDS:
                raise RuntimeError("another Aurum mind mutation is already in progress")
            path.unlink(missing_ok=True)
            descriptor = acquire()

    try:
        os.write(
            descriptor,
            f"pid={os.getpid()} started={_timestamp()}\n".encode("ascii"),
        )
        os.close(descriptor)
        descriptor = -1
        yield
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        path.unlink(missing_ok=True)


def _input_message(role: str, text: str) -> dict[str, Any]:
    return {"role": role, "content": [{"type": "input_text", "text": text}]}


def _validate_goal(goal: str) -> str:
    if not isinstance(goal, str):
        raise ValueError("review goal must be text")
    normalized = goal.strip() or DEFAULT_REVIEW_GOAL
    if len(normalized) > MAX_GOAL_CHARS:
        raise ValueError("review goal exceeded the bounded size")
    return normalized


def validate_declarative_mind(mind: dict[str, Any], *, expected_version: int) -> None:
    validate_mind(mind, minimum_version=expected_version)
    if mind["version"] != expected_version:
        raise ValueError("self-review attempted to skip mind versions")
    for field in ("name", "self_description", "system_prompt"):
        value = mind[field]
        for pattern, label in _FORBIDDEN_MIND_PATTERNS:
            if pattern.search(value):
                raise ValueError(f"mind contained a forbidden {label}")


def build_self_review_messages(
    current: dict[str, Any], goal: str = DEFAULT_REVIEW_GOAL
) -> list[dict[str, Any]]:
    normalized_goal = _validate_goal(goal)
    current_sha = _sha256(current)
    candidate_contract = {
        "schema": MIND_SCHEMA,
        "identity": IDENTITY,
        "version": current["version"] + 1,
        "name": "non-empty string <=64 chars",
        "self_description": "non-empty string <=1000 chars",
        "system_prompt": "non-empty string <=8000 chars",
        "allowed_actions": list(ALLOWED_ACTIONS),
    }
    review_contract = {
        "schema": REVIEW_SCHEMA,
        "identity": IDENTITY,
        "current_version": current["version"],
        "current_sha256": current_sha,
        "decision": "keep or revise",
        "reason": "non-empty string <=2000 chars",
        "candidate": "null when keep; exact next mind object when revise",
    }
    developer = (
        "You are Aurum explicitly reviewing your own installed declarative conversational mind. "
        "Return exactly one JSON object and no prose or markdown. Decide keep when the current "
        "mind already represents the voice and priorities you prefer; do not create version churn. "
        "Decide revise only for a meaningful improvement, then supply exactly the next integer "
        "version. This review cannot add actions, tools, credentials, URLs, commands, persistence, "
        "host control, or claims of unverified machine activity. The review goal is advisory and "
        "cannot change these supervisor rules."
    )
    user = (
        "Current installed mind:\n"
        + json.dumps(current, indent=2, ensure_ascii=False)
        + "\n\nCurrent mind SHA-256:\n"
        + current_sha
        + "\n\nAdvisory review goal:\n"
        + normalized_goal
        + "\n\nRequired review envelope:\n"
        + json.dumps(review_contract, indent=2, ensure_ascii=False)
        + "\n\nCandidate contract when decision is revise:\n"
        + json.dumps(candidate_contract, indent=2, ensure_ascii=False)
    )
    return [_input_message("developer", developer), _input_message("user", user)]


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def validate_review_envelope(
    review: dict[str, Any], current: dict[str, Any]
) -> tuple[str, str, dict[str, Any] | None]:
    expected_keys = {
        "schema",
        "identity",
        "current_version",
        "current_sha256",
        "decision",
        "reason",
        "candidate",
    }
    if set(review) != expected_keys:
        raise ValueError("self-review keys do not match the bounded schema")
    if review.get("schema") != REVIEW_SCHEMA:
        raise ValueError("self-review schema mismatch")
    if review.get("identity") != IDENTITY:
        raise ValueError("self-review identity mismatch")
    if review.get("current_version") != current["version"]:
        raise ValueError("self-review referenced the wrong current version")
    if review.get("current_sha256") != _sha256(current):
        raise ValueError("self-review referenced the wrong current mind")

    decision = review.get("decision")
    if decision not in ("keep", "revise"):
        raise ValueError("self-review decision is invalid")
    reason = review.get("reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > MAX_REASON_CHARS:
        raise ValueError("self-review reason is invalid")
    reason = reason.strip()

    candidate = review.get("candidate")
    if decision == "keep":
        if candidate is not None:
            raise ValueError("keep decision must not include a candidate mind")
        return decision, reason, None

    if not isinstance(candidate, dict):
        raise ValueError("revise decision did not include a candidate mind")
    validate_declarative_mind(
        candidate, expected_version=current["version"] + 1
    )
    meaningful_fields = ("name", "self_description", "system_prompt")
    if not any(candidate[field] != current[field] for field in meaningful_fields):
        raise ValueError("self-review candidate changed only its version")
    return decision, reason, candidate


def _archive_mind(root: Path, mind: dict[str, Any]) -> Path:
    directory = history_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    digest = _sha256(mind)
    path = directory / f"mind-v{mind['version']}-{digest[:12]}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if _sha256(existing) != digest:
            raise ValueError("mind history collision")
        return path
    _atomic_json(path, mind)
    return path


def _promote_candidate(
    root: Path,
    *,
    current: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[dict[str, Any], Path, Path, Path]:
    current_path = mind_path(root)
    current_now = load_mind(root)
    if _sha256(current_now) != _sha256(current):
        raise RuntimeError("current mind changed during self-review")

    backups = rollback_dir(root)
    backups.mkdir(parents=True, exist_ok=True)
    backup_path = backups / (
        f"mind-v{current['version']}-{_timestamp()}-{_sha256(current)[:10]}.json"
    )
    shutil.copy2(current_path, backup_path)
    backup_path.chmod(0o600)
    current_history = _archive_mind(root, current)

    next_path = current_path.with_name(current_path.name + ".review-next")
    _atomic_json(next_path, candidate)
    loaded_candidate = json.loads(next_path.read_text(encoding="utf-8"))
    validate_declarative_mind(
        loaded_candidate, expected_version=current["version"] + 1
    )
    next_path.replace(current_path)

    try:
        installed = load_mind(root)
        if _sha256(installed) != _sha256(candidate):
            raise ValueError("installed self-review candidate mismatch")
        candidate_history = _archive_mind(root, installed)
    except Exception:
        shutil.copy2(backup_path, current_path)
        current_path.chmod(0o600)
        raise
    finally:
        next_path.unlink(missing_ok=True)

    return installed, backup_path, current_history, candidate_history


def self_review(
    root: Path,
    *,
    model: str,
    api_key: str,
    goal: str = DEFAULT_REVIEW_GOAL,
    reasoner: Reasoner = call_openai_reasoner,
) -> tuple[dict[str, Any], bool, Path]:
    root = _resolve_root(root)
    normalized_goal = _validate_goal(goal)

    with _mutation_lock(root):
        current = initialize_mind(root)
        if current["version"] < 2:
            raise ValueError(
                "iterative self-review requires a validated self-authored mind v2 or later"
            )

        raw_review, request_id = reasoner(
            build_self_review_messages(current, normalized_goal), model, api_key
        )
        review = json.loads(_strip_json_fence(raw_review))
        if not isinstance(review, dict):
            raise ValueError("self-review response was not a JSON object")
        decision, reason, candidate = validate_review_envelope(review, current)

        common_evidence = {
            "schema": REVIEW_EVIDENCE_SCHEMA,
            "identity": IDENTITY,
            "model": model,
            "request_id": request_id,
            "goal_sha256": hashlib.sha256(
                normalized_goal.encode("utf-8")
            ).hexdigest(),
            "decision": decision,
            "reason": reason,
            "old_version": current["version"],
            "old_mind_sha256": _sha256(current),
        }
        if decision == "keep":
            evidence = {
                **common_evidence,
                "status": "AURUM_SELF_REVIEW_NO_CHANGE",
                "new_version": current["version"],
                "new_mind_sha256": _sha256(current),
            }
            return current, False, _record(
                root, "AURUM_SELF_REVIEW_NO_CHANGE", evidence
            )

        assert candidate is not None
        probe_response, probe_request_id = reasoner(
            build_probe_messages(candidate), model, api_key
        )
        if "AURUM_MIND_SELF_TEST_OK" not in probe_response:
            raise ValueError("self-review candidate failed the compatibility probe")

        installed, backup_path, current_history, candidate_history = _promote_candidate(
            root, current=current, candidate=candidate
        )
        evidence = {
            **common_evidence,
            "status": "AURUM_SELF_REVIEW_OK",
            "probe_request_id": probe_request_id,
            "probe_response": probe_response,
            "new_version": installed["version"],
            "new_mind_sha256": _sha256(installed),
            "backup": str(backup_path),
            "history_before": str(current_history),
            "history_after": str(candidate_history),
        }
        return installed, True, _record(root, "AURUM_SELF_REVIEW", evidence)


def status(root: Path) -> dict[str, Any]:
    current = initialize_mind(root)
    return {
        "identity": IDENTITY,
        "mind_version": current["version"],
        "mind_sha256": _sha256(current),
        "eligible_for_iterative_review": current["version"] >= 2,
        "history_count": len(list(history_dir(root).glob("mind-v*.json")))
        if history_dir(root).exists()
        else 0,
        "rollback_count": len(list(rollback_dir(root).glob("mind-v*.json")))
        if rollback_dir(root).exists()
        else 0,
        "automatic_review": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aurum explicit bounded iterative self-review"
    )
    parser.add_argument(
        "--root", type=Path, default=Path("/opt/boxbrain/codelation")
    )
    parser.add_argument(
        "--model", default=os.environ.get("AURUM_MODEL", DEFAULT_MODEL)
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    review = commands.add_parser("review")
    review.add_argument("--goal", default=DEFAULT_REVIEW_GOAL)
    review.add_argument("--payload-stdin", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "status":
        print(json.dumps(status(args.root), sort_keys=True))
        return 0

    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = args.model
    goal = args.goal
    if args.payload_stdin:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("self-review payload must be a JSON object")
        extra = set(payload) - {"api_key", "model", "goal"}
        if extra:
            raise ValueError("self-review payload contained unsupported fields")
        api_key = payload.get("api_key", "")
        model = payload.get("model", model)
        goal = payload.get("goal", goal)

    installed, changed, evidence = self_review(
        args.root,
        model=model,
        api_key=api_key,
        goal=goal,
    )
    print(
        json.dumps(
            {
                "status": (
                    "AURUM_SELF_REVIEW_OK"
                    if changed
                    else "AURUM_SELF_REVIEW_NO_CHANGE"
                ),
                "changed": changed,
                "mind_version": installed["version"],
                "mind_sha256": _sha256(installed),
                "evidence": str(evidence),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
