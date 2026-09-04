"""Loopback control API; chat/voice are clients, never the execution controller."""
from __future__ import annotations

import hmac
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .ledger import Ledger, LedgerError
from .models import JobSpec


class FarmerApiServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], ledger: Ledger, token: str):
        self.ledger = ledger
        self.token = token
        super().__init__(address, FarmerApiHandler)


class FarmerApiHandler(BaseHTTPRequestHandler):
    server: FarmerApiServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {self.server.token}"
        return hmac.compare_digest(supplied, expected)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 1_048_576:
            raise ValueError("request body must be from 1 byte to 1 MiB")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        path = urlparse(self.path).path
        if path == "/monitor":
            host = urlparse("//" + self.headers.get("Host", "")).hostname
            if self.client_address[0] not in {"127.0.0.1", "::1"} or host not in {"127.0.0.1", "localhost", "::1"}:
                self._json(HTTPStatus.FORBIDDEN, {"error": "loopback_only"})
                return
            from .telemetry import monitor_snapshot
            try:
                self._json(HTTPStatus.OK, monitor_snapshot(self.server.ledger))
            except (LedgerError, ValueError, KeyError, TypeError):
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "decision_integrity_failure"})
            return
        if path == "/health":
            self._json(HTTPStatus.OK, {"status": "healthy", **self.server.ledger.stats()})
            return
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        try:
            if path == "/jobs":
                self._json(HTTPStatus.OK, {"jobs": self.server.ledger.list_jobs()})
                return
            if path == "/futures":
                self._json(HTTPStatus.OK, self.server.ledger.future_status())
                return
            if path.startswith("/futures/"):
                self._json(HTTPStatus.OK, self.server.ledger.future_status(path.split("/", 2)[2]))
                return
            if path.startswith("/jobs/"):
                self._json(HTTPStatus.OK, self.server.ledger.get_job(path.split("/", 2)[2]))
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except LedgerError as error:
            self._json(HTTPStatus.NOT_FOUND, {"error": str(error)})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        path = urlparse(self.path).path
        try:
            body = self._body()
            if path == "/jobs":
                job_id, created = self.server.ledger.submit(JobSpec.from_dict(body))
                self._json(HTTPStatus.CREATED if created else HTTPStatus.OK, {"job_id": job_id, "created": created})
                return
            if path.startswith("/jobs/") and path.endswith("/resume"):
                job_id = path.split("/")[2]
                self.server.ledger.resume(
                    job_id,
                    changed_dimension=str(body["changed_dimension"]),
                    note=str(body["note"]),
                )
                self._json(HTTPStatus.OK, self.server.ledger.get_job(job_id))
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except (KeyError, ValueError, json.JSONDecodeError) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except LedgerError as error:
            self._json(HTTPStatus.CONFLICT, {"error": str(error)})


def serve_in_thread(server: FarmerApiServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, name="aurum-farmer-api", daemon=True)
    thread.start()
    return thread
