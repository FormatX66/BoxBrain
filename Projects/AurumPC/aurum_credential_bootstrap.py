#!/usr/bin/env python3
"""Machine-sealed runtime credential bootstrap for Hopper.

The OpenAI key never enters Git or the browser. Hopper creates a root-owned
RSA receiver, publishes only its public half and fingerprint through the
read-only self-debug proof, and accepts one matching OAEP envelope from the
allowlisted BoxBrain trunk. Plaintext exists only in the root-owned runtime
credential file under /run.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

SCHEMA = "aurum.credential-bootstrap.v1"
ENVELOPE_SCHEMA = "aurum.credential-envelope.v1"
MACHINE = "hopper"
PURPOSE = "openai-api"
ALGORITHM = "rsa-oaep-sha256"
DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
DEFAULT_PRIVATE_ROOT = Path(os.environ.get("AURUM_CREDENTIAL_ROOT", "/var/lib/aurum/credentials"))
DEFAULT_RUNTIME_KEY = Path(
    os.environ.get("AURUM_OPENAI_KEY_FILE", "/run/credentials/aurum-gpt/openai_api_key")
)
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
ENVELOPE_RELATIVE = Path("Projects/AurumPC/credentials/hopper-openai-api.sealed.json")
MAX_KEY_BYTES = 400
MAX_CIPHERTEXT_BYTES = 512


class CredentialBootstrapError(RuntimeError):
    pass


def _atomic_bytes(path: Path, value: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        temporary.write_bytes(value)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_bytes(
        path,
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        0o600,
    )


def _openssl(*arguments: str, input_bytes: bytes | None = None) -> bytes:
    executable = shutil.which("openssl")
    if not executable:
        raise CredentialBootstrapError("openssl-unavailable")
    try:
        completed = subprocess.run(
            [executable, *arguments],
            input=input_bytes,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CredentialBootstrapError(f"openssl-failed:{type(exc).__name__}") from exc
    if completed.returncode != 0:
        raise CredentialBootstrapError("openssl-operation-refused")
    return completed.stdout


def _receiver_paths(private_root: Path) -> tuple[Path, Path]:
    return private_root / "hopper-openai-private.pem", private_root / "hopper-openai-public.pem"


def _public_receiver(public_path: Path) -> dict[str, Any]:
    try:
        public = public_path.read_bytes()
    except OSError as exc:
        raise CredentialBootstrapError("receiver-public-key-unavailable") from exc
    if not (public.startswith(b"-----BEGIN PUBLIC KEY-----") and public.rstrip().endswith(b"-----END PUBLIC KEY-----")):
        raise CredentialBootstrapError("receiver-public-key-invalid")
    return {
        "machine": MACHINE,
        "purpose": PURPOSE,
        "algorithm": ALGORITHM,
        "recipient_sha256": hashlib.sha256(public).hexdigest(),
        "public_key_b64": base64.b64encode(public).decode("ascii"),
    }


def ensure_receiver(private_root: Path = DEFAULT_PRIVATE_ROOT) -> dict[str, Any]:
    private_root.mkdir(parents=True, exist_ok=True)
    os.chmod(private_root, 0o700)
    private_path, public_path = _receiver_paths(private_root)
    if public_path.is_file():
        if not private_path.is_file():
            raise CredentialBootstrapError("receiver-private-key-missing")
        os.chmod(private_path, 0o600)
        os.chmod(public_path, 0o644)
        return _public_receiver(public_path)

    temporary_private = private_root / f".receiver-private.{os.getpid()}.{time.time_ns()}.tmp"
    temporary_public = private_root / f".receiver-public.{os.getpid()}.{time.time_ns()}.tmp"
    try:
        if private_path.is_file():
            private_source = private_path
        else:
            _openssl(
                "genpkey",
                "-algorithm",
                "RSA",
                "-pkeyopt",
                "rsa_keygen_bits:4096",
                "-out",
                str(temporary_private),
            )
            os.chmod(temporary_private, 0o600)
            os.replace(temporary_private, private_path)
            private_source = private_path
        public = _openssl("pkey", "-in", str(private_source), "-pubout")
        _atomic_bytes(temporary_public, public, 0o644)
        os.replace(temporary_public, public_path)
        os.chmod(private_path, 0o600)
        os.chmod(public_path, 0o644)
    finally:
        for temporary in (temporary_private, temporary_public):
            try:
                temporary.unlink()
            except OSError:
                pass
    return _public_receiver(public_path)


def _envelope(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise CredentialBootstrapError("credential-envelope-invalid") from exc
    if not isinstance(value, dict):
        raise CredentialBootstrapError("credential-envelope-invalid")
    required = {
        "schema",
        "machine",
        "purpose",
        "algorithm",
        "recipient_sha256",
        "ciphertext_b64",
        "ciphertext_sha256",
        "created_at",
    }
    if set(value) != required:
        raise CredentialBootstrapError("credential-envelope-fields-invalid")
    return value


def _runtime_key_valid(path: Path) -> bool:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    encoded = value.encode("utf-8", "strict")
    return bool(
        value.startswith("sk-")
        and 20 <= len(encoded) <= MAX_KEY_BYTES
        and not any(character.isspace() for character in value)
    )


def install(
    *,
    workspace: Path = DEFAULT_WORKSPACE,
    private_root: Path = DEFAULT_PRIVATE_ROOT,
    runtime_key: Path = DEFAULT_RUNTIME_KEY,
    state_dir: Path = DEFAULT_STATE,
) -> dict[str, Any]:
    receiver = ensure_receiver(private_root)
    envelope_path = workspace / ENVELOPE_RELATIVE
    envelope = _envelope(envelope_path)
    base = {
        "schema": SCHEMA,
        "machine": MACHINE,
        "purpose": PURPOSE,
        "transport": "machine-sealed",
        "receiver": receiver,
        "browser_credential": False,
        "plaintext_in_git": False,
        "credential_value_exposed": False,
    }
    if envelope is None:
        return {**base, "status": "awaiting-envelope", "runtime_credential": False}
    if (
        envelope.get("schema") != ENVELOPE_SCHEMA
        or envelope.get("machine") != MACHINE
        or envelope.get("purpose") != PURPOSE
        or envelope.get("algorithm") != ALGORITHM
        or envelope.get("recipient_sha256") != receiver["recipient_sha256"]
    ):
        raise CredentialBootstrapError("credential-envelope-recipient-mismatch")
    try:
        ciphertext = base64.b64decode(str(envelope.get("ciphertext_b64") or ""), validate=True)
    except (ValueError, TypeError) as exc:
        raise CredentialBootstrapError("credential-envelope-ciphertext-invalid") from exc
    if not 1 <= len(ciphertext) <= MAX_CIPHERTEXT_BYTES:
        raise CredentialBootstrapError("credential-envelope-ciphertext-invalid")
    ciphertext_sha256 = hashlib.sha256(ciphertext).hexdigest()
    if ciphertext_sha256 != envelope.get("ciphertext_sha256"):
        raise CredentialBootstrapError("credential-envelope-digest-mismatch")

    receipt_path = state_dir / "credential-openai.json"
    try:
        previous = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        previous = {}
    if previous.get("ciphertext_sha256") == ciphertext_sha256 and _runtime_key_valid(runtime_key):
        return {**base, "status": "ready", "runtime_credential": True, "ciphertext_sha256": ciphertext_sha256}

    private_path, _public_path = _receiver_paths(private_root)
    plaintext = _openssl(
        "pkeyutl",
        "-decrypt",
        "-inkey",
        str(private_path),
        "-pkeyopt",
        "rsa_padding_mode:oaep",
        "-pkeyopt",
        "rsa_oaep_md:sha256",
        input_bytes=ciphertext,
    )
    try:
        value = plaintext.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise CredentialBootstrapError("decrypted-credential-invalid") from exc
    encoded = value.encode("utf-8")
    if not (
        value.startswith("sk-")
        and 20 <= len(encoded) <= MAX_KEY_BYTES
        and not any(character.isspace() for character in value)
    ):
        raise CredentialBootstrapError("decrypted-credential-invalid")
    _atomic_bytes(runtime_key, encoded + b"\n", 0o600)
    receipt = {
        "schema": SCHEMA,
        "status": "ready",
        "machine": MACHINE,
        "purpose": PURPOSE,
        "transport": "machine-sealed",
        "recipient_sha256": receiver["recipient_sha256"],
        "ciphertext_sha256": ciphertext_sha256,
        "runtime_credential": True,
        "browser_credential": False,
        "plaintext_in_git": False,
        "credential_value_exposed": False,
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _atomic_json(receipt_path, receipt)
    return {**base, **receipt}


def status(**kwargs: Any) -> dict[str, Any]:
    try:
        return install(**kwargs)
    except CredentialBootstrapError as exc:
        return {
            "schema": SCHEMA,
            "machine": MACHINE,
            "purpose": PURPOSE,
            "status": "unavailable",
            "reason": str(exc),
            "transport": "machine-sealed",
            "runtime_credential": False,
            "browser_credential": False,
            "plaintext_in_git": False,
            "credential_value_exposed": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Aurum Hopper sealed credential bootstrap")
    parser.add_argument("command", choices=("status", "install"))
    args = parser.parse_args()
    result = status() if args.command == "status" else install()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") in {"ready", "awaiting-envelope"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
