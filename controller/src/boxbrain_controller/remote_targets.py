from __future__ import annotations

import ipaddress
import os
import re
import shutil
import socket
import sqlite3
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from .models import (
    RemoteSessionRequest,
    RemoteSessionResult,
    RemoteTargetCreate,
    RemoteTargetProbeResult,
    RemoteTargetRecord,
    RemoteTransport,
)


_DEFAULT_PORTS: dict[RemoteTransport, int] = {
    "usb-c": 22,
    "ssh": 22,
    "winrm": 5986,
    "rdp": 3389,
    "telnet": 23,
}
_CAPABILITIES: dict[RemoteTransport, tuple[str, ...]] = {
    "usb-c": ("tcp-probe", "interactive-shell", "edge-diagnostics"),
    "ssh": ("tcp-probe", "interactive-shell"),
    "winrm": ("tcp-probe", "powershell-session"),
    "rdp": ("tcp-probe", "desktop-session"),
    "telnet": ("tcp-probe", "legacy-terminal"),
}
_CREDENTIAL_MODES = {
    "usb-c": "dedicated-key",
    "ssh": "ssh-agent",
    "winrm": "current-user",
    "rdp": "interactive",
    "telnet": "none",
}
_HOST_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$"
)
_USB_TARGET_ID = UUID("00000000-0000-0000-0000-000000000004")


class RemoteTargetError(ValueError):
    """Base error for invalid remote-target operations."""


class RemoteTargetNotFoundError(RemoteTargetError):
    """Raised when a remote target cannot be found."""


class RemoteTargetScopeError(RemoteTargetError):
    """Raised when a target resolves outside local/private scope."""


class RemoteSessionLaunchError(RuntimeError):
    """Raised when an operator session cannot be opened."""


Connector = Callable[[str, int, float], Any]
Resolver = Callable[[str, int], list[tuple[Any, ...]]]
Launcher = Callable[[list[str]], None]


def _connect(host: str, port: int, timeout: float) -> Any:
    return socket.create_connection((host, port), timeout=timeout)


def _resolve(host: str, port: int) -> list[tuple[Any, ...]]:
    return socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)


def _launch(command: list[str]) -> None:
    if shutil.which(command[0]) is None:
        raise RemoteSessionLaunchError(
            f"{command[0]} is not installed or available on PATH."
        )
    creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(  # noqa: S603 - command is a fixed argv list.
        command,
        close_fds=True,
        creationflags=creation_flags,
    )


