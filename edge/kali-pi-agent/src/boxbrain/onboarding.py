"""Read-only onboarding for USB-C and explicit private-network target links."""

from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from boxbrain import __version__


LOG = logging.getLogger("boxbrain.onboarding")
CONTENT_DIRECTORY = Path(
    os.environ.get("BOXBRAIN_ONBOARDING_DIR", "/opt/boxbrain/onboarding")
)
FILES = {
    "/windows-link.ps1": ("windows-link.ps1", "text/plain; charset=utf-8"),
    "/windows-wifi-provision.ps1": (
        "windows-wifi-provision.ps1",
        "text/plain; charset=utf-8",
    ),
    "/linux-link.sh": ("linux-link.sh", "text/plain; charset=utf-8"),
    "/boxbrain-target.pub": ("boxbrain-target.pub", "text/plain; charset=utf-8"),
    "/install-morris-vnc.ps1": (
        "install-morris-vnc.ps1",
        "text/plain; charset=utf-8",
    ),
    "/install-morri-profile.ps1": (
        "install-morri-profile.ps1",
        "text/plain; charset=utf-8",
    ),
    "/tightvnc-2.8.88-gpl-setup-64bit.msi": (
        "tightvnc-2.8.88-gpl-setup-64bit.msi",
        "application/octet-stream",
    ),
}


def _page(host: str) -> bytes:
    origin = f"http://{host}"
    windows = (
        f"Invoke-WebRequest {origin}/windows-link.ps1 -OutFile "
        "$env:TEMP\\boxbrain-link.ps1; "
        "PowerShell -ExecutionPolicy Bypass -File $env:TEMP\\boxbrain-link.ps1"
    )
    linux = (
        f"curl -fsS {origin}/linux-link.sh -o /tmp/boxbrain-link.sh && "
        "sudo sh /tmp/boxbrain-link.sh"
    )
    windows_network = (
        "PowerShell -ExecutionPolicy Bypass -File "
        "$env:TEMP\\boxbrain-link.ps1 "
        "-BoxBrainAddress 10.12.194.1,<PI-WIFI-IP>"
    )
    linux_network = (
        "sudo env BOXBRAIN_AGENT_ADDRESS=10.12.194.1,<PI-WIFI-IP> "
        "sh /tmp/boxbrain-link.sh"
    )
    enroll_network = "boxbrainctl add-target <TARGET-WIFI-IP> --authorized"
    windows_wifi = (
        f"Invoke-WebRequest {origin}/windows-wifi-provision.ps1 -OutFile "
        "$env:TEMP\\boxbrain-wifi.ps1; "
        "PowerShell -ExecutionPolicy Bypass -File $env:TEMP\\boxbrain-wifi.ps1"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Connect to BoxBrain</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
    body {{ margin: 0; background: #07100d; color: #e9fff5; }}
    main {{ width: min(820px, calc(100% - 32px)); margin: 44px auto; }}
    h1 {{ font-size: clamp(2.2rem, 7vw, 4.4rem); letter-spacing: -.055em; margin: 8px 0; }}
    .eyebrow {{ color: #62f5a7; text-transform: uppercase; letter-spacing: .14em; font-weight: 700; }}
    .card {{ background: #0d1b16; border: 1px solid #203b30; border-radius: 18px; padding: 22px; margin-top: 18px; }}
    code {{ display: block; white-space: pre-wrap; overflow-wrap: anywhere; background: #06100c; border-radius: 12px; padding: 16px; color: #a9ffd0; }}
    a {{ color: #8fffc0; }}
    .warning {{ color: #ffd88f; }}
  </style>
</head>
<body><main>
  <div class="eyebrow">USB-C + private-network onboarding</div>
  <h1>Connect this computer to BoxBrain</h1>
  <p>This page cannot change your computer by itself. Choose the matching script,
  inspect it, run it as administrator/root, and type <strong>AUTHORIZE</strong>
  when it asks. The link creates a non-administrator account named
  <strong>boxbrain-link</strong> and permits only BoxBrain's SSH key. USB-C
  targets are discovered automatically after authorization.</p>
  <p class="warning">Only authorize computers and networks you own or have
  explicit permission to assess.</p>
  <section class="card"><h2>Windows</h2>
    <p><a href="/windows-link.ps1">Download the Windows link script</a>, then run:</p>
    <code>{escape(windows)}</code>
  </section>
  <section class="card"><h2>Linux</h2>
    <p><a href="/linux-link.sh">Download the Linux link script</a>, then run:</p>
    <code>{escape(linux)}</code>
  </section>
  <section class="card"><h2>Continue over Wi-Fi or Ethernet</h2>
    <p>Rerun the target script with the Pi's exact private Wi-Fi/Ethernet address
    allowed through the target firewall:</p>
    <code>Windows: {escape(windows_network)}
Linux: {escape(linux_network)}</code>
    <p>Then enroll the target's private address from the Pi:</p>
    <code>{escape(enroll_network)}</code>
  </section>
  <section class="card"><h2>Provision the Pi from this Windows Wi-Fi</h2>
    <p>Run this separately as administrator. It reads only the current profile
    after explicit approval and streams the passphrase through SSH over USB-C.
    The restricted target account is also checked to confirm that it cannot
    retrieve the saved key.</p>
    <code>{escape(windows_wifi)}</code>
  </section>
  <p>BoxBrain {__version__} | read-only onboarding service</p>
</main></body></html>""".encode("utf-8")


class OnboardingHandler(BaseHTTPRequestHandler):
    server_version = f"BoxBrain-Onboarding/{__version__}"
    sys_version = ""

    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in {"/", "/index.html"}:
            host = self.headers.get("Host", "10.12.194.1:8788")
            self._send(_page(host), "text/html; charset=utf-8")
            return
        if path == "/health":
            self._send(
                b'{"status":"ok","service":"boxbrain-onboarding"}',
                "application/json; charset=utf-8",
            )
            return
        item = FILES.get(path)
        if item is not None:
            filename, content_type = item
            try:
                body = (CONTENT_DIRECTORY / filename).read_bytes()
            except OSError:
                self._send(b"not found\n", "text/plain; charset=utf-8", 404)
                return
            self._send(body, content_type)
            return
        self._send(b"not found\n", "text/plain; charset=utf-8", 404)

    def log_message(self, format: str, *args: object) -> None:
        LOG.info("%s - %s", self.client_address[0], format % args)


def build_server(bind: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((bind, port), OnboardingHandler)


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("BOXBRAIN_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bind = os.environ.get("BOXBRAIN_ONBOARDING_BIND", "10.12.194.1")
    port = int(os.environ.get("BOXBRAIN_ONBOARDING_PORT", "8788"))
    server = build_server(bind, port)
    LOG.info("BoxBrain onboarding listening on %s:%s", bind, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
