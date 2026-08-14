#!/usr/bin/env python3
"""Aurum GUI local-first control surface.

The GUI is intentionally dependency-light: Python's standard library serves the
static interface and exposes a small read-mostly status API plus an Aurum-owned
LLM chat bridge.  It binds to loopback by default; LAN exposure must be explicit.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlparse

VERSION = "0.01"
HERE = Path(__file__).resolve().parent
STATIC_ROOT = HERE / "static"
REPO_ROOT = HERE.parents[1]
LLM_ROOT = REPO_ROOT / "Projects" / "AurumLLM"
if LLM_ROOT.is_dir():
    sys.path.insert(0, str(LLM_ROOT))

try:
    from aurum_llm import AurumLLM, AurumLLMConfig, AurumLLMError  # type: ignore
except Exception:  # GUI must still boot when the model lane is absent.
    AurumLLM = None  # type: ignore[assignment]
    AurumLLMConfig = None  # type: ignore[assignment]

    class AurumLLMError(RuntimeError):
        pass


def _codelation_root() -> Path:
    configured = os.environ.get("AURUM_CODELATION_ROOT")
    candidates = [
        Path(configured) if configured else None,
        REPO_ROOT / "Projects" / "Codelation",
        Path("/opt/aurum/codelation"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_dir():
            return candidate
    return REPO_ROOT / "Projects" / "Codelation"


def _read_text(path: Path, default: str = "unknown") -> str:
    try:
        value = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default
    return value or default


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _memory_total_bytes() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _names(path: Path) -> list[str]:
    try:
        return sorted(item.name for item in path.iterdir())
    except OSError:
        return []


def machine_status() -> dict[str, Any]:
    return {
        "hostname": socket.gethostname(),
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "platform": platform.system(),
        "vendor": _read_text(Path("/sys/class/dmi/id/sys_vendor")),
        "model": _read_text(Path("/sys/class/dmi/id/product_name")),
        "cpu_count": os.cpu_count(),
        "memory_total_bytes": _memory_total_bytes(),
        "network_interfaces": _names(Path("/sys/class/net")),
        "block_devices": _names(Path("/sys/class/block")),
        "pci_device_count": len(_names(Path("/sys/bus/pci/devices"))),
        "usb_device_count": len(_names(Path("/sys/bus/usb/devices"))),
    }


def aurum_state() -> dict[str, Any]:
    root = _codelation_root()
    state = _read_json(root / "autobuild" / "native_chain_state.json")
    workflow = state.get("workflow_verification")
    if not isinstance(workflow, dict):
        workflow = {}
    return {
        "codelation_present": root.is_dir(),
        "completed_generations": state.get("completed_generations"),
        "latest_completed_gap": state.get("latest_completed_gap"),
        "next_gap": state.get("next_gap"),
        "blocked_reason": state.get("blocked_reason"),
        "trusted_for_continuation": workflow.get("trusted_for_continuation"),
        "reusable_native_capabilities": state.get("reusable_native_capabilities") or [],
        "reusable_local_capabilities": state.get("reusable_local_capabilities") or [],
    }


def llm_health() -> dict[str, Any]:
    if AurumLLM is None or AurumLLMConfig is None:
        return {"available": False, "state": "client-not-present", "model": "aurum-seed"}
    server_url = os.environ.get("AURUM_LLM_URL", "http://127.0.0.1:8080")
    model = os.environ.get("AURUM_LLM_MODEL", "aurum-seed")
    try:
        client = AurumLLM(AurumLLMConfig(server_url=server_url, model_alias=model, timeout_seconds=2.0))
        health = client.health()
    except Exception as exc:
        return {
            "available": False,
            "state": "offline",
            "model": model,
            "detail": f"{type(exc).__name__}:{exc}",
        }
    return {"available": True, "state": "ready", "model": model, "health": health}


def build_status(*, include_llm_health: bool = True) -> dict[str, Any]:
    return {
        "schema": "aurum-gui-status-v0",
        "gui_version": VERSION,
        "machine": machine_status(),
        "aurum": aurum_state(),
        "llm": llm_health() if include_llm_health else {"state": "not-probed"},
    }


def _normalize_messages(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("messages must be a non-empty list")
    if len(raw) > 32:
        raise ValueError("too many messages")
    normalized: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each message must be an object")
        role = item.get("role")
        content = item.get("content")
        if role not in {"system", "user", "assistant"}:
            raise ValueError("invalid message role")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("message content must be non-empty text")
        if len(content) > 16_384:
            raise ValueError("message content is too large")
        normalized.append({"role": role, "content": content.strip()})
    if normalized[0]["role"] != "system":
        normalized.insert(
            0,
            {
                "role": "system",
                "content": (
                    "You are Aurum's local semantic interface. Be concise, identify uncertainty, "
                    "and never claim a machine action happened unless verified evidence is supplied."
                ),
            },
        )
    return normalized


def chat_with_aurum(messages: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    if AurumLLM is None or AurumLLMConfig is None:
        raise AurumLLMError("Aurum LLM client is not present")
    server_url = os.environ.get("AURUM_LLM_URL", "http://127.0.0.1:8080")
    model = os.environ.get("AURUM_LLM_MODEL", "aurum-seed")
    client = AurumLLM(AurumLLMConfig(server_url=server_url, model_alias=model))
    reply = client.chat(messages, temperature=0.2, max_tokens=512)
    return {
        "model": model,
        "content": reply.content,
        "reasoning_content": reply.reasoning_content,
        "tool_calls": list(reply.tool_calls),
    }


class AurumGUIHandler(BaseHTTPRequestHandler):
    server_version = "AurumGUI/0.01"

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.environ.get("AURUM_GUI_QUIET") != "1":
            super().log_message(fmt, *args)

    def _json(self, status: int, payload: Mapping[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)

    def _static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"", "/"} else unquote(request_path).lstrip("/")
        candidate = (STATIC_ROOT / relative).resolve()
        try:
            candidate.relative_to(STATIC_ROOT.resolve())
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        suffix = candidate.suffix.lower()
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
        }.get(suffix, "application/octet-stream")
        data = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/status":
            self._json(HTTPStatus.OK, build_status())
            return
        if path == "/api/health":
            self._json(HTTPStatus.OK, {"ok": True, "version": VERSION})
            return
        self._static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/api/chat":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid content length"})
            return
        if content_length <= 0 or content_length > 262_144:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid request size"})
            return
        try:
            raw = json.loads(self.rfile.read(content_length).decode("utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("request body must be an object")
            messages = _normalize_messages(raw.get("messages"))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        try:
            reply = chat_with_aurum(messages)
        except Exception as exc:
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "Aurum reasoning core unavailable", "detail": f"{type(exc).__name__}:{exc}"},
            )
            return
        self._json(HTTPStatus.OK, reply)


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the Aurum local GUI")
    parser.add_argument("--host", default=os.environ.get("AURUM_GUI_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("AURUM_GUI_PORT", "8765")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), AurumGUIHandler)
    print(f"AURUM_GUI_READY version={VERSION} url=http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
