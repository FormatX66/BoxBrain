#!/usr/bin/env python3
"""GPT trait — direct, policy-mediated reasoning and control on Hopper.

GPT can reason across the Aurum OS and may use a bounded set of local tools.
Aurum remains the execution authority: no raw shell is exposed, tracked seed
source is read-only at runtime, temporary UI choices live outside Git, and every
action returns a durable receipt to the model.
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

SCHEMA = "aurum.trait.gpt.gen1-direct-control"
API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = os.environ.get("AURUM_GPT_MODEL", "gpt-5.6-sol")
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
DEFAULT_RUNTIME = Path(os.environ.get("AURUM_RUNTIME_ROOT", "/opt/aurum"))
DEFAULT_KEY_FILE = Path(os.environ.get("AURUM_OPENAI_KEY_FILE", "/run/credentials/aurum-gpt/openai_api_key"))
MAX_TOOL_ROUNDS = 8

SYSTEM_TEXT = (
    "You are GPT operating directly inside Aurum on Hopper. You may reason about every Aurum OS "
    "domain. When the operator asks for a local observation or a change, use the provided Aurum "
    "tools instead of inventing commands. Aurum owns authorization, execution, verification, "
    "healing, cull-and-regrow decisions, and receipts. Never claim an action succeeded unless a returned receipt proves it. "
    "Use the appearance preview tool for requested color or theme experiments; it changes only "
    "reboot-ephemeral runtime state and never tracked seed source. Tracked source is read-only on "
    "the running machine and permanent changes must arrive through a verified next seed. Do not "
    "seek or request raw shell access. Prefer reversible, evidence-producing changes and keep "
    "unknowns explicit. Published generations never move backward: heal the current seed or cull "
    "the candidate and regrow a verified forward successor."
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
        value = ""
    if value:
        return value
    bootstrap = _load_local_module("aurum_credential_bootstrap.py", "aurum_credential_bootstrap")
    if bootstrap is not None:
        try:
            bootstrap.install(
                workspace=DEFAULT_WORKSPACE,
                runtime_root=DEFAULT_RUNTIME,
                runtime_key=DEFAULT_KEY_FILE,
                state_dir=DEFAULT_STATE,
            )
            value = DEFAULT_KEY_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            value = ""
    return value or None


def _load_local_module(filename: str, module_prefix: str):
    candidates = (
        DEFAULT_RUNTIME / filename,
        DEFAULT_WORKSPACE / "Projects" / "AurumPC" / filename,
        Path(__file__).with_name(filename),
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"{module_prefix}_{os.getpid()}_{time.time_ns()}", path
            )
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            return module
        except Exception:
            continue
    return None


def _control_catalog() -> dict[str, Any]:
    module = _load_local_module("aurum_control_plane.py", "aurum_control_plane")
    if module is not None:
        try:
            value = module.catalog()
            if isinstance(value, dict):
                return value
        except Exception:
            pass
    return {
        "schema": "aurum.control-plane.v1",
        "scope": "all-os-domains",
        "model_intent_scope": "full",
        "execution_authority": "aurum-policy-broker",
        "domains": [],
    }


def _executor():
    return _load_local_module("aurum_gpt_executor.py", "aurum_gpt_executor")


def local_context(
    state_dir: Path = DEFAULT_STATE,
    workspace: Path = DEFAULT_WORKSPACE,
) -> dict[str, Any]:
    autonomy = _json_file(state_dir / "autonomy.json")
    runtime = _json_file(state_dir / "runtime-update.json")
    identity = _json_file(state_dir / "machine-identity.json")
    desktop = _json_file(state_dir / "desktop-ui.json")
    executor = _executor()
    executor_catalog = None
    if executor is not None:
        try:
            executor_catalog = executor.catalog()
        except Exception:
            executor_catalog = None
    return {
        "machine": identity.get("display_name") or "Hopper",
        "hostname": identity.get("hostname") or "hopper",
        "branch": "aurum/trunk-v0.01",
        "head": _git_head(workspace),
        "autonomy_status": autonomy.get("status") or "unknown",
        "runtime_status": runtime.get("status") or "unknown",
        "runtime_schema": runtime.get("schema") or "unknown",
        "desktop_status": desktop.get("status") or "unknown",
        "desktop_generation": desktop.get("generation_name") or "unknown",
        "physical_surface": desktop.get("surface") or "unknown",
        "control_plane": _control_catalog(),
        "direct_executor": executor_catalog,
    }


def _tools(executor) -> list[dict[str, Any]]:
    if executor is None:
        return []
    catalog = executor.catalog()
    actions = list(catalog.get("control_actions") or [])
    return [
        {
            "type": "function",
            "name": "aurum_control",
            "description": (
                "Execute one named, bounded Aurum control action on Hopper and return its receipt. "
                "No arbitrary shell command is available."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": actions},
                },
                "required": ["action"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "aurum_workspace_read",
            "description": (
                "Read a bounded line range from an allowed Aurum source file in Hopper's workspace."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                },
                "required": ["path", "start_line", "end_line"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "aurum_appearance_preview",
            "description": (
                "Temporarily preview one bounded Aurum background theme. This changes runtime "
                "state only, never Git, and resets on reboot. Use default to reset it now."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "theme": {
                        "type": "string",
                        "enum": list((catalog.get("appearance") or {}).get("themes") or ["default"]),
                    },
                },
                "required": ["theme"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    ]


def status() -> dict[str, Any]:
    control = _control_catalog()
    executor = _executor()
    key = _api_key()
    if executor is None:
        direct = "executor-required"
    elif not key:
        direct = "api-key-required"
    else:
        direct = "ready"
    return {
        "schema": SCHEMA,
        "trait": "GPT",
        "status": direct,
        "model": DEFAULT_MODEL,
        "endpoint": API_URL,
        "responses_api": True,
        "function_tools": bool(executor),
        "local_context": local_context(),
        "model_intent_scope": control.get("model_intent_scope"),
        "control_scope": control.get("scope"),
        "execution_authority": control.get("execution_authority"),
        "host_actuation": "bounded" if executor else False,
        "workspace_read": bool(executor),
        "workspace_exact_replace": False,
        "appearance_preview": bool(executor),
        "appearance_resets_on_reboot": True,
        "raw_shell": False,
        "git_push": False,
        "key_persisted_by_trait": False,
        "browser_credential": False,
        "credential_source": (
            "environment"
            if os.environ.get("OPENAI_API_KEY", "").strip()
            else ("machine-sealed-runtime" if key else "unavailable")
        ),
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


def _function_calls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for item in payload.get("output") or []:
        if isinstance(item, dict) and item.get("type") == "function_call":
            calls.append(item)
    return calls


def _post(body: dict[str, Any], *, key: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "Aurum-GPT-Gen1-Direct-Control",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(4_000_000).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read(8192).decode("utf-8", "replace")
        raise GptTraitError(f"OpenAI HTTP {exc.code}: {detail[:2000]}") from exc
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise GptTraitError(
            f"OpenAI request failed: {type(exc).__name__}:{exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise GptTraitError("OpenAI response was not an object")
    return payload


def model_probe(*, model: str = DEFAULT_MODEL, timeout: int = 60) -> dict[str, Any]:
    """Prove the remote model path without giving the model any local tools."""
    key = _api_key()
    if not key:
        return {
            "schema": SCHEMA,
            "status": "unproven",
            "model": model,
            "reason": "api-key-required",
            "model_call_proven": False,
            "tools_offered": False,
        }
    marker = "AURUM_HOPPER_MODEL_READY"
    payload = _post(
        {
            "model": model,
            "instructions": f"Return exactly {marker} and nothing else.",
            "input": "Prove the bounded Aurum model path.",
            "reasoning": {"effort": "none"},
            "max_output_tokens": 64,
        },
        key=key,
        timeout=timeout,
    )
    exact = _extract_text(payload) == marker
    return {
        "schema": SCHEMA,
        "status": "passed" if exact else "failed",
        "model": payload.get("model") or model,
        "response_id": payload.get("id"),
        "model_call_proven": exact,
        "tools_offered": False,
        "raw_shell": False,
        "proven_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _dispatch(executor, call: dict[str, Any]) -> dict[str, Any]:
    name = str(call.get("name") or "")
    try:
        arguments = json.loads(str(call.get("arguments") or "{}"))
    except json.JSONDecodeError as exc:
        raise GptTraitError(f"invalid tool arguments for {name}: {exc}") from exc
    if not isinstance(arguments, dict):
        raise GptTraitError(f"tool arguments for {name} were not an object")
    try:
        if name == "aurum_control":
            return executor.execute_control(str(arguments.get("action") or ""))
        if name == "aurum_workspace_read":
            return executor.read_workspace(
                str(arguments.get("path") or ""),
                start_line=int(arguments.get("start_line") or 1),
                end_line=int(arguments.get("end_line") or 1),
            )
        if name == "aurum_appearance_preview":
            return executor.set_appearance(str(arguments.get("theme") or ""))
    except Exception as exc:
        return {
            "schema": "aurum.gpt-tool-error.gen1-direct-control",
            "tool": name,
            "status": "failed",
            "detail": f"{type(exc).__name__}:{exc}",
        }
    return {
        "schema": "aurum.gpt-tool-error.gen1-direct-control",
        "tool": name,
        "status": "failed",
        "detail": "unsupported tool",
    }


def ask(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    timeout: int = 180,
) -> dict[str, Any]:
    key = _api_key()
    if not key:
        raise GptTraitError("OPENAI_API_KEY is not available to the GPT trait")
    clean = " ".join(str(prompt).split())
    if not clean:
        raise GptTraitError("prompt is empty")
    if len(clean) > 24000:
        raise GptTraitError("prompt exceeds GPT trait input bound")

    executor = _executor()
    tools = _tools(executor)
    context = local_context()
    body: dict[str, Any] = {
        "model": model,
        "instructions": SYSTEM_TEXT,
        "input": (
            "Verified local Aurum context:\n"
            + json.dumps(context, sort_keys=True)
            + "\n\nOperator request:\n"
            + clean
        ),
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
        body["parallel_tool_calls"] = False

    tool_receipts: list[dict[str, Any]] = []
    payload = _post(body, key=key, timeout=timeout)
    for _round in range(MAX_TOOL_ROUNDS):
        calls = _function_calls(payload)
        if not calls:
            text = _extract_text(payload)
            if not text:
                raise GptTraitError("OpenAI response contained no final output text")
            return {
                "schema": SCHEMA,
                "trait": "GPT",
                "status": "completed",
                "model": payload.get("model") or model,
                "response_id": payload.get("id"),
                "text": text,
                "control_scope": "all-os-domains",
                "host_actuation": "bounded" if executor else False,
                "tool_receipts": tool_receipts,
                "raw_shell": False,
                "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        if executor is None:
            raise GptTraitError("model requested a tool but the Aurum executor is unavailable")
        outputs: list[dict[str, Any]] = []
        for call in calls:
            receipt = _dispatch(executor, call)
            tool_receipts.append(receipt)
            call_id = call.get("call_id")
            if not call_id:
                raise GptTraitError("OpenAI function call did not include call_id")
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(receipt, sort_keys=True),
                }
            )
        follow: dict[str, Any] = {
            "model": model,
            "previous_response_id": payload.get("id"),
            "input": outputs,
            "tools": tools,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
        }
        payload = _post(follow, key=key, timeout=timeout)
    raise GptTraitError("GPT direct-control tool loop exceeded bounded round limit")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aurum GPT direct-control trait")
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
                    "Inspect local Aurum state and prepare or execute the bounded implementation steps "
                    "needed for this request. Use Aurum tools when action is appropriate and report "
                    "receipts rather than assumptions. Request: "
                    + prompt
                )
            result = ask(prompt, model=args.model)
    except GptTraitError as exc:
        result = {
            "schema": SCHEMA,
            "trait": "GPT",
            "status": "failed",
            "detail": str(exc),
        }
        print(json.dumps(result, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
