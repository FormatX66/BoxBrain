#!/usr/bin/env python3
"""Context-aware loopback GUI surface for Aurum.

This module reuses the existing Aurum GUI shell and security boundary while
routing /api/ask through a bounded semantic context session. Raw prior turns
remain process-local. Only a content-free integrity marker is persisted so a
restart can detect lost semantic continuity and fail closed instead of
pretending memory survived.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import aurum_gui as base
from aurum_context import BoundedContextSession
from aurum_dialogue import (
    DEFAULT_MODEL,
    Reasoner,
    _hard_supervisor_instruction,
    call_openai_reasoner,
    initialize_mind,
)
from context_exchange import parse_context_state

CONTEXT_SURFACE_SCHEMA = "aurum.gui.context-surface.v1"
MAX_CONTEXT_MARKER_BYTES = 2048


class ContextContinuityLost(RuntimeError):
    def __init__(self, sequence: int) -> None:
        super().__init__("semantic context unavailable after restart")
        self.sequence = sequence


def _marker_path(root: Path) -> Path:
    base_root = root.expanduser().resolve()
    path = (base_root / "state" / "interface" / "gui_context_marker.json").resolve()
    if base_root not in path.parents:
        raise ValueError("context marker path escaped Aurum root")
    return path


def _context_evidence_dir(root: Path) -> Path:
    base_root = root.expanduser().resolve()
    path = (base_root / "verification" / "dialogue").resolve()
    if base_root not in path.parents:
        raise ValueError("context evidence path escaped Aurum root")
    return path


def _read_marker(root: Path) -> str | None:
    path = _marker_path(root)
    try:
        if path.stat().st_size > MAX_CONTEXT_MARKER_BYTES:
            raise ValueError("context marker exceeded its bound")
    except FileNotFoundError:
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("context marker is invalid")
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"))
    parse_context_state(raw)
    return raw


def _write_marker(root: Path, marker: str) -> None:
    state = parse_context_state(marker)
    base._atomic_private_json(_marker_path(root), {
        "schema": state.schema,
        "context_id": state.context_id,
        "sequence": state.sequence,
        "input_sha256": state.input_sha256,
        "output_sha256": state.output_sha256,
        "previous_chain_sha256": state.previous_chain_sha256,
        "chain_sha256": state.chain_sha256,
    })


def _remove_marker(root: Path) -> None:
    try:
        _marker_path(root).unlink()
    except FileNotFoundError:
        pass


class AurumContextGuiServer(base.AurumGuiServer):
    """Existing GUI server plus one bounded semantic context per server surface."""

    def __init__(
        self,
        server_address: tuple[str, int],
        root: Path,
        model: str,
        reasoner: Reasoner,
    ) -> None:
        super().__init__(server_address, root, model, reasoner)
        self.RequestHandlerClass = AurumContextGuiHandler
        self.context_lock = threading.Lock()
        self._context_system_message = _hard_supervisor_instruction(
            initialize_mind(self.aurum_root)
        )
        marker = _read_marker(self.aurum_root)
        if marker is None:
            self._context_session = self._fresh_context_session()
        else:
            restored = parse_context_state(marker)
            self._context_session = BoundedContextSession.from_restart_marker(
                context_id=restored.context_id,
                system_message=self._context_system_message,
                marker=marker,
            )

    def _fresh_context_session(self) -> BoundedContextSession:
        return BoundedContextSession(
            context_id="gui-" + secrets.token_hex(16),
            system_message=self._context_system_message,
        )

    def context_status(self) -> dict[str, Any]:
        with self.context_lock:
            session = self._context_session
            marker = session.integrity_marker()
            return {
                "schema": CONTEXT_SURFACE_SCHEMA,
                "context_id": session.context_id,
                "sequence": session.sequence,
                "retained_turns": len(session.retained_turns),
                "semantic_context_lost": session.semantic_context_lost,
                "bounded_prior_turns": True,
                "marker_persisted": marker is not None,
                "raw_context_persisted": False,
                "api_key_persisted": False,
                "host_actuation": False,
            }

    def exchange_with_context(
        self,
        *,
        prompt: str,
        model: str,
        api_key: str,
    ) -> tuple[str, Path, int]:
        with self.context_lock:
            if self._context_session.semantic_context_lost:
                lost_sequence = self._context_session.sequence
                self._context_session = self._fresh_context_session()
                _remove_marker(self.aurum_root)
                raise ContextContinuityLost(lost_sequence)

            response, marker = self._context_session.exchange(
                prompt=prompt,
                model=model,
                api_key=api_key,
                reasoner=self.aurum_reasoner,
            )
            _write_marker(self.aurum_root, marker)
            state = parse_context_state(marker)
            evidence = {
                "schema": "aurum.gui.context.evidence.v1",
                "observed_at": int(time.time()),
                "context_id": state.context_id,
                "sequence": state.sequence,
                "chain_sha256": state.chain_sha256,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
                "model": model,
                "prior_turns_supplied": state.sequence > 1,
                "raw_user_content_persisted": False,
                "api_key_persisted": False,
                "host_actuation": False,
            }
            evidence_hash = hashlib.sha256(
                json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            evidence_path = _context_evidence_dir(self.aurum_root) / (
                f"AURUM_CONTEXT_{state.sequence:08d}_{evidence_hash[:12]}.json"
            )
            base._atomic_private_json(evidence_path, evidence)
            return response, evidence_path, state.sequence


class AurumContextGuiHandler(base.AurumGuiHandler):
    server: AurumContextGuiServer

    def _status_payload(self) -> dict[str, Any]:
        payload = super()._status_payload()
        payload["context"] = self.server.context_status()
        return payload

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        request_path = urlsplit(self.path).path
        if request_path != "/api/ask":
            super().do_POST()
            return

        if not self._host_is_loopback() or not self._origin_is_loopback():
            self._error(HTTPStatus.FORBIDDEN, "loopback origin required")
            return
        if not secrets.compare_digest(
            self.headers.get("X-Aurum-CSRF", ""), self.server.csrf_token
        ):
            self._error(HTTPStatus.FORBIDDEN, "request proof invalid")
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "application/json required")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 1 <= length <= base.MAX_REQUEST_BYTES:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request size invalid")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(HTTPStatus.BAD_REQUEST, "invalid JSON")
            return
        if not isinstance(payload, dict) or not set(payload).issubset({"prompt", "api_key", "model"}):
            self._error(HTTPStatus.BAD_REQUEST, "request fields invalid")
            return

        prompt = payload.get("prompt")
        api_key = payload.get("api_key")
        model = payload.get("model", self.server.aurum_model)
        if not isinstance(prompt, str) or not prompt.strip():
            self._error(HTTPStatus.BAD_REQUEST, "prompt is empty")
            return
        if not isinstance(api_key, str) or not api_key.strip() or len(api_key) > base.MAX_API_KEY_CHARS:
            self._error(HTTPStatus.BAD_REQUEST, "API key is required")
            return
        if (
            not isinstance(model, str)
            or len(model) > base.MAX_MODEL_CHARS
            or base.MODEL_PATTERN.fullmatch(model) is None
        ):
            self._error(HTTPStatus.BAD_REQUEST, "model is invalid")
            return

        try:
            response, evidence, sequence = self.server.exchange_with_context(
                prompt=prompt,
                model=model,
                api_key=api_key.strip(),
            )
        except ContextContinuityLost as exc:
            self._json(
                HTTPStatus.CONFLICT,
                {
                    "schema": CONTEXT_SURFACE_SCHEMA,
                    "error": "semantic context was lost across restart; context reset",
                    "lost_sequence": exc.sequence,
                    "retry_starts_new_context": True,
                    "host_actuation": False,
                    "api_key_persisted": False,
                },
            )
            return
        except Exception as exc:
            self._error(
                HTTPStatus.BAD_GATEWAY,
                f"Aurum context exchange unavailable: {type(exc).__name__}",
            )
            return

        self._json(
            HTTPStatus.OK,
            {
                "schema": base.GUI_SCHEMA,
                "context_schema": CONTEXT_SURFACE_SCHEMA,
                "response": response,
                "evidence": evidence.name,
                "context_sequence": sequence,
                "context_continuity": True,
                "host_actuation": False,
                "api_key_persisted": False,
            },
        )


def create_server(
    host: str,
    port: int,
    root: Path,
    model: str = DEFAULT_MODEL,
    reasoner: Reasoner = call_openai_reasoner,
) -> AurumContextGuiServer:
    if host not in {"127.0.0.1", "::1"}:
        raise ValueError("Aurum GUI must bind to loopback")
    if port != 0 and not 1024 <= port <= 65535:
        raise ValueError("Aurum GUI port must be zero or between 1024 and 65535")
    if len(model) > base.MAX_MODEL_CHARS or base.MODEL_PATTERN.fullmatch(model) is None:
        raise ValueError("Aurum model name is invalid")
    return AurumContextGuiServer((host, port), root, model, reasoner)


def main() -> int:
    args = base.build_parser().parse_args()
    if args.status:
        payload = base.console_status(args.root, args.model)
        preferences = base.load_preferences(args.root)
        payload.update(
            {
                "gui_schema": base.GUI_SCHEMA,
                "context_surface_schema": CONTEXT_SURFACE_SCHEMA,
                "host": args.host,
                "port": args.port,
                "loopback_only": args.host in {"127.0.0.1", "::1"},
                "safe_layout_available": True,
                "adaptation_lock_available": True,
                "preferences": preferences,
                "proof_view_present": True,
                "key_bootstrap_schema": base.KEY_BOOTSTRAP_SCHEMA,
                "key_bootstrap_memory_only": True,
            }
        )
        print(json.dumps(payload, sort_keys=True))
        return 0

    server = create_server(args.host, args.port, args.root, args.model)
    print(
        f"AURUM_GUI_READY address={args.host} port={server.server_address[1]} "
        "context_exchange=true host_actuation=false",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
