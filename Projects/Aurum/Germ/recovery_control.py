#!/usr/bin/env python3
"""Cryptographic verification for Aurum remote recovery requests.

Requests are Ed25519-signed, short-lived, bound to one machine identity, and
checked against replay state before any recovery action is allowed. A `specific`
request pins both the genetics commit and the platform-source commit, so a
moving branch can never silently change the signed recovery state.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


ENVELOPE_SCHEMA = "aurum-recovery-envelope-v1"
REQUEST_SCHEMA = "aurum-recovery-request-v1"
TRUST_SCHEMA = "aurum-recovery-trust-v1"
MAX_LIFETIME_SECONDS = 15 * 60
CLOCK_SKEW_SECONDS = 120
REQUEST_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")


class RecoveryControlError(RuntimeError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def load_trusted_states(path: Path) -> set[tuple[str, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryControlError(f"recovery trust policy unreadable: {exc}") from exc
    if payload.get("schema") != TRUST_SCHEMA:
        raise RecoveryControlError("unsupported recovery trust policy")
    states = payload.get("specific_states")
    if not isinstance(states, list):
        raise RecoveryControlError("specific_states must be a list")
    result: set[tuple[str, str]] = set()
    for item in states:
        if not isinstance(item, dict):
            raise RecoveryControlError("specific recovery trust entries must be objects")
        genetics = str(item.get("genetics_commit") or "").lower()
        platform = str(item.get("platform_commit") or "").lower()
        if not COMMIT_RE.fullmatch(genetics) or not COMMIT_RE.fullmatch(platform):
            raise RecoveryControlError("trusted specific states require two immutable 40-character commits")
        result.add((genetics, platform))
    return result


def _validate_payload(
    payload: dict[str, Any],
    *,
    local_node_id: str,
    trusted_states: set[tuple[str, str]],
    now: int,
) -> dict[str, Any]:
    if payload.get("schema") != REQUEST_SCHEMA:
        raise RecoveryControlError("unsupported recovery request schema")

    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise RecoveryControlError("invalid recovery request_id")

    node_id = payload.get("node_id")
    if not isinstance(node_id, str) or not node_id or node_id != local_node_id:
        raise RecoveryControlError("recovery request is not addressed to this machine")

    issued = payload.get("issued_at_unix")
    expires = payload.get("expires_at_unix")
    if not isinstance(issued, int) or not isinstance(expires, int):
        raise RecoveryControlError("recovery request timestamps must be integers")
    if expires <= issued or expires - issued > MAX_LIFETIME_SECONDS:
        raise RecoveryControlError("recovery request lifetime is invalid")
    if issued > now + CLOCK_SKEW_SECONDS:
        raise RecoveryControlError("recovery request is from the future")
    if expires < now:
        raise RecoveryControlError("recovery request has expired")

    target = payload.get("target")
    if target not in {"previous", "last-known-good", "specific"}:
        raise RecoveryControlError("unsupported recovery target")

    ref = payload.get("ref")
    platform_commit = payload.get("platform_commit")
    if target == "specific":
        if not isinstance(ref, str) or not COMMIT_RE.fullmatch(ref.lower()):
            raise RecoveryControlError("specific recovery genetics must be an immutable commit")
        if not isinstance(platform_commit, str) or not COMMIT_RE.fullmatch(platform_commit.lower()):
            raise RecoveryControlError("specific recovery platform source must be an immutable commit")
        ref = ref.lower()
        platform_commit = platform_commit.lower()
        if (ref, platform_commit) not in trusted_states:
            raise RecoveryControlError("specific genetics/platform state pair is not trusted")
    else:
        if ref is not None or platform_commit is not None:
            raise RecoveryControlError("ref/platform_commit are only valid for target=specific")

    reboot = payload.get("reboot", False)
    if not isinstance(reboot, bool):
        raise RecoveryControlError("reboot must be boolean")

    return {
        "schema": REQUEST_SCHEMA,
        "request_id": request_id,
        "node_id": node_id,
        "issued_at_unix": issued,
        "expires_at_unix": expires,
        "target": target,
        "ref": ref,
        "platform_commit": platform_commit,
        "reboot": reboot,
    }


def _verify_ed25519(public_key: Path, payload_bytes: bytes, signature: bytes) -> None:
    if not public_key.is_file():
        raise RecoveryControlError("recovery authority is not enrolled")
    try:
        if public_key.stat().st_size > 8192:
            raise RecoveryControlError("recovery public key is unexpectedly large")
    except OSError as exc:
        raise RecoveryControlError(f"recovery public key unreadable: {exc}") from exc

    with tempfile.TemporaryDirectory(prefix="aurum-recovery-verify-") as td:
        root = Path(td)
        payload_path = root / "payload.bin"
        signature_path = root / "signature.bin"
        payload_path.write_bytes(payload_bytes)
        signature_path.write_bytes(signature)
        try:
            result = subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-inkey",
                    str(public_key),
                    "-rawin",
                    "-in",
                    str(payload_path),
                    "-sigfile",
                    str(signature_path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RecoveryControlError(f"signature verifier unavailable: {exc}") from exc
    if result.returncode != 0:
        raise RecoveryControlError("recovery request signature verification failed")


def verify_envelope(
    envelope: dict[str, Any],
    *,
    public_key: Path,
    local_node_id: str,
    trusted_states: set[tuple[str, str]],
    now: int | None = None,
) -> dict[str, Any]:
    if envelope.get("schema") != ENVELOPE_SCHEMA:
        raise RecoveryControlError("unsupported recovery envelope schema")
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise RecoveryControlError("recovery envelope payload must be an object")
    encoded_signature = envelope.get("signature_ed25519_base64")
    if not isinstance(encoded_signature, str) or not encoded_signature:
        raise RecoveryControlError("recovery signature is missing")
    try:
        signature = base64.b64decode(encoded_signature, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RecoveryControlError("recovery signature is not valid base64") from exc
    if len(signature) != 64:
        raise RecoveryControlError("Ed25519 recovery signature must be 64 bytes")

    checked = _validate_payload(
        payload,
        local_node_id=local_node_id,
        trusted_states=trusted_states,
        now=int(time.time()) if now is None else int(now),
    )
    _verify_ed25519(public_key, canonical_json(payload), signature)
    return checked
