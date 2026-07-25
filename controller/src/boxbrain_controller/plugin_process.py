from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from time import monotonic
from typing import Any, BinaryIO, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .plugin_registry import PluginRegistry, RegisteredPlugin
from .sandbox_observer import (
    SandboxCaptureError,
    SandboxNotRunningError,
    WindowsSandboxObserver,
)


class PluginProcessError(RuntimeError):
    """Raised when a plugin violates or cannot complete its process contract."""


class PluginTargetUnavailable(PluginProcessError):
    """Raised when the plugin is healthy but its target is not connected."""


class _ResponseLimitExceeded(RuntimeError):
    pass


class _ResponseEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal["1"]
    plugin_id: str
    request_id: UUID
    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = None


class _TargetDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: Literal["windows-sandbox"]
    target_name: Literal["Windows Sandbox"]
    connected: bool
    window_title: str
    input_enabled: Literal[False]


class _FrameResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: Literal["windows-sandbox"]
    media_type: Literal["image/png"]
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    data_base64: str


class ObserverPluginClient:
    protocol_version = "1"
    required_capabilities = frozenset(
        {"observation.describe", "observation.frame"}
    )

    def __init__(
        self,
        registry: PluginRegistry,
        plugin_id: str,
        *,
        timeout_seconds: float = 4.0,
        max_response_bytes: int = 12 * 1024 * 1024,
        max_frame_bytes: int = 8 * 1024 * 1024,
    ) -> None:
        self._registry = registry
        self.plugin_id = plugin_id
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._max_frame_bytes = max_frame_bytes

    def describe(self) -> _TargetDescription:
        result = self._invoke("describe", "observation.describe")
        try:
            description = _TargetDescription.model_validate(result)
        except ValidationError as error:
            raise PluginProcessError(
                "Observer plugin returned an invalid target description."
            ) from error
        self._verify_target_id(description.target_id)
        return description

    def capture_png(self) -> bytes:
        result = self._invoke("capture_frame", "observation.frame")
        try:
            frame = _FrameResult.model_validate(result)
            content = base64.b64decode(frame.data_base64, validate=True)
        except (ValidationError, ValueError) as error:
            raise PluginProcessError(
                "Observer plugin returned an invalid frame envelope."
            ) from error
        self._verify_target_id(frame.target_id)
        if len(content) > self._max_frame_bytes:
            raise PluginProcessError("Observer plugin frame exceeded its limit.")
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise PluginProcessError("Observer plugin frame was not a PNG.")
        digest = hashlib.sha256(content).hexdigest()
        if not hmac.compare_digest(digest, frame.sha256):
            raise PluginProcessError("Observer plugin frame digest did not match.")
        return content

    def _invoke(
        self,
        operation: str,
        required_capability: str,
    ) -> dict[str, Any]:
        registration = self._require_registration(required_capability)
        request_id = uuid4()
        request = {
            "protocol_version": self.protocol_version,
            "plugin_id": self.plugin_id,
            "request_id": str(request_id),
            "operation": operation,
            "payload": {},
        }
        request_bytes = (
            json.dumps(request, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
            + b"\n"
        )
        creation_flags = (
            subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        deadline = monotonic() + self._timeout_seconds
        try:
            process = subprocess.Popen(
                [sys.executable, str(registration.entrypoint)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=registration.directory,
                env=self._minimal_environment(),
                creationflags=creation_flags,
            )
        except OSError as error:
            raise PluginProcessError(
                "Observer plugin process could not be started."
            ) from error

        try:
            if process.stdin is None or process.stdout is None:
                raise PluginProcessError("Observer plugin pipes were unavailable.")
            process.stdin.write(request_bytes)
            process.stdin.close()
            with ThreadPoolExecutor(max_workers=1) as executor:
                output_future = executor.submit(
                    self._read_bounded,
                    process.stdout,
                    self._max_response_bytes,
                )
                try:
                    output = output_future.result(
                        timeout=max(0.01, deadline - monotonic())
                    )
                except FutureTimeout as error:
                    process.kill()
                    process.wait()
                    raise PluginProcessError(
                        "Observer plugin process did not complete within its boundary."
                    ) from error
                except _ResponseLimitExceeded as error:
                    process.kill()
                    process.wait()
                    raise PluginProcessError(
                        "Observer plugin response exceeded its limit."
                    ) from error
            try:
                return_code = process.wait(
                    timeout=max(0.01, deadline - monotonic())
                )
            except subprocess.TimeoutExpired as error:
                process.kill()
                process.wait()
                raise PluginProcessError(
                    "Observer plugin process did not complete within its boundary."
                ) from error
        except (BrokenPipeError, OSError) as error:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise PluginProcessError(
                "Observer plugin process communication failed."
            ) from error
        finally:
            if process.stdout is not None:
                process.stdout.close()

        if return_code != 0:
            raise PluginProcessError("Observer plugin process failed.")
        lines = output.splitlines()
        if len(lines) != 1:
            raise PluginProcessError(
                "Observer plugin must return exactly one JSON response."
            )
        try:
            payload = json.loads(lines[0].decode("utf-8"))
            response = _ResponseEnvelope.model_validate(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
            raise PluginProcessError(
                "Observer plugin returned an invalid response envelope."
            ) from error
        if (
            response.plugin_id != self.plugin_id
            or response.protocol_version != self.protocol_version
            or response.request_id != request_id
        ):
            raise PluginProcessError(
                "Observer plugin response identity did not match the request."
            )
        if not response.ok:
            if response.error == "target_not_running":
                raise PluginTargetUnavailable(
                    "Observer plugin reported that its target is not running."
                )
            detail = (response.error or "request failed")[:300]
            raise PluginProcessError(f"Observer plugin rejected the request: {detail}")
        if response.result is None:
            raise PluginProcessError("Observer plugin returned no result.")
        return response.result

    def _require_registration(
        self,
        required_capability: str,
    ) -> RegisteredPlugin:
        registration = self._registry.get(self.plugin_id)
        if registration is None:
            raise PluginProcessError("Configured observer plugin was not found.")
        manifest = registration.manifest
        if (
            not manifest.enabled
            or manifest.process_boundary != "out-of-process"
            or manifest.protocol_version != self.protocol_version
            or manifest.target_id != "windows-sandbox"
        ):
            raise PluginProcessError(
                "Configured observer plugin identity is not approved."
            )
        capabilities = set(manifest.capabilities)
        if (
            capabilities != self.required_capabilities
            or required_capability not in capabilities
        ):
            raise PluginProcessError(
                "Configured observer plugin lacks an approved capability."
            )
        return registration

    @staticmethod
    def _read_bounded(stream: BinaryIO, limit: int) -> bytes:
        output = bytearray()
        while True:
            remaining = limit + 1 - len(output)
            chunk = stream.read(min(64 * 1024, remaining))
            if not chunk:
                return bytes(output)
            output.extend(chunk)
            if len(output) > limit:
                raise _ResponseLimitExceeded

    @staticmethod
    def _minimal_environment() -> dict[str, str]:
        allowed = ("SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP")
        environment = {
            name: os.environ[name]
            for name in allowed
            if name in os.environ
        }
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PYTHONUTF8"] = "1"
        return environment

    @staticmethod
    def _verify_target_id(target_id: str) -> None:
        if target_id != "windows-sandbox":
            raise PluginProcessError(
                "Observer plugin returned an unapproved target identity."
            )


class OutOfProcessWindowsSandboxObserver:
    target_id = "windows-sandbox"
    target_name = "Windows Sandbox"
    window_title = "Windows Sandbox"

    def __init__(
        self,
        plugin: ObserverPluginClient,
        launcher: WindowsSandboxObserver,
    ) -> None:
        self._plugin = plugin
        self._launcher = launcher

    def describe(self) -> dict[str, object]:
        try:
            description = self._plugin.describe()
            connected = description.connected
            window_title = description.window_title
            observation_status = "ready"
        except PluginProcessError:
            connected = False
            window_title = self.window_title
            observation_status = "unavailable"
        return {
            "id": self.target_id,
            "name": self.target_name,
            "transport": "out-of-process-plugin",
            "mode": "read-only",
            "connected": connected,
            "window_title": window_title,
            "frame_endpoint": (
                f"/api/v1/targets/{self.target_id}/frame"
                if connected
                else None
            ),
            "input_enabled": False,
            "observer_plugin_id": self._plugin.plugin_id,
            "observer_process_boundary": "out-of-process",
            "observation_status": observation_status,
            "start_enabled": self.start_enabled,
            "start_endpoint": (
                f"/api/v1/targets/{self.target_id}/start"
                if self.start_enabled
                else None
            ),
        }

    @property
    def start_enabled(self) -> bool:
        return self._launcher.start_enabled

    def start(self) -> Literal["starting", "already_running"]:
        return self._launcher.start()

    def capture_png(self) -> bytes:
        try:
            return self._plugin.capture_png()
        except PluginTargetUnavailable as error:
            raise SandboxNotRunningError(
                "Windows Sandbox is not running."
            ) from error
        except PluginProcessError as error:
            raise SandboxCaptureError(
                "The out-of-process observer plugin could not capture a frame."
            ) from error