class RemoteTargetService:
    def __init__(
        self,
        database_path: str | Path,
        *,
        probe_timeout_seconds: float = 1.5,
        usb_identity_file: str | Path | None = None,
        connector: Connector = _connect,
        resolver: Resolver = _resolve,
        launcher: Launcher = _launch,
    ) -> None:
        self.database_path = Path(database_path)
        self.probe_timeout_seconds = probe_timeout_seconds
        self.usb_identity_file = (
            Path(usb_identity_file).expanduser().resolve()
            if usb_identity_file
            else None
        )
        self._connector = connector
        self._resolver = resolver
        self._launcher = launcher
        self._lock = Lock()
        self._initialize()

    def list(self) -> list[RemoteTargetRecord]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, transport, host, port, username, built_in,
                       status, last_checked_at, created_at
                FROM remote_targets
                ORDER BY built_in DESC, name COLLATE NOCASE ASC
                """
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def get(self, target_id: UUID) -> RemoteTargetRecord:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, transport, host, port, username, built_in,
                       status, last_checked_at, created_at
                FROM remote_targets
                WHERE id = ?
                """,
                (str(target_id),),
            ).fetchone()
        if row is None:
            raise RemoteTargetNotFoundError("Remote target not found.")
        return self._record_from_row(row)

    def resolve_authorized(
        self,
        target_id: UUID,
    ) -> tuple[RemoteTargetRecord, str]:
        record = self.get(target_id)
        addresses = self._authorized_addresses(record.host, record.port)
        return record, addresses[0]

    def create(self, request: RemoteTargetCreate) -> RemoteTargetRecord:
        host = self._validate_host(request.host)
        if (
            request.transport == "telnet"
            and not request.insecure_transport_acknowledged
        ):
            raise RemoteTargetError(
                "Telnet is plaintext; acknowledge the insecure transport first."
            )
        created_at = datetime.now(UTC)
        record = RemoteTargetRecord(
            id=uuid4(),
            name=request.name,
            transport=request.transport,
            host=host,
            port=request.port or _DEFAULT_PORTS[request.transport],
            username=request.username,
            built_in=False,
            status="unknown",
            credential_mode=_CREDENTIAL_MODES[request.transport],
            capabilities=_CAPABILITIES[request.transport],
            last_checked_at=None,
            created_at=created_at,
        )
        try:
            with self._lock, self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO remote_targets (
                        id, name, transport, host, port, username, built_in,
                        status, last_checked_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, NULL, ?)
                    """,
                    (
                        str(record.id),
                        record.name,
                        record.transport,
                        record.host,
                        record.port,
                        record.username,
                        record.status,
                        record.created_at.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise RemoteTargetError(
                "That remote target is already registered."
            ) from error
        return record

    def delete(self, target_id: UUID) -> RemoteTargetRecord:
        record = self.get(target_id)
        if record.built_in:
            raise RemoteTargetError("The built-in USB-C target cannot be removed.")
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM remote_targets WHERE id = ?",
                (str(target_id),),
            )
        return record

    def probe(self, target_id: UUID) -> RemoteTargetProbeResult:
        record = self.get(target_id)
        checked_at = datetime.now(UTC)
        started_at = monotonic()
        resolved_address: str | None = None
        try:
            resolved = self._authorized_addresses(record.host, record.port)
            resolved_address = resolved[0]
            connection = self._connector(
                record.host,
                record.port,
                self.probe_timeout_seconds,
            )
            close = getattr(connection, "close", None)
            if callable(close):
                close()
            latency_ms = max(0, round((monotonic() - started_at) * 1000))
            result = RemoteTargetProbeResult(
                target_id=record.id,
                status="online",
                resolved_address=resolved_address,
                latency_ms=latency_ms,
                message=f"{record.transport.upper()} endpoint is reachable.",
                checked_at=checked_at,
            )
        except RemoteTargetScopeError:
            raise
        except (OSError, TimeoutError, ValueError):
            result = RemoteTargetProbeResult(
                target_id=record.id,
                status="offline",
                resolved_address=resolved_address,
                latency_ms=None,
                message=f"{record.transport.upper()} endpoint did not respond.",
                checked_at=checked_at,
            )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE remote_targets
                SET status = ?, last_checked_at = ?
                WHERE id = ?
                """,
                (result.status, result.checked_at.isoformat(), str(record.id)),
            )
        return result

    def open_session(
        self,
        target_id: UUID,
        request: RemoteSessionRequest,
    ) -> RemoteSessionResult:
        record = self.get(target_id)
        self._authorized_addresses(record.host, record.port)
        if record.transport == "telnet" and request.insecure_confirmation != (
            "I UNDERSTAND TELNET IS PLAINTEXT"
        ):
            raise RemoteTargetError(
                "Type I UNDERSTAND TELNET IS PLAINTEXT to open Telnet."
            )
        command, application = self._session_command(record)
        self._launcher(command)
        return RemoteSessionResult(
            target_id=record.id,
            status="opened",
            application=application,
            message=f"Opened an operator-controlled {application} session.",
        )

    def _session_command(
        self,
        record: RemoteTargetRecord,
    ) -> tuple[list[str], str]:
        if record.transport in {"usb-c", "ssh"}:
            destination = (
                f"{record.username}@{record.host}"
                if record.username
                else record.host
            )
            command = ["ssh", "-p", str(record.port)]
            if (
                record.transport == "usb-c"
                and self.usb_identity_file is not None
                and self.usb_identity_file.is_file()
            ):
                command.extend(["-i", str(self.usb_identity_file)])
            command.append(destination)
            return command, "SSH terminal"
        if record.transport == "rdp":
            return ["mstsc.exe", f"/v:{record.host}:{record.port}"], "RDP"
        if record.transport == "winrm":
            use_ssl = " -UseSSL" if record.port == 5986 else ""
            script = (
                f"Enter-PSSession -ComputerName '{record.host}' "
                f"-Port {record.port}{use_ssl}"
            )
            return [
                "powershell.exe",
                "-NoExit",
                "-NoProfile",
                "-Command",
                script,
            ], "WinRM PowerShell"
        return ["telnet.exe", record.host, str(record.port)], "Telnet"

    def _authorized_addresses(self, host: str, port: int) -> list[str]:
        try:
            results = self._resolver(host, port)
        except OSError as error:
            raise ValueError("Target host could not be resolved.") from error
        addresses: list[str] = []
        for result in results:
            sockaddr = result[4]
            if not isinstance(sockaddr, tuple) or not sockaddr:
                continue
            address = str(sockaddr[0]).split("%", maxsplit=1)[0]
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError:
                continue
            allowed = parsed.is_private or parsed.is_loopback or parsed.is_link_local
            if not allowed or parsed.is_multicast or parsed.is_unspecified:
                raise RemoteTargetScopeError(
                    "Remote targets must resolve only to private, loopback, or "
                    "link-local addresses."
                )
            if address not in addresses:
                addresses.append(address)
        if not addresses:
            raise ValueError("Target host did not resolve to an IP address.")
        return addresses

    @staticmethod
    def _validate_host(value: str) -> str:
        host = value.strip().lower()
        if (
            not _HOST_PATTERN.fullmatch(host)
            or ".." in host
            or host.startswith("-")
            or host.endswith("-")
        ):
            raise RemoteTargetError("Enter a valid IP address or hostname.")
        return host

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS remote_targets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    transport TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    username TEXT,
                    built_in INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'unknown',
                    last_checked_at TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(transport, host, port, username)
                );
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO remote_targets (
                    id, name, transport, host, port, username, built_in,
                    status, last_checked_at, created_at
                ) VALUES (?, ?, 'usb-c', '10.12.194.1', 22, 'kali', 1,
                          'unknown', NULL, ?)
                """,
                (str(_USB_TARGET_ID), "Kali Pi USB-C", created_at),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> RemoteTargetRecord:
        transport: RemoteTransport = row["transport"]
        return RemoteTargetRecord(
            id=row["id"],
            name=row["name"],
            transport=transport,
            host=row["host"],
            port=int(row["port"]),
            username=row["username"],
            built_in=bool(row["built_in"]),
            status=row["status"],
            credential_mode=_CREDENTIAL_MODES[transport],
            capabilities=_CAPABILITIES[transport],
            last_checked_at=(
                datetime.fromisoformat(row["last_checked_at"])
                if row["last_checked_at"]
                else None
            ),
            created_at=datetime.fromisoformat(row["created_at"]),
        )