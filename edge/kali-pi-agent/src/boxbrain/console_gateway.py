"""Serve the Pi console and loopback-proxy the bounded HID KVM surface."""

from __future__ import annotations

import argparse
from http.client import HTTPConnection
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


MAX_PROXY_BODY = 4096
_PROXY_PATHS = {"/kvm", "/api/v1/hid-kvm/status", "/api/v1/hid-kvm/input"}
_VIDEO_PATH = "/api/v1/kvm/video"
_RESPONSE_HEADERS = {
    "content-type",
    "cache-control",
    "content-security-policy",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
}


class ConsoleGatewayHandler(SimpleHTTPRequestHandler):
    server_version = "BoxBrainConsole/1"
    sys_version = ""

    def _proxy(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path not in _PROXY_PATHS:
            self.send_error(404)
            return
        body = b""
        if self.command == "POST":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = -1
            if not 1 <= content_length <= MAX_PROXY_BODY:
                self.send_error(400, "Invalid request size")
                return
            body = self.rfile.read(content_length)
        headers = {"Host": "127.0.0.1"}
        for name in ("Content-Type", "X-BoxBrain-CSRF"):
            if self.headers.get(name):
                headers[name] = self.headers[name]
        backend_host, backend_port = self.server.backend  # type: ignore[attr-defined]
        connection = HTTPConnection(backend_host, backend_port, timeout=3)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read(MAX_PROXY_BODY * 64 + 1)
            if len(payload) > MAX_PROXY_BODY * 64:
                self.send_error(502, "Backend response too large")
                return
            self.send_response(response.status)
            for name, value in response.getheaders():
                if name.lower() in _RESPONSE_HEADERS:
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        except OSError:
            self.send_error(502, "BoxBrain control service unavailable")
        finally:
            connection.close()

    def _proxy_video(self) -> None:
        backend_host, backend_port, backend_path = (  # type: ignore[attr-defined]
            self.server.video_backend
        )
        connection = HTTPConnection(backend_host, backend_port, timeout=10)
        headers_sent = False
        try:
            connection.request("GET", backend_path, headers={"Host": "127.0.0.1"})
            response = connection.getresponse()
            self.send_response(response.status)
            for name, value in response.getheaders():
                if name.lower() == "content-type":
                    self.send_header(name, value)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            headers_sent = True
            if self.command == "HEAD":
                return
            while chunk := response.read1(64 * 1024):
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except OSError:
            if not headers_sent:
                self.send_error(502, "Capture-card video unavailable")
        finally:
            connection.close()

    def _serve_static_or_kvm_root(self) -> None:
        parsed = urlsplit(self.path)
        if self.server.kvm_only:  # type: ignore[attr-defined]
            if parsed.path == "/":
                self.send_response(302)
                self.send_header("Location", "/kvm")
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif parsed.path == "/current" or parsed.path.startswith("/current/"):
                root = Path(self.directory).resolve()
                allowed = (root / "current").resolve()
                requested = Path(self.translate_path(parsed.path)).resolve()
                try:
                    requested.relative_to(allowed)
                except ValueError:
                    self.send_error(404)
                    return
                if self.command == "GET":
                    super().do_GET()
                else:
                    super().do_HEAD()
            else:
                self.send_error(404)
            return
        if self.command == "GET":
            super().do_GET()
        else:
            super().do_HEAD()

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == _VIDEO_PATH:
            self._proxy_video()
        elif path in _PROXY_PATHS:
            self._proxy()
        else:
            self._serve_static_or_kvm_root()

    def do_HEAD(self) -> None:
        path = urlsplit(self.path).path
        if path == _VIDEO_PATH:
            self._proxy_video()
        elif path in _PROXY_PATHS:
            self._proxy()
        else:
            self._serve_static_or_kvm_root()

    def do_POST(self) -> None:
        self._proxy()


def build_gateway(
    bind: str,
    port: int,
    directory: Path,
    backend_host: str = "127.0.0.1",
    backend_port: int = 8787,
    video_host: str = "127.0.0.1",
    video_port: int = 8082,
    video_path: str = "/stream",
    kvm_only: bool = False,
) -> ThreadingHTTPServer:
    handler = lambda *args, **kwargs: ConsoleGatewayHandler(  # noqa: E731
        *args,
        directory=str(directory),
        **kwargs,
    )
    server = ThreadingHTTPServer((bind, port), handler)
    server.backend = (backend_host, backend_port)  # type: ignore[attr-defined]
    server.video_backend = (  # type: ignore[attr-defined]
        video_host,
        video_port,
        video_path,
    )
    server.kvm_only = kvm_only  # type: ignore[attr-defined]
    return server


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--backend", default="http://127.0.0.1:8787")
    parser.add_argument("--video-backend", default="http://127.0.0.1:8082/stream")
    parser.add_argument("--kvm-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    address = ipaddress.ip_address(arguments.bind)
    if not (address.is_private or address.is_link_local):
        raise SystemExit("Console bind address must be private or link-local.")
    if not 1024 <= arguments.port <= 65535:
        raise SystemExit("Console port must be from 1024 through 65535.")
    if not arguments.directory.is_dir():
        raise SystemExit("Console directory does not exist.")
    backend = urlsplit(arguments.backend)
    if backend.scheme != "http" or backend.hostname not in {"127.0.0.1", "::1"}:
        raise SystemExit("The BoxBrain backend must be loopback HTTP.")
    video_backend = urlsplit(arguments.video_backend)
    if (
        video_backend.scheme != "http"
        or video_backend.hostname not in {"127.0.0.1", "::1"}
        or video_backend.path != "/stream"
    ):
        raise SystemExit("The KVM video backend must be the loopback /stream endpoint.")
    server = build_gateway(
        str(address),
        arguments.port,
        arguments.directory,
        backend.hostname,
        backend.port or 80,
        video_backend.hostname,
        video_backend.port or 80,
        video_backend.path,
        arguments.kvm_only,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
