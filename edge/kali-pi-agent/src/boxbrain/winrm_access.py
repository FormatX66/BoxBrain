"""Persistent WinRM access established through an authorized BoxLink SSH session."""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from boxbrain.links import target_id_for


WINRM_PORT = 5985
WINRM_VERIFY_INTERVAL = int(os.environ.get("BOXBRAIN_WINRM_VERIFY_INTERVAL", "300"))
_KEY_CONTEXT = b"BoxBrain-WinRM-Credential-v1"
_BOOTSTRAP_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$path = Join-Path $env:USERPROFILE '.boxbrain\winrm-bootstrap.json'
if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
    throw 'The authorized WinRM bootstrap is unavailable.'
}
$value = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
$entropy = [Text.Encoding]::UTF8.GetBytes('BoxBrain-WinRM-Bootstrap-v1')
$protected = [Convert]::FromBase64String([string]$value.protected_password)
$plain = [Security.Cryptography.ProtectedData]::Unprotect(
    $protected,
    $entropy,
    [Security.Cryptography.DataProtectionScope]::LocalMachine
)
try {
    [ordered]@{
        schema_version = [int]$value.schema_version
        username = [string]$value.username
        password_b64 = [Convert]::ToBase64String($plain)
        port = [int]$value.port
        use_ssl = [bool]$value.use_ssl
        authorized_at_utc = [string]$value.authorized_at_utc
    } | ConvertTo-Json -Compress
}
finally {
    [Array]::Clear($plain, 0, $plain.Length)
}
"""


class WinRMAccessError(RuntimeError):
    """Raised when an authorized WinRM connection cannot be captured or verified."""


Runner = Callable[..., subprocess.CompletedProcess[str]]
SessionFactory = Callable[..., Any]


def _safe_address(raw: object) -> str:
    try:
        address = ipaddress.ip_address(str(raw))
    except ValueError as error:
        raise WinRMAccessError("The WinRM target address is invalid.") from error
    if (
        address.version != 4
        or not (address.is_private or address.is_link_local)
        or address.is_multicast
        or address.is_unspecified
    ):
        raise WinRMAccessError("WinRM access is restricted to private IPv4 targets.")
    return str(address)


def _credential_path(state_directory: str | Path, target_id: str) -> Path:
    return Path(state_directory) / "credentials" / f"{target_id}.winrm"


def _fernet(identity_file: str | Path) -> Any:
    try:
        from cryptography.fernet import Fernet
    except ImportError as error:
        raise WinRMAccessError("The node credential-encryption library is unavailable.") from error
    try:
        identity = Path(identity_file).read_bytes()
    except OSError as error:
        raise WinRMAccessError("The node target identity is unavailable.") from error
    if not identity:
        raise WinRMAccessError("The node target identity is empty.")
    key = hashlib.sha256(_KEY_CONTEXT + identity).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _atomic_private_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _save_profile(
    state_directory: str | Path,
    identity_file: str | Path,
    target_id: str,
    profile: dict[str, Any],
) -> None:
    secret = json.dumps(profile, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ciphertext = _fernet(identity_file).encrypt(secret)
    container = {
        "schema_version": 1,
        "target_id": target_id,
        "captured_at_utc": _now(),
        "ciphertext": ciphertext.decode("ascii"),
    }
    _atomic_private_write(
        _credential_path(state_directory, target_id),
        (json.dumps(container, separators=(",", ":"), sort_keys=True) + "\n").encode(
            "utf-8"
        ),
    )


def _load_profile(
    state_directory: str | Path,
    identity_file: str | Path,
    target_id: str,
) -> dict[str, Any] | None:
    path = _credential_path(state_directory, target_id)
    if not path.is_file():
        return None
    try:
        from cryptography.fernet import InvalidToken
    except ImportError as error:
        raise WinRMAccessError("The node credential-encryption library is unavailable.") from error
    try:
        container = json.loads(path.read_text(encoding="utf-8"))
        ciphertext = str(container["ciphertext"]).encode("ascii")
        profile = json.loads(_fernet(identity_file).decrypt(ciphertext).decode("utf-8"))
    except (OSError, UnicodeError, ValueError, KeyError, json.JSONDecodeError, InvalidToken) as error:
        raise WinRMAccessError("The saved WinRM credential could not be opened.") from error
    if not isinstance(profile, dict):
        raise WinRMAccessError("The saved WinRM credential is invalid.")
    return profile


def _capture_bootstrap(
    address: str,
    identity_file: str | Path,
    known_hosts_file: str | Path,
    *,
    runner: Runner,
) -> dict[str, Any]:
    encoded = base64.b64encode(_BOOTSTRAP_SCRIPT.encode("utf-16-le")).decode("ascii")
    command = [
        "ssh",
        "-i",
        str(identity_file),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts_file}",
        f"boxbrain-link@{address}",
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-OutputFormat",
        "Text",
        "-EncodedCommand",
        encoded,
    ]
    try:
        result = runner(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=12,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise WinRMAccessError("The node could not retrieve the WinRM bootstrap.") from error
    if result.returncode != 0:
        raise WinRMAccessError("The authorized WinRM bootstrap is not ready on the target.")
    try:
        value = json.loads(result.stdout.strip())
        password = base64.b64decode(str(value.pop("password_b64")), validate=True).decode(
            "utf-8"
        )
    except (UnicodeError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise WinRMAccessError("The target returned an invalid WinRM bootstrap.") from error
    if not isinstance(value, dict) or int(value.get("schema_version", 0)) != 1:
        raise WinRMAccessError("The target returned an unsupported WinRM bootstrap.")
    if not 32 <= len(password) <= 512:
        raise WinRMAccessError("The target returned an invalid WinRM credential.")
    username = str(value.get("username", ""))
    if not username.lower().endswith("\\boxbrain-link"):
        raise WinRMAccessError("The WinRM bootstrap is not mapped to BoxBrain's account.")
    if int(value.get("port", 0)) != WINRM_PORT or value.get("use_ssl") is not False:
        raise WinRMAccessError("The target WinRM endpoint is not the required listener.")
    value["password"] = password
    return value


def _verify(
    address: str,
    profile: dict[str, Any],
    *,
    session_factory: SessionFactory | None,
) -> str:
    if session_factory is None:
        try:
            import winrm
        except ImportError as error:
            raise WinRMAccessError("The node WinRM client is unavailable.") from error
        session_factory = winrm.Session
    endpoint = f"http://{address}:{int(profile['port'])}/wsman"
    try:
        session = session_factory(
            endpoint,
            auth=(str(profile["username"]), str(profile["password"])),
            transport="ntlm",
            message_encryption="always",
        )
        result = session.run_ps("$env:COMPUTERNAME")
    except Exception as error:
        raise WinRMAccessError("The target rejected the saved WinRM connection.") from error
    if int(getattr(result, "status_code", 1)) != 0:
        raise WinRMAccessError("The target rejected the WinRM PowerShell probe.")
    hostname = bytes(getattr(result, "std_out", b"")).decode("utf-8", errors="replace").strip()
    expected_hostname = str(profile["username"]).split("\\", maxsplit=1)[0]
    if not hostname or hostname.casefold() != expected_hostname.casefold():
        raise WinRMAccessError("The WinRM endpoint identity did not match the authorized computer.")
    return hostname


def ensure_winrm_access(
    link: dict[str, Any],
    state_directory: str | Path,
    identity_file: str | Path,
    known_hosts_file: str | Path,
    *,
    runner: Runner = subprocess.run,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    """Capture, encrypt, authenticate, and describe an authorized WinRM path."""

    platform = str(link.get("platform", ""))
    if "windows" not in platform.casefold() and "microsoft" not in platform.casefold():
        raise WinRMAccessError("WinRM enrollment is supported only for Windows targets.")
    address = _safe_address(link.get("address"))
    target_id = target_id_for(link)
    profile = _load_profile(state_directory, identity_file, target_id)
    if profile is None:
        profile = _capture_bootstrap(
            address,
            identity_file,
            known_hosts_file,
            runner=runner,
        )
        _save_profile(state_directory, identity_file, target_id, profile)
    hostname = _verify(
        address,
        profile,
        session_factory=session_factory,
    )
    now = _now()
    return {
        "id": "winrm",
        "friendly_name": "WinRM",
        "connection_type": "winrm",
        "description": "Node-managed Windows PowerShell over authenticated WinRM",
        "status": "available",
        "address": address,
        "ports": [WINRM_PORT],
        "transport": "ntlm-message-encrypted",
        "credential_mode": "node-encrypted",
        "hostname": hostname,
        "authorized_at": profile.get("authorized_at_utc"),
        "last_seen_at": now,
        "last_verified_at": now,
    }


def verify_saved_winrm(
    state_directory: str | Path,
    identity_file: str | Path,
    computer: dict[str, Any],
    *,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    """Verify a previously enrolled WinRM path without using SSH."""

    target_id = target_id_for(computer)
    profile = _load_profile(state_directory, identity_file, target_id)
    if profile is None:
        raise WinRMAccessError("No node-protected WinRM credential is saved for this computer.")
    address = _safe_address(computer.get("address"))
    hostname = _verify(
        address,
        profile,
        session_factory=session_factory,
    )
    return {"connected": True, "hostname": hostname, "address": address, "port": WINRM_PORT}


def verification_due(connection: dict[str, Any] | None, now: datetime | None = None) -> bool:
    if not isinstance(connection, dict):
        return True
    checked = connection.get("last_verified_at")
    if not isinstance(checked, str):
        return True
    try:
        value = datetime.fromisoformat(checked.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return True
    current = now or datetime.now(timezone.utc)
    return (current - value).total_seconds() >= max(30, WINRM_VERIFY_INTERVAL)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
