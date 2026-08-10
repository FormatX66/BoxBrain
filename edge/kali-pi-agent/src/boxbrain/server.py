"""Local-only HTTP status service for BoxBrain."""

from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import secrets
import signal
import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

from boxbrain import __version__
from boxbrain.control import ControlServer
from boxbrain.connections import build_connection_map
from boxbrain.agent import agent_state
from boxbrain.diagnostics import DiagnosticError, TargetDiagnostics
from boxbrain.links import load_links
from boxbrain.hid_kvm import HidKvmClient, HidKvmError
from boxbrain.kvm_page import render_kvm_page
from boxbrain.patches import PatchManager
from boxbrain.scanner import AssessmentManager
from boxbrain.storage import Storage
from boxbrain.system import collect_status


LOG = logging.getLogger("boxbrain")
STARTED_MONOTONIC = time.monotonic()


def _human_bytes(value: int | None) -> str:
    if value is None:
        return "Unavailable"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return "Unavailable"


def _dashboard(status: dict[str, Any]) -> str:
    memory = status["memory"]
    storage = status["storage"]
    interfaces = status["network"]["interfaces"]
    connection_map = status.get("connection_map", {})
    connection_items = (
        connection_map.get("transports", [])
        if isinstance(connection_map, dict)
        else []
    )
    interface_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item['name']))}</td>"
        f"<td>{escape(str(item['state']))}</td>"
        f"<td>{escape(', '.join(item['addresses']) or 'None')}</td>"
        "</tr>"
        for item in interfaces
    )
    temperature = status["temperature_c"]
    temperature_text = f"{temperature:.1f} °C" if temperature is not None else "Unavailable"
    uptime_hours = status["system_uptime_seconds"]
    uptime_text = (
        f"{uptime_hours / 3600:.1f} hours" if uptime_hours is not None else "Unavailable"
    )
    latest = status.get("latest_assessment")
    links = status.get("target_links", [])
    agent = status.get("agent", {})
    if not isinstance(agent, dict):
        agent = {}
    link_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('hostname', 'unknown')))}</td>"
        f"<td>{escape(str(item.get('address', 'unknown')))}</td>"
        f"<td>{escape(str(item.get('status', 'unknown')))}</td>"
        f"<td>{escape(str(item.get('transport', 'unknown')))} / {escape(str(item.get('interface', 'unknown')))}</td>"
        f"<td>{escape(str(item.get('platform', 'unknown')))}</td>"
        f"<td>{escape(str(item.get('diagnostics', {}).get('overall', 'waiting')))}</td>"
        f"<td>{escape(str(item.get('diagnostics', {}).get('finding_count', 0)))}</td>"
        "</tr>"
        for item in links
    )
    if not link_rows:
        link_rows = '<tr><td colspan="7">No authorized target enrolled</td></tr>'
    connection_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('label', 'Unknown')))}</td>"
        f"<td>{escape(str(item.get('state', 'unknown')))}</td>"
        f"<td>{escape(', '.join(item.get('interfaces', [])) or 'None')}</td>"
        f"<td>{escape(str(item.get('target_count', 0)))}</td>"
        f"<td>{escape(', '.join(str(cap.get('id', 'unknown')) + ': ' + str(cap.get('state', 'unknown')) for cap in item.get('capabilities', []) if isinstance(cap, dict)))}</td>"
        "</tr>"
        for item in connection_items
        if isinstance(item, dict)
    )
    if not connection_rows:
        connection_rows = '<tr><td colspan="5">Connection inventory unavailable</td></tr>'
    target_panels = ""
    for item in links:
        diagnostic = item.get("diagnostics", {})
        if not isinstance(diagnostic, dict):
            diagnostic = {}
        findings = diagnostic.get("findings", [])
        if not isinstance(findings, list):
            findings = []
        finding_html = "".join(
            "<li>"
            f"<span class='severity {escape(str(finding.get('severity', 'low')))}'>"
            f"{escape(str(finding.get('severity', 'note')))}</span>"
            f"<strong>{escape(str(finding.get('title', 'Finding')))}</strong>"
            f"<span>{escape(str(finding.get('recommendation', 'Review this item.')))}</span>"
            "</li>"
            for finding in findings
            if isinstance(finding, dict)
        )
        if not finding_html:
            message = (
                "Read-only diagnostics are waiting to run."
                if diagnostic.get("status") != "completed"
                else "No optimization or repair priorities were found."
            )
            finding_html = f"<li><span>{escape(message)}</span></li>"
        metrics = diagnostic.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        disk_free = metrics.get("lowest_disk_free_percent")
        memory_free = metrics.get("memory_free_percent")
        disk_free_text = f"{disk_free}%" if disk_free is not None else "waiting"
        memory_free_text = f"{memory_free}%" if memory_free is not None else "waiting"
        target_panels += (
            "<article class='target'>"
            "<div class='target-head'>"
            f"<div><div class='label'>Managed system</div><h2>{escape(str(item.get('hostname', 'unknown')))}</h2></div>"
            f"<span class='target-status {escape(str(diagnostic.get('overall', 'waiting')))}'>{escape(str(diagnostic.get('overall', 'waiting')))}</span>"
            "</div>"
            "<div class='target-metrics'>"
            f"<span>Address <strong>{escape(str(item.get('address', 'unknown')))}</strong></span>"
            f"<span>Link <strong>{escape(str(item.get('status', 'unknown')))}</strong></span>"
            f"<span>Transport <strong>{escape(str(item.get('transport', 'unknown')))}</strong></span>"
            f"<span>Lowest disk free <strong>{escape(disk_free_text)}</strong></span>"
            f"<span>Memory free <strong>{escape(memory_free_text)}</strong></span>"
            f"<span>Last check <strong>{escape(str(diagnostic.get('last_run', 'waiting')))}</strong></span>"
            "</div>"
            f"<ul class='findings'>{finding_html}</ul>"
            "</article>"
        )
    recommendation_items = agent.get("recommendations", [])
    if not isinstance(recommendation_items, list):
        recommendation_items = []
    recommendation_html = "".join(
        "<article class='recommendation'>"
        f"<span class='priority {escape(str(item.get('priority', 'normal')))}'>{escape(str(item.get('priority', 'normal')))}</span>"
        f"<div><div class='label'>{escape(str(item.get('domain', 'system')))} / {escape(str(item.get('target', 'BoxBrain')))}</div>"
        f"<h3>{escape(str(item.get('title', 'Edge-agent recommendation')))}</h3>"
        f"<p>{escape(str(item.get('reason', 'Review this recommendation.')))}</p>"
        f"<p><strong>Proposed next step:</strong> {escape(str(item.get('proposed_action', 'Review before acting.')))}</p>"
        f"<p class='execution'>Execution: {escape(str(item.get('execution', 'operator-approved')))}</p></div>"
        "</article>"
        for item in recommendation_items
        if isinstance(item, dict)
    ) or "<p>No edge-agent recommendations are waiting.</p>"
    capability_items = agent.get("capabilities", [])
    if not isinstance(capability_items, list):
        capability_items = []
    capability_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('name', 'Capability')))}</td>"
        f"<td>{escape(str(item.get('domain', 'system')))}</td>"
        f"<td>{escape(str(item.get('mode', 'advisory')))}</td>"
        f"<td>{escape(str(item.get('status', 'unknown')))}</td>"
        "</tr>"
        for item in capability_items
        if isinstance(item, dict)
    )
    if latest:
        assessment_text = (
            f"{latest['status']} / {latest['asset_count']} assets / "
            f"{latest['finding_count']} findings"
        )
    else:
        assessment_text = "No assessments yet"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="refresh" content="10">
  <title>BoxBrain</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
    body {{ margin: 0; background: #07100d; color: #e9fff5; }}
    main {{ width: min(960px, calc(100% - 32px)); margin: 48px auto; }}
    header {{ display: flex; align-items: center; justify-content: space-between; gap: 24px; }}
    h1 {{ margin: 0; font-size: clamp(2rem, 7vw, 4.5rem); letter-spacing: -.06em; }}
    .eyebrow {{ color: #62f5a7; text-transform: uppercase; letter-spacing: .14em; font-weight: 700; }}
    .badge {{ border: 1px solid #2b7d55; border-radius: 999px; padding: 8px 14px; color: #8fffc0; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(190px,1fr)); gap: 14px; margin: 30px 0; }}
    .card, .panel {{ background: #0d1b16; border: 1px solid #203b30; border-radius: 18px; padding: 20px; }}
    .target {{ background: #0d1b16; border: 1px solid #203b30; border-radius: 18px; padding: 22px; margin-top: 14px; }}
    .target-head {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }}
    .target h2 {{ margin: 5px 0 0; }}
    .target-status, .severity {{ border-radius: 999px; padding: 5px 10px; text-transform: uppercase; font-size: .72rem; font-weight: 750; }}
    .target-status.healthy {{ color: #8fffc0; background: #133d29; }}
    .target-status.review, .severity.medium, .severity.low {{ color: #ffe59b; background: #594513; }}
    .target-status.attention, .severity.high, .severity.critical {{ color: #ffb7c0; background: #5d1c25; }}
    .target-status.waiting {{ color: #c8d2cd; background: #26352f; }}
    .target-metrics {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(180px,1fr)); gap: 10px; margin: 18px 0; color: #8eaa9e; }}
    .target-metrics strong {{ display: block; color: #e9fff5; margin-top: 3px; overflow-wrap: anywhere; }}
    .findings {{ list-style: none; margin: 0; padding: 0; }}
    .findings li {{ display: grid; grid-template-columns: auto 1fr; gap: 7px 12px; align-items: center; border-top: 1px solid #203b30; padding: 13px 0; }}
    .findings li span:last-child {{ grid-column: 2; color: #a9bbb3; }}
    .recommendation {{ display: grid; grid-template-columns: auto 1fr; gap: 14px; background: #0d1b16; border: 1px solid #203b30; border-radius: 16px; padding: 18px; margin-top: 12px; }}
    .recommendation h3 {{ margin: 5px 0 8px; }}
    .recommendation p {{ margin: 6px 0; color: #b8cac2; }}
    .recommendation .execution {{ color: #7f9c90; font-size: .85rem; }}
    .priority {{ align-self: start; border-radius: 999px; padding: 5px 10px; text-transform: uppercase; font-size: .72rem; font-weight: 750; }}
    .priority.urgent {{ color: #ffb7c0; background: #5d1c25; }}
    .priority.normal {{ color: #ffe59b; background: #594513; }}
    .priority.low {{ color: #a9d8ff; background: #173d5b; }}
    .label {{ color: #8eaa9e; font-size: .82rem; text-transform: uppercase; letter-spacing: .08em; }}
    a {{ color: #8fffc0; }}
    .value {{ margin-top: 8px; font-size: 1.35rem; font-weight: 650; overflow-wrap: anywhere; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 14px; }}
    th, td {{ text-align: left; padding: 12px 8px; border-bottom: 1px solid #203b30; }}
    th {{ color: #8eaa9e; font-size: .8rem; text-transform: uppercase; }}
    footer {{ color: #688075; margin-top: 24px; font-size: .85rem; }}
  </style>
</head>
<body>
<main>
  <header>
    <div><div class="eyebrow">Kali Pi edge agent</div><h1>BoxBrain</h1></div>
    <div class="badge">Healthy</div>
  </header>
  <div class="grid">
    <div class="card"><div class="label">Device</div><div class="value">{escape(status['hostname'])}</div></div>
    <div class="card"><div class="label">Model</div><div class="value">{escape(status['model'])}</div></div>
    <div class="card"><div class="label">Temperature</div><div class="value">{temperature_text}</div></div>
    <div class="card"><div class="label">System uptime</div><div class="value">{uptime_text}</div></div>
    <div class="card"><div class="label">Memory available</div><div class="value">{_human_bytes(memory['available_bytes'])}</div></div>
    <div class="card"><div class="label">Storage free</div><div class="value">{_human_bytes(storage['free_bytes'])}</div></div>
    <div class="card"><div class="label">Latest assessment</div><div class="value">{escape(assessment_text)}</div></div>
    <div class="card"><div class="label">Agent mode</div><div class="value">{escape(str(agent.get('operating_mode', 'advisory')))}</div></div>
    <div class="card"><div class="label">Recommendations</div><div class="value">{escape(str(agent.get('recommendation_count', 0)))}</div></div>
  </div>
  <section class="panel">
    <div class="label">Network interfaces</div>
    <table><thead><tr><th>Name</th><th>State</th><th>IPv4</th></tr></thead><tbody>{interface_rows}</tbody></table>
  </section>
  <section class="panel" style="margin-top:14px">
    <div class="label">Connection map</div>
    <table><thead><tr><th>Transport</th><th>State</th><th>Interfaces</th><th>Targets</th><th>Capabilities</th></tr></thead><tbody>{connection_rows}</tbody></table>
    <p><a href="/kvm">Open Morris PC keyboard and mouse controls</a></p>
  </section>
  <section class="panel" style="margin-top:14px">
    <div class="label">Managed systems</div>
    <table><thead><tr><th>Name</th><th>Address</th><th>Link</th><th>Transport</th><th>Platform</th><th>System status</th><th>Findings</th></tr></thead><tbody>{link_rows}</tbody></table>
  </section>
  <section style="margin-top:14px">
    {target_panels}
  </section>
  <section class="panel" style="margin-top:14px">
    <div class="label">Edge-agent recommendations</div>
    {recommendation_html}
  </section>
  <section class="panel" style="margin-top:14px">
    <div class="label">Edge-agent capabilities</div>
    <table><thead><tr><th>Capability</th><th>Domain</th><th>Mode</th><th>Status</th></tr></thead><tbody>{capability_rows}</tbody></table>
  </section>
  <footer>BoxBrain {__version__} / local management channel / refreshes every 10 seconds</footer>
</main>
</body>
</html>"""


class BoxBrainHandler(BaseHTTPRequestHandler):
    server_version = f"BoxBrain/{__version__}"
    sys_version = ""
    storage: Storage | None = None
    diagnostics: TargetDiagnostics | None = None

    @classmethod
    def status_payload(cls) -> dict[str, Any]:
        payload = collect_status(STARTED_MONOTONIC)
        payload["version"] = __version__
        payload["target_links"] = load_links(
            os.environ.get("BOXBRAIN_STATE_DIR", "/var/lib/boxbrain")
        )
        payload["connection_map"] = build_connection_map(
            payload.get("network"),
            payload["target_links"],
        )
        payload["latest_assessment"] = (
            cls.storage.latest_summary() if cls.storage is not None else None
        )
        payload["agent"] = agent_state(
            os.environ.get("BOXBRAIN_STATE_DIR", "/var/lib/boxbrain"),
            payload["latest_assessment"],
        )
        return payload

    def _send(
        self,
        body: bytes,
        content_type: str,
        status: int = 200,
        *,
        content_security_policy: str = "default-src 'none'; style-src 'unsafe-inline'",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", content_security_policy)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/health":
            payload = {
                "status": "ok",
                "service": "boxbrain",
                "version": __version__,
            }
            self._send(
                json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                "application/json; charset=utf-8",
            )
            return

        if parsed.path == "/api/v1/status":
            payload = self.status_payload()
            self._send(
                json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                "application/json; charset=utf-8",
            )
            return

        if parsed.path == "/api/v1/hid-kvm/status":
            try:
                payload = self.server.hid_kvm_client.request(  # type: ignore[attr-defined]
                    {"action": "status"}
                )
            except HidKvmError as error:
                payload = {"ok": False, "error": str(error)}
                response_status = 503
            else:
                response_status = 200
            self._send(
                json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                "application/json; charset=utf-8",
                response_status,
            )
            return

        if parsed.path == "/api/v1/jobs":
            jobs = self.storage.list_jobs(20) if self.storage is not None else []
            self._send(
                json.dumps({"jobs": jobs}, separators=(",", ":")).encode("utf-8"),
                "application/json; charset=utf-8",
            )
            return

        if parsed.path == "/api/v1/report/latest":
            latest = self.storage.latest_summary() if self.storage is not None else None
            if latest is None or self.storage is None:
                self._send(
                    b'{"error":"report_not_found"}',
                    "application/json; charset=utf-8",
                    404,
                )
                return
            payload = self.storage.build_report(latest["id"])
            self._send(
                json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                "application/json; charset=utf-8",
            )
            return

        if parsed.path == "/api/v1/target-report":
            address = parse_qs(parsed.query).get("address", [""])[0]
            if self.diagnostics is None:
                self._send(
                    b'{"error":"diagnostics_unavailable"}',
                    "application/json; charset=utf-8",
                    503,
                )
                return
            try:
                payload = self.diagnostics.latest_report(address)
            except DiagnosticError:
                self._send(
                    b'{"error":"target_report_not_found"}',
                    "application/json; charset=utf-8",
                    404,
                )
                return
            self._send(
                json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                "application/json; charset=utf-8",
            )
            return

        if parsed.path == "/":
            body = _dashboard(self.status_payload()).encode("utf-8")
            self._send(body, "text/html; charset=utf-8")
            return


        if parsed.path == "/kvm":
            body = render_kvm_page(
                self.server.hid_kvm_csrf_token  # type: ignore[attr-defined]
            ).encode("utf-8")
            self._send(
                body,
                "text/html; charset=utf-8",
                content_security_policy=(
                    "default-src 'none'; style-src 'unsafe-inline'; "
                    "script-src 'unsafe-inline'; connect-src 'self'"
                ),
            )
            return

        self._send(b'{"error":"not_found"}', "application/json; charset=utf-8", 404)

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path != "/api/v1/hid-kvm/input":
            self._send(b'{"error":"not_found"}', "application/json; charset=utf-8", 404)
            return
        if self.client_address[0] not in {"127.0.0.1", "::1"}:
            self._send(b'{"error":"loopback_required"}', "application/json; charset=utf-8", 403)
            return
        expected_token = self.server.hid_kvm_csrf_token  # type: ignore[attr-defined]
        if not secrets.compare_digest(self.headers.get("X-BoxBrain-CSRF", ""), expected_token):
            self._send(b'{"error":"csrf_rejected"}', "application/json; charset=utf-8", 403)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = -1
        if not 1 <= content_length <= 4096:
            self._send(b'{"error":"invalid_request_size"}', "application/json; charset=utf-8", 400)
            return
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self._send(b'{"error":"invalid_json"}', "application/json; charset=utf-8", 400)
            return
        if not isinstance(payload, dict):
            self._send(b'{"error":"invalid_request"}', "application/json; charset=utf-8", 400)
            return
        try:
            response = self.server.hid_kvm_client.request(payload)  # type: ignore[attr-defined]
        except HidKvmError as error:
            response = {"ok": False, "error": str(error)}
            response_status = 400
        else:
            response_status = 200
        self._send(
            json.dumps(response, separators=(",", ":")).encode("utf-8"),
            "application/json; charset=utf-8",
            response_status,
        )

    def log_message(self, format: str, *args: object) -> None:
        LOG.info("%s - %s", self.client_address[0], format % args)


def build_server(
    bind: str,
    port: int,
    storage: Storage | None = None,
    diagnostics: TargetDiagnostics | None = None,
    hid_kvm_client: HidKvmClient | None = None,
    hid_kvm_csrf_token: str | None = None,
) -> ThreadingHTTPServer:
    BoxBrainHandler.storage = storage
    BoxBrainHandler.diagnostics = diagnostics
    server = ThreadingHTTPServer((bind, port), BoxBrainHandler)
    server.hid_kvm_client = hid_kvm_client or HidKvmClient()  # type: ignore[attr-defined]
    server.hid_kvm_csrf_token = (  # type: ignore[attr-defined]
        hid_kvm_csrf_token or secrets.token_urlsafe(32)
    )
    return server


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("BOXBRAIN_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bind = os.environ.get("BOXBRAIN_BIND", "127.0.0.1")
    port = int(os.environ.get("BOXBRAIN_PORT", "8787"))
    state_directory = os.environ.get("BOXBRAIN_STATE_DIR", "/var/lib/boxbrain")
    control_socket = os.environ.get(
        "BOXBRAIN_CONTROL_SOCKET",
        "/run/boxbrain/control.sock",
    )
    storage = Storage(state_directory)
    storage.initialize()
    manager = AssessmentManager(storage)
    diagnostics = TargetDiagnostics(state_directory)
    patches = PatchManager(state_directory)
    control = ControlServer(control_socket, storage, manager, diagnostics, patches)
    control_thread = threading.Thread(
        target=control.serve_forever,
        name="boxbrain-control",
        daemon=True,
    )
    server = build_server(bind, port, storage, diagnostics)

    def stop_server(_signum: int, _frame: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()
        threading.Thread(target=control.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop_server)
    signal.signal(signal.SIGINT, stop_server)
    control_thread.start()
    LOG.info("BoxBrain %s listening on %s:%s", __version__, bind, port)
    try:
        server.serve_forever()
    finally:
        control.shutdown()
        control.server_close()
        control_thread.join(timeout=3)
        server.server_close()
        LOG.info("BoxBrain stopped")


if __name__ == "__main__":
    main()
