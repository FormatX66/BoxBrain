#!/usr/bin/env python3
"""Consume physical boot-media authority into the protected TinySeed root."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import ssl
from pathlib import Path
from typing import Any

from early_kvm import load_authority


class BootstrapError(RuntimeError):
    pass


def _relative(root: Path, absolute: str) -> Path:
    return root / absolute.lstrip("/")


def _atomic_install(body: bytes, destination: Path, *, mode: int) -> str:
    digest = hashlib.sha256(body).hexdigest()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(body)
    os.chmod(temporary, mode)
    temporary.replace(destination)
    os.chmod(destination, mode)
    if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
        raise BootstrapError(f"copy verification failed for {destination}")
    return digest


def _validate_wifi(body: bytes) -> None:
    text = body.decode("utf-8")
    required = ("[connection]", "type=wifi", "[wifi]", "mode=infrastructure", "[ipv4]", "method=auto")
    if any(marker not in text for marker in required):
        raise BootstrapError("boot Wi-Fi profile is invalid")


def _validate_public_key(body: bytes) -> str:
    line = body.decode("utf-8").strip()
    parts = line.split()
    valid_type = len(parts) >= 1 and (parts[0] in {"ssh-ed25519", "ssh-rsa"} or parts[0].startswith("ecdsa-sha2-"))
    if "\n" in line or len(parts) < 2 or not valid_type:
        raise BootstrapError("boot SSH public key is invalid")
    try:
        decoded = base64.b64decode(parts[1], validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise BootstrapError("boot SSH public key payload is invalid") from exc
    if len(decoded) < 16:
        raise BootstrapError("boot SSH public key payload is too short")
    return line


def _validate_tls_identity(certificate: bytes, private_key: bytes) -> None:
    if b"-----BEGIN CERTIFICATE-----" not in certificate or b"-----END CERTIFICATE-----" not in certificate:
        raise BootstrapError("boot early KVM certificate is invalid")
    if b"-----BEGIN PRIVATE KEY-----" not in private_key or b"-----END PRIVATE KEY-----" not in private_key:
        raise BootstrapError("boot early KVM private key is invalid")


def bootstrap(root: Path = Path("/")) -> dict[str, Any]:
    source_root = _relative(root, "/boot/firmware/aurum-kvm")
    authority_source = source_root / "authority.json"
    authority_destination = _relative(root, "/etc/aurum/early-kvm.json")
    if not authority_source.is_file():
        return {"schema": "aurum-early-kvm-bootstrap-v1", "state": "no-authority", "enabled": False}
    # Read and validate the complete physical handoff before activating any of
    # it. Authority is installed last, so partial copies cannot start a listener.
    authority_body = authority_source.read_bytes()
    load_authority(authority_source)
    wifi_source = source_root / "aurum-early-kvm.nmconnection"
    wifi_body = wifi_source.read_bytes() if wifi_source.is_file() else None
    if wifi_body is not None:
        _validate_wifi(wifi_body)

    ssh_source = source_root / "authorized_key"
    ssh_body = ssh_source.read_bytes() if ssh_source.is_file() else None
    key_line = _validate_public_key(ssh_body) if ssh_body is not None else None

    certificate_source = source_root / "server.crt"
    private_key_source = source_root / "server.key"
    if not certificate_source.is_file() or not private_key_source.is_file():
        raise BootstrapError("boot early KVM TLS identity is incomplete")
    certificate_body = certificate_source.read_bytes()
    private_key_body = private_key_source.read_bytes()
    _validate_tls_identity(certificate_body, private_key_body)

    wifi_sha256 = None
    if wifi_body is not None:
        wifi_sha256 = _atomic_install(
            wifi_body,
            _relative(root, "/etc/NetworkManager/system-connections/aurum-early-kvm.nmconnection"),
            mode=0o600,
        )

    ssh_key_sha256 = None
    if key_line is not None:
        ssh_root = _relative(root, "/home/aurum/.ssh")
        ssh_root.mkdir(parents=True, exist_ok=True)
        os.chmod(ssh_root, 0o700)
        authorized = ssh_root / "authorized_keys"
        authorized.write_text(key_line + "\n", encoding="utf-8")
        os.chmod(authorized, 0o600)
        ssh_key_sha256 = hashlib.sha256(key_line.encode("utf-8")).hexdigest()
        if root == Path("/"):
            try:
                import pwd

                identity = pwd.getpwnam("aurum")
                os.chown(ssh_root, identity.pw_uid, identity.pw_gid)
                os.chown(authorized, identity.pw_uid, identity.pw_gid)
            except (KeyError, OSError):
                raise BootstrapError("the protected aurum account is unavailable")

    certificate_destination = _relative(root, "/etc/aurum/early-kvm-server.crt")
    private_key_destination = _relative(root, "/etc/aurum/early-kvm-server.key")
    certificate_sha256 = _atomic_install(certificate_body, certificate_destination, mode=0o644)
    _atomic_install(private_key_body, private_key_destination, mode=0o600)
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(certificate_destination), str(private_key_destination))
    except (OSError, ssl.SSLError) as exc:
        raise BootstrapError("boot early KVM TLS certificate and key do not match") from exc
    authority_sha256 = _atomic_install(authority_body, authority_destination, mode=0o600)
    for source in (
        authority_source,
        certificate_source,
        private_key_source,
        wifi_source if wifi_body is not None else None,
        ssh_source if ssh_body is not None else None,
    ):
        if source is not None:
            source.unlink()

    receipt = {
        "schema": "aurum-early-kvm-bootstrap-v1",
        "state": "prepared",
        "enabled": True,
        "authority_sha256": authority_sha256,
        "wifi_profile_sha256": wifi_sha256,
        "ssh_public_key_sha256": ssh_key_sha256,
        "boot_authority_consumed": True,
        "secret_recorded": False,
        "transport": "tls-pinned+hmac-sha256",
        "tls_certificate_sha256": certificate_sha256,
        "tls_private_key_sha256_recorded": False,
    }
    receipt_path = _relative(root, "/var/lib/aurum/evidence/early-kvm-bootstrap.json")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import TinySeed early-KVM boot authority")
    parser.add_argument("--root", type=Path, default=Path("/"))
    args = parser.parse_args(argv)
    try:
        print(json.dumps(bootstrap(args.root), indent=2, sort_keys=True))
        return 0
    except (BootstrapError, OSError, ValueError) as exc:
        print(json.dumps({"schema": "aurum-early-kvm-bootstrap-v1", "state": "refused", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
