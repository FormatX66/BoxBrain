"""One-request observation-only Windows Sandbox plugin process."""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from typing import Any

from pydantic import ValidationError

from boxbrain_controller.observation_policy import ObservationPolicy
from boxbrain_controller.sandbox_observer import (
    NormalizedRedactionRegion,
    SandboxCaptureError,
    WindowsSandboxObserver,
)


PLUGIN_ID = "boxbrain.windows-sandbox-observer"
PROTOCOL_VERSION = "1"
MAX_REQUEST_BYTES = 64 * 1024


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
    ):
        return response(request_id=request_id, ok=False, error="identity mismatch")

    if request["operation"] == "describe":
        if request["payload"]:
            return response(
                request_id=request_id,
                ok=False,
                error="invalid_payload",
            )
        observer = WindowsSandboxObserver(start_enabled=False)
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
        if set(request["payload"]) != {"policy"}:
            return response(
                request_id=request_id,
                ok=False,
                error="invalid_policy",
            )
        try:
            policy = ObservationPolicy.model_validate(
                request["payload"]["policy"]
            )
        except ValidationError:
            return response(
                request_id=request_id,
                ok=False,
                error="invalid_policy",
            )
        observer = WindowsSandboxObserver(
            max_frame_width=policy.max_frame_width,
            start_enabled=False,
        )
        redaction_regions = tuple(
            NormalizedRedactionRegion(
                x=region.x,
                y=region.y,
                width=region.width,
                height=region.height,
            )
            for region in policy.redaction_regions
        )
        try:
            frame = observer.capture_png(
                redaction_regions=redaction_regions,
            )
        except SandboxCaptureError:
            return response(
                request_id=request_id,
                ok=False,
                error="target_not_running",
            )
        if len(frame) > policy.max_frame_bytes:
            return response(
                request_id=request_id,
                ok=False,
                error="frame_too_large",
            )
        return response(
            request_id=request_id,
            ok=True,
            result={
                "target_id": observer.target_id,
                "media_type": "image/png",
                "sha256": hashlib.sha256(frame).hexdigest(),
                "redaction_region_count": len(redaction_regions),
                "max_frame_width": policy.max_frame_width,
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
