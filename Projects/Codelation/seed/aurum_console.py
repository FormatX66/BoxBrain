#!/usr/bin/env python3
"""Interactive, dialogue-only Aurum console for the BBPI4.

The console deliberately exposes no shell, tools, or host actuation. It wraps
the bounded dialogue supervisor already installed with the Aurum gold seed.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Callable, Mapping, TextIO

from aurum_dialogue import DEFAULT_MODEL, Reasoner, ask, call_openai_reasoner, status


CONSOLE_SCHEMA = "aurum.console.v1"
DEFAULT_ROOT = Path("/opt/boxbrain/codelation")
PLAIN_PROMPT = "Åurum> "
YELLOW = "\x1b[33m"
TEAL = "\x1b[38;2;0;150;160m"
RESET = "\x1b[0m"
HELP = """Commands:
  /status  Show the bounded Aurum mind status.
  /help    Show this help.
  /quit    Close the console.

Any other text is sent to Aurum's dialogue-only supervisor. The console has no
shell or host-control actions. Dialogue evidence is stored locally by the
existing supervisor; an API key is held in memory only for this process.
"""


def console_status(root: Path, model: str) -> dict[str, object]:
    mind = status(root)
    return {
        "schema": CONSOLE_SCHEMA,
        "identity": mind["identity"],
        "name": mind["name"],
        "mind_version": mind["mind_version"],
        "mind_sha256": mind["mind_sha256"],
        "model": model,
        "root": str(root.expanduser().resolve()),
        "dialogue_only": True,
        "host_actuation": False,
        "api_key_persisted": False,
    }


def _write(stream: TextIO, text: str = "") -> None:
    stream.write(text + "\n")
    stream.flush()


def _console_prompt(stream: TextIO) -> str:
    if not getattr(stream, "isatty", lambda: False)():
        return PLAIN_PROMPT
    return f"{YELLOW}Å{RESET}{TEAL}u{RESET}rum> "


def _read_key(
    environment: Mapping[str, str],
    key_provider: Callable[[str], str],
) -> str:
    key = environment.get("OPENAI_API_KEY", "").strip()
    if not key:
        key = key_provider("OpenAI API key (memory only; not saved): ").strip()
    if not key:
        raise ValueError("an API key is required for live dialogue")
    return key


def run_console(
    root: Path,
    *,
    model: str = DEFAULT_MODEL,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
    error_stream: TextIO = sys.stderr,
    environment: Mapping[str, str] = os.environ,
    key_provider: Callable[[str], str] = getpass.getpass,
    reasoner: Reasoner = call_openai_reasoner,
    allow_key_prompt: bool = True,
) -> int:
    current = console_status(root, model)
    _write(output_stream, "AURUM CONSOLE — BBPI4")
    _write(
        output_stream,
        f"{current['name']} | mind v{current['mind_version']} | dialogue only | model {model}",
    )
    _write(output_stream, "Type /help for commands. Type /quit to leave.")

    api_key: str | None = None
    while True:
        output_stream.write(_console_prompt(output_stream))
        output_stream.flush()
        line = input_stream.readline()
        if line == "":
            _write(output_stream, "")
            return 0
        prompt = line.strip()
        if not prompt:
            continue

        command = prompt.casefold()
        if command in {"/quit", "/exit"}:
            _write(output_stream, "Aurum console closed.")
            return 0
        if command == "/help":
            _write(output_stream, HELP.rstrip())
            continue
        if command == "/status":
            _write(output_stream, json.dumps(console_status(root, model), sort_keys=True))
            continue
        if command.startswith("/"):
            _write(error_stream, "Unknown console command. Type /help.")
            continue

        try:
            if api_key is None:
                if not allow_key_prompt and not environment.get("OPENAI_API_KEY", "").strip():
                    raise ValueError("live dialogue is disabled without an in-memory API key")
                api_key = _read_key(environment, key_provider)
            response, evidence = ask(
                root,
                prompt=prompt,
                model=model,
                api_key=api_key,
                reasoner=reasoner,
            )
        except Exception as exc:  # keep an interactive console alive after bounded failures
            _write(error_stream, f"Aurum dialogue unavailable: {type(exc).__name__}: {exc}")
            continue

        _write(output_stream, f"\nAurum: {response}")
        _write(output_stream, f"[evidence: {evidence}]")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BBPI4 Aurum dialogue-only console")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--model", default=os.environ.get("AURUM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--status", action="store_true", help="print console readiness and exit")
    parser.add_argument(
        "--no-key-prompt",
        action="store_true",
        help="do not prompt for a key; dialogue remains unavailable unless OPENAI_API_KEY exists",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.status:
        current = console_status(args.root, args.model)
        print(
            "AURUM_CONSOLE_READY "
            f"identity={current['identity']} mind_version={current['mind_version']} "
            f"dialogue_only=true host_actuation=false api_key_persisted=false"
        )
        return 0
    return run_console(
        args.root,
        model=args.model,
        allow_key_prompt=not args.no_key_prompt,
    )


if __name__ == "__main__":
    raise SystemExit(main())
