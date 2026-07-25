"""Serve a built BoxBrain dashboard over loopback HTTPS."""

from __future__ import annotations

import argparse
import functools
import ssl
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class DashboardHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        super().end_headers()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--certfile", required=True, type=Path)
    parser.add_argument("--keyfile", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    handler = functools.partial(
        DashboardHandler,
        directory=str(args.directory.resolve()),
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(args.certfile, args.keyfile)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print(f"Serving BoxBrain dashboard on https://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
