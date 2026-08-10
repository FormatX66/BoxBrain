"""Local Unix-socket control plane for BoxBrain."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socketserver
from typing import Any

from boxbrain.agent import agent_state
from boxbrain.diagnostics import TargetDiagnostics
from boxbrain.enrollment import enroll_target
from boxbrain.links import load_links
from boxbrain.patches import PatchManager
from boxbrain.scanner import AssessmentManager
from boxbrain.storage import Storage


MAX_REQUEST_BYTES = 64 * 1024
_HAS_UNIX_SERVER = hasattr(socketserver, "ThreadingUnixStreamServer")
_ControlServerBase = getattr(
    socketserver,
    "ThreadingUnixStreamServer",
    socketserver.ThreadingTCPServer,
)


class ControlHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            self._send({"ok": False, "error": "request_too_large"})
            return
        try:
            request = json.loads(raw.decode("utf-8"))
            response = self.server.dispatch(request)  # type: ignore[attr-defined]
        except (UnicodeError, json.JSONDecodeError):
            response = {"ok": False, "error": "invalid_json"}
        except Exception as error:
            response = {"ok": False, "error": str(error)[:1000]}
        self._send(response)

    def _send(self, payload: dict[str, Any]) -> None:
        self.wfile.write(json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n")


class ControlServer(_ControlServerBase):  # type: ignore[misc,valid-type]
    daemon_threads = True

    def __init__(
        self,
        socket_path: str,
        storage: Storage,
        manager: AssessmentManager,
        diagnostics: TargetDiagnostics,
        patches: PatchManager,
    ) -> None:
        if not _HAS_UNIX_SERVER:
            raise RuntimeError("BoxBrain control sockets require Unix-domain socket support.")
        self.socket_path = Path(socket_path)
        self.storage = storage
        self.manager = manager
        self.diagnostics = diagnostics
        self.patches = patches
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self.socket_path.unlink(missing_ok=True)
        super().__init__(str(self.socket_path), ControlHandler)
        os.chmod(self.socket_path, 0o660)

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        if action == "assess":
            job = self.manager.submit(
                str(request.get("target", "")),
                str(request.get("profile", "discovery")),
                str(request.get("authorization", "")),
            )
            return {"ok": True, "job": job}
        if action == "jobs":
            return {
                "ok": True,
                "jobs": self.storage.list_jobs(int(request.get("limit", 20))),
            }
        if action == "job":
            job = self.storage.get_job(str(request.get("job_id", "")))
            if job is None:
                return {"ok": False, "error": "job_not_found"}
            return {"ok": True, "job": job}
        if action == "report":
            job_id = str(request.get("job_id", "latest"))
            if job_id == "latest":
                latest = self.storage.latest_summary()
                if latest is None:
                    return {"ok": False, "error": "report_not_found"}
                job_id = latest["id"]
            try:
                report = self.storage.build_report(job_id)
            except KeyError:
                return {"ok": False, "error": "report_not_found"}
            return {"ok": True, "report": report}
        if action == "targets":
            return {
                "ok": True,
                "targets": load_links(str(self.diagnostics.state_directory)),
            }
        if action == "add_target":
            target = enroll_target(
                str(request.get("address", "")),
                str(request.get("transport", "network-ssh")),
                str(request.get("authorization", "")),
            )
            return {"ok": True, "target": target}
        if action in {"agent", "controller"}:
            response_key = "controller" if action == "controller" else "agent"
            return {
                "ok": True,
                response_key: agent_state(
                    str(self.diagnostics.state_directory),
                    self.storage.latest_summary(),
                ),
            }
        if action == "diagnose":
            report = self.diagnostics.diagnose(
                str(request.get("address", "")),
                str(request.get("authorization", "")),
            )
            return {"ok": True, "report": report}
        if action == "target_report":
            report = self.diagnostics.latest_report(str(request.get("address", "")))
            return {"ok": True, "report": report}
        if action == "patches":
            return {"ok": True, "patches": self.patches.list()}
        if action == "deliver_patch":
            receipt = self.patches.deliver(
                str(request.get("reference", "")),
                str(request.get("authorization", "")),
                str(request.get("confirmation", "")),
            )
            return {"ok": True, "receipt": receipt}
        return {"ok": False, "error": "unsupported_action"}

    def server_close(self) -> None:
        super().server_close()
        self.socket_path.unlink(missing_ok=True)
