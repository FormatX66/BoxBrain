#!/usr/bin/env python3
"""GPT trait — OpenAI reasoning bridge for Aurum on Hopper.

GPT may reason about and request changes across the whole Aurum OS. Aurum's
control plane remains the authority for authorization, execution, verification,
and rollback. The model therefore gains full OS scope without raw shell access
becoming the operating-system contract.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SCHEMA = "aurum.trait.gpt.v1"
API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = os.environ.get("AURUM_GPT_MODEL", "gpt-5.6-sol")
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
DEFAULT_RUNTIME = Path(os.environ.get("AURUM_RUNTIME_ROOT", "/opt/aurum"))
DEFAULT_KEY_FILE = Path(os.environ.get("AURUM_OPENAI_KEY_FILE", "/run/credentials/aurum-gpt/openai_api_key"))

SYSTEM_TEXT = (
    "You are GPT operating as a reasoning trait inside Aurum on Hopper. You may reason about "
    "and request changes across every Aurum OS domain, including appearance, interaction, traits, "
    "builds, runtime, kernel, devices, transport, storage, identity, permissions, recovery, and power. "
    "Aurum's control plane owns authorization, execution, verification, and rollback. Do not claim an "
    "action happened unless Aurum reports that it happened. Prefer machine-first capability design, "
    "reversible changes, concise operator guidance, and explicit blockers."
)


class GptTraitError(RuntimeError):
    pass


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _text(path: Path, default: str = "") -> str:
    try:
        value = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default
    return value or default


def _git_head(workspace: Path) -> str:
    raw = _text(workspace / ".git" / "HEAD")
    if raw.startswith("ref: "):
        return _text(workspace / ".git" / raw[5:].strip(), "unknown")
    return raw or "unknown"


def _api_key() -> str | None:
    value = os.environ.get("OPENAI_API_KEY", "").strip()
    if value:
        return value
    try:
        value = DEFAULT_KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _control_catalog() -> dict[str, Any]:
    candidates = (
        DEFAULT_RUNTIME / "aurum_control_plane.py",
        DEFAULT_WORKSPACE / "Projects" / "AurumPC" / "aurum_control_plane.py",
        Path(__file__).with_name("aurum_control_plane.py"),
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"aurum_control_plane_{os.getpid()}_{time.time_ns()}", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            value = module.catalog()
            if isinstance(value, dict) and value.get("schema") == "aurum.control-plane.v1":
                return value
        except Exception:
            continue
    return {
        "schema": "aurum.control-plane.v1",
        "scope": "all-os-domains",
        "model_intent_scope": "full",
        "execution_authority": "aurum-policy-broker",
        "domains": [],
    }


def local_context(state_dir: Path = DEFAULT_STATE, workspace: Path = DEFAULT_WORKSPACE) -> dict[str, Any]:
    autonomy = _json_file(state_dir / "autonomy.json")
    runtime = _json_file(state_dir / "runtime-update.json")
    identity = _json_file(state_dir / "machine-identity.json")
    desktop = _json_file(state_dir / "desktop-ui.json")
    return {
        "machine": identity.get("display_name") or "Hopper",
        "hostname": identity.get("hostname") or "hopper",
        "branch": "aurum/trunk-v0.01",
        "head": _git_head(workspace),
        "autonomy_status": autonomy.get("status") or "unknown",
        "runtime_status": runtime.get("status") or "unknown",
        "runtime_schema": runtime.get("schema") or "unknown",
        "desktop_status": desktop.get("status") or "unknown",
        "physical_surface": desktop.get("surface") or "unknown",
        "control_plane": _control_catalog(),
    }


def status() -> dict[str, Any]:
    control = _control_catalog()
    return {
        "schema": SCHEMA,
        "trait": "GPT",
        "status": "ready-for-api-key" if _api_key() else "key-required",
        "model": DEFAULT_MODEL,
        "endpoint": API_URL,
        "responses_api": True,
        "local_context": local_context(),
        "model_intent_scope": control.get("model_intent_scope"),
        "control_scope": control.get("scope"),
        "execution_authority": control.get("execution_authority"),
        "host_actuation": False,
        "build_broker": "control-plane-planning-ready-executor-pending",
        "key_persisted_by_trait": False,
    }


def _extract_text(payload: dict[str, Any]) -> str:
    for item in payload.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
    text = payload.get("output_text")
    return text.strip() if isinstance(text, str) else ""


def ask(prompt: str, *, model: str = DEFAULT_MODEL, timeout: int = 180) -> dict[str, Any]:
    key = _api_key()
    if not key:
        raise GptTraitError("OPENAI_API_KEY is not available to the GPT trait")
    clean = " ".join(str(prompt).split())
    if not clean:
        raise GptTraitError("prompt is empty")
    if len(clean) > 24000:
        raise GptTraitError("prompt exceeds GPT trait input bound")

    context = local_context()
    body = json.dumps(
        {
            "model": model,
            "instructions": SYSTEM_TEXT,
            "input": (
                "Verified local Aurum context:\n"
                + json.dumps(context, sort_keys=True)
                + "\n\nOperator request:\n"
                + clean
            ),
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "Aurum-GPT-Trait/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(2_000_000).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", "replace")
        raise GptTraitError(f"OpenAI HTTP {exc.code}: {detail[:1200]}") from exc
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise GptTraitError(f"OpenAI request failed: {type(exc).__name__}:{exc}") from exc

    text = _extract_text(payload)
    if not text:
        raise GptTraitError("OpenAI response contained no output text")
    return {
        "schema": SCHEMA,
        "trait": "GPT",
        "status": "completed",
        "model": payload.get("model") or model,
        "response_id": payload.get("id"),
        "text": text,
        "control_scope": "all-os-domains",
        "host_actuation": False,
        "build_broker": "control-plane-planning-ready-executor-pending",
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aurum GPT reasoning trait")
    parser.add_argument("command", choices=("status", "ask", "build-plan"))
    parser.add_argument("prompt", nargs="*")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "status":
            result = status()
        else:
            prompt = " ".join(args.prompt).strip()
            if args.command == "build-plan":
                prompt = (
                    "Prepare the next Aurum control-plane implementation plan for this request. "
                    "Use any OS domain required, but separate model intent from operations the Aurum "
                    "executor must authorize, execute, verify, and receipt. Request: " + prompt
                )
            result = ask(prompt, model=args.model)
    except GptTraitError as exc:
        result = {"schema": SCHEMA, "trait": "GPT", "status": "failed", "detail": str(exc)}
        print(json.dumps(result, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
