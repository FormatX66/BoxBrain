"""One-request observation-only Windows Sandbox plugin process."""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from typing import Any

from boxbrain_controller.sandbox_observer import (
    SandboxCaptureError,
    WindowsSandboxObserver,
)


PLUGIN_ID = "boxbrain.windows-sandbox-observer"
PROTOCOL_VERSION = "1"
MAX_REQUEST_BYTES = 64 * 1024
MAX_FRAME_WIDTH = 1280


def response(
    *,
    request_id: str,
    ok: bool,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "plugin_id": PLUGIN_ID,
        "request_id": request_id,
        "ok": ok,
        "result": result,
        "error": error,
    }


def handle(request: dict[str, Any]) -> dict[str, Any]:
    request_id = str(request.get("request_id", "invalid"))
    if set(request) != {
        "protocol_version",
        "plugin_id",
        "request_id",
        "operation",
        "payload",
    }:
        return response(request_id=request_id, ok=False, error="invalid request")
    if (
        request["protocol_version"] != PROTOCOL_VERSION
        or request["plugin_id"] != PLUGIN_ID
        or not isinstance(request["payload"], dict)
        or request["payload"]
    ):
        return response(request_id=request_id, ok=False, error="identity mismatch")

    observer = WindowsSandboxObserver(
        max_frame_width=MAX_FRAME_WIDTH,
        start_enabled=False,
    )
    if request["operation"] == "describe":
        description = observer.describe()
        return response(
            request_id=request_id,
            ok=True,
            result={
                "target_id": observer.target_id,
                "target_name": observer.target_name,
                "connected": description["connected"],
                "window_title": description["window_title"],
                "input_enabled": False,
            },
        )
    if request["operation"] == "capture_frame":
        try:
            frame = observer.capture_png()
        except SandboxCaptureError:
            return response(
                request_id=request_id,
                ok=False,
                error="target_not_running",
            )
        return response(
            request_id=request_id,
            ok=True,
            result={
                "target_id": observer.target_id,
                "media_type": "image/png",
                "sha256": hashlib.sha256(frame).hexdigest(),
                "data_base64": base64.b64encode(frame).decode("ascii"),
            },
        )
    return response(request_id=request_id, ok=False, error="operation not allowed")


def main() -> int:
    raw = sys.stdin.buffer.readline(MAX_REQUEST_BYTES + 1)
    if not raw or len(raw) > MAX_REQUEST_BYTES:
        return 2
    try:
        request = json.loads(raw.decode("utf-8"))
        if not isinstance(request, dict):
            return 2
        result = handle(request)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return 2
    output = json.dumps(result, separators=(",", ":"), sort_keys=True)
    sys.stdout.write(output + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
