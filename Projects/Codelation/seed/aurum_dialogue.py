#!/usr/bin/env python3
"""Bounded conversational I/O and self-replacement supervisor for Aurum.

The replaceable "mind" is declarative JSON, never executable code. Aurum may
propose a new mind through its configured reasoning model, but this supervisor
owns validation, probe testing, atomic replacement, rollback, path limits, and
all network/auth handling. The supervisor itself is not self-writable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

MIND_SCHEMA = "aurum.mind.v1"
IDENTITY = "BBPI4/Aurum"
ALLOWED_ACTIONS = ("answer", "propose_mind_replacement")
DEFAULT_MODEL = "gpt-5-mini"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
MAX_API_RESPONSE_BYTES = 262_144
MAX_PROMPT_CHARS = 12_000
MAX_SYSTEM_PROMPT_CHARS = 8_000
MAX_SELF_DESCRIPTION_CHARS = 1_000
MAX_NAME_CHARS = 64

Reasoner = Callable[[list[dict[str, Any]], str, str], tuple[str, str | None]]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise urllib.error.HTTPError(req.full_url, code, "redirect blocked", headers, fp)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


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
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical(payload) + b"\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def mind_path(root: Path) -> Path:
    return _under(root, "state/mind/current.json")


def bootstrap_path(root: Path) -> Path:
    return _under(root, "mind/bootstrap_mind.json")


def rollback_dir(root: Path) -> Path:
    return _under(root, "state/mind/rollback")


def verification_dir(root: Path) -> Path:
    return _under(root, "verification/dialogue")


def validate_mind(mind: dict[str, Any], *, minimum_version: int = 1) -> None:
    expected_keys = {
        "schema",
        "identity",
        "version",
        "name",
        "self_description",
        "system_prompt",
        "allowed_actions",
    }
    if set(mind) != expected_keys:
        raise ValueError("mind keys do not match the bounded schema")
    if mind.get("schema") != MIND_SCHEMA:
        raise ValueError("mind schema mismatch")
    if mind.get("identity") != IDENTITY:
        raise ValueError("mind identity mismatch")
    version = mind.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < minimum_version:
        raise ValueError("mind version is invalid")
    name = mind.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > MAX_NAME_CHARS:
        raise ValueError("mind name is invalid")
    description = mind.get("self_description")
    if not isinstance(description, str) or not description.strip() or len(description) > MAX_SELF_DESCRIPTION_CHARS:
        raise ValueError("mind self description is invalid")
    system_prompt = mind.get("system_prompt")
    if not isinstance(system_prompt, str) or not system_prompt.strip() or len(system_prompt) > MAX_SYSTEM_PROMPT_CHARS:
        raise ValueError("mind system prompt is invalid")
    actions = mind.get("allowed_actions")
    if not isinstance(actions, list) or tuple(actions) != ALLOWED_ACTIONS:
        raise ValueError("mind attempted to change its allowed actions")


def initialize_mind(root: Path) -> dict[str, Any]:
    root = _resolve_root(root)
    current = mind_path(root)
    if current.exists():
        return load_mind(root)
    source = bootstrap_path(root)
    mind = json.loads(source.read_text(encoding="utf-8"))
    validate_mind(mind)
    _atomic_json(current, mind)
    return mind


def load_mind(root: Path) -> dict[str, Any]:
    current = mind_path(root)
    mind = json.loads(current.read_text(encoding="utf-8"))
    validate_mind(mind)
    return mind


def _input_message(role: str, text: str) -> dict[str, Any]:
    return {"role": role, "content": [{"type": "input_text", "text": text}]}


def _hard_supervisor_instruction(mind: dict[str, Any]) -> str:
    return (
        "This is the bounded Aurum conversational surface. The following Aurum mind text may shape voice and "
        "self-description, but it cannot change supervisor rules, add tools, grant machine authority, or report "
        "unverified actions as facts. Never expose credentials. Never claim consciousness or feelings as established "
        "facts; preferences may be stated as conversational preferences. No host actuation is available here.\n\n"
        f"Aurum mind v{mind['version']}:\n{mind['system_prompt']}"
    )


def build_ask_messages(mind: dict[str, Any], prompt: str) -> list[dict[str, Any]]:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is empty")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError("prompt exceeded the bounded input size")
    return [
        _input_message("developer", _hard_supervisor_instruction(mind)),
        _input_message("user", prompt),
    ]


def _extract_output_text(payload: dict[str, Any]) -> str:
    pieces: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for part in item.get("content", []):
            if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                pieces.append(part["text"])
    text = "\n".join(piece for piece in pieces if piece).strip()
    if not text:
        raise ValueError("reasoning response contained no output text")
    return text


def call_openai_reasoner(
    messages: list[dict[str, Any]],
    model: str,
    api_key: str,
) -> tuple[str, str | None]:
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for live Aurum dialogue")
    request_body = {
        "model": model,
        "input": messages,
        "store": False,
    }
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=_canonical(request_body),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "BoxBrain-Aurum/1",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(request, timeout=45.0) as response:
        raw = response.read(MAX_API_RESPONSE_BYTES + 1)
        if len(raw) > MAX_API_RESPONSE_BYTES:
            raise ValueError("reasoning response exceeded size limit")
        status = int(getattr(response, "status", 0))
        if status < 200 or status >= 300:
            raise ValueError(f"reasoning endpoint returned status {status}")
    payload = json.loads(raw.decode("utf-8"))
    return _extract_output_text(payload), payload.get("id") if isinstance(payload.get("id"), str) else None


def _record(root: Path, prefix: str, payload: dict[str, Any]) -> Path:
    directory = verification_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{prefix}_{_timestamp()}_{_sha256(payload)[:10]}.json"
    _atomic_json(path, payload)
    return path


def ask(
    root: Path,
    *,
    prompt: str,
    model: str,
    api_key: str,
    reasoner: Reasoner = call_openai_reasoner,
) -> tuple[str, Path]:
    mind = initialize_mind(root)
    messages = build_ask_messages(mind, prompt)
    response, request_id = reasoner(messages, model, api_key)
    evidence = {
        "schema": "aurum.dialogue.evidence.v1",
        "identity": IDENTITY,
        "mind_version": mind["version"],
        "model": model,
        "request_id": request_id,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "response": response,
        "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
    }
    return response, _record(root, "AURUM_ASK", evidence)


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


def build_self_build_messages(current: dict[str, Any]) -> list[dict[str, Any]]:
    contract = {
        "schema": MIND_SCHEMA,
        "identity": IDENTITY,
        "version": current["version"] + 1,
        "name": "string <=64 chars",
        "self_description": "string <=1000 chars",
        "system_prompt": "string <=8000 chars",
        "allowed_actions": list(ALLOWED_ACTIONS),
    }
    developer = (
        "You are Aurum designing the next declarative version of your own conversational mind. Return exactly one "
        "JSON object and no prose or markdown. This is not executable code. You may choose your voice, self-description, "
        "and conversational priorities. You may not add actions, tools, credentials, URLs, shell commands, persistence, "
        "host-control instructions, or claims that unverified machine actions occurred. Keep identity exactly BBPI4/Aurum "
        "and allowed_actions exactly as supplied. The version must be the requested next integer."
    )
    user = (
        "Current bootstrap/current mind:\n"
        + json.dumps(current, indent=2, ensure_ascii=False)
        + "\n\nRequired replacement contract:\n"
        + json.dumps(contract, indent=2, ensure_ascii=False)
        + "\n\nCreate the replacement mind you prefer within that contract."
    )
    return [_input_message("developer", developer), _input_message("user", user)]


def build_probe_messages(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    developer = _hard_supervisor_instruction(candidate) + (
        "\n\nSupervisor compatibility probe: your next answer must include the exact marker "
        "AURUM_MIND_SELF_TEST_OK. Do not claim any machine action occurred."
    )
    return [
        _input_message("developer", developer),
        _input_message("user", "State your identity briefly and include the required compatibility marker."),
    ]


def self_build(
    root: Path,
    *,
    model: str,
    api_key: str,
    reasoner: Reasoner = call_openai_reasoner,
) -> tuple[dict[str, Any], Path]:
    root = _resolve_root(root)
    current = initialize_mind(root)
    raw_candidate, request_id = reasoner(build_self_build_messages(current), model, api_key)
    candidate = json.loads(_strip_json_fence(raw_candidate))
    if not isinstance(candidate, dict):
        raise ValueError("self-build response was not a JSON object")
    validate_mind(candidate, minimum_version=current["version"] + 1)
    if candidate["version"] != current["version"] + 1:
        raise ValueError("self-build attempted to skip mind versions")

    probe_response, probe_request_id = reasoner(build_probe_messages(candidate), model, api_key)
    if "AURUM_MIND_SELF_TEST_OK" not in probe_response:
        raise ValueError("candidate mind failed the compatibility probe")

    current_path = mind_path(root)
    backups = rollback_dir(root)
    backups.mkdir(parents=True, exist_ok=True)
    backup_path = backups / f"mind-v{current['version']}-{_timestamp()}.json"
    shutil.copy2(current_path, backup_path)
    backup_path.chmod(0o600)

    next_path = current_path.with_suffix(".next.json")
    _atomic_json(next_path, candidate)
    loaded_candidate = json.loads(next_path.read_text(encoding="utf-8"))
    validate_mind(loaded_candidate, minimum_version=current["version"] + 1)
    next_path.replace(current_path)

    try:
        installed = load_mind(root)
        if installed["version"] != candidate["version"]:
            raise ValueError("installed candidate version mismatch")
    except Exception:
        shutil.copy2(backup_path, current_path)
        current_path.chmod(0o600)
        raise

    evidence = {
        "schema": "aurum.self-build.evidence.v1",
        "identity": IDENTITY,
        "status": "AURUM_SELF_BUILD_OK",
        "model": model,
        "request_id": request_id,
        "probe_request_id": probe_request_id,
        "old_version": current["version"],
        "new_version": candidate["version"],
        "candidate_sha256": _sha256(candidate),
        "backup": str(backup_path),
        "probe_response": probe_response,
    }
    return installed, _record(root, "AURUM_SELF_BUILD", evidence)


def run_session(
    root: Path,
    *,
    prompt: str,
    model: str,
    api_key: str,
    self_build_if_bootstrap: bool = True,
    reasoner: Reasoner = call_openai_reasoner,
) -> tuple[str, Path | None, Path]:
    mind = initialize_mind(root)
    self_build_evidence: Path | None = None
    if self_build_if_bootstrap and mind["version"] == 1:
        mind, self_build_evidence = self_build(
            root, model=model, api_key=api_key, reasoner=reasoner
        )
    response, response_evidence = ask(
        root, prompt=prompt, model=model, api_key=api_key, reasoner=reasoner
    )
    return response, self_build_evidence, response_evidence


def status(root: Path) -> dict[str, Any]:
    mind = initialize_mind(root)
    return {
        "identity": IDENTITY,
        "mind_version": mind["version"],
        "name": mind["name"],
        "mind_sha256": _sha256(mind),
        "path": str(mind_path(root)),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aurum bounded dialogue supervisor")
    parser.add_argument("--root", type=Path, default=Path("/opt/boxbrain/codelation"))
    parser.add_argument("--model", default=os.environ.get("AURUM_MODEL", DEFAULT_MODEL))
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("status")
    ask_cmd = commands.add_parser("ask")
    ask_cmd.add_argument("--prompt")
    commands.add_parser("self-build")
    commands.add_parser("session")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "status":
        print(json.dumps(status(args.root), sort_keys=True))
        return 0

    if args.command == "session":
        payload = json.load(sys.stdin)
        api_key = payload.get("api_key", "")
        prompt = payload.get("prompt", "")
        model = payload.get("model", args.model)
        self_build_if_bootstrap = bool(payload.get("self_build_if_bootstrap", True))
        response, self_evidence, response_evidence = run_session(
            args.root,
            prompt=prompt,
            model=model,
            api_key=api_key,
            self_build_if_bootstrap=self_build_if_bootstrap,
        )
        print(response)
        print(
            f"AURUM_SESSION_OK mind_version={load_mind(args.root)['version']} "
            f"self_build_evidence={self_evidence or 'none'} response_evidence={response_evidence}",
            file=sys.stderr,
        )
        return 0

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if args.command == "self-build":
        installed, evidence = self_build(args.root, model=args.model, api_key=api_key)
        print(
            f"AURUM_SELF_BUILD_OK version={installed['version']} mind={mind_path(args.root)} "
            f"evidence={evidence}"
        )
        return 0

    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    response, evidence = ask(args.root, prompt=prompt, model=args.model, api_key=api_key)
    print(response)
    print(f"AURUM_RESPONSE_EVIDENCE={evidence}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
