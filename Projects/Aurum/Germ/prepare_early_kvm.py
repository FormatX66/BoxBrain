#!/usr/bin/env python3
"""Provision explicit early-KVM authority onto a TinySeed Pi boot partition."""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import ipaddress
import json
import os
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from early_kvm import AUTHORITY_SCHEMA
from early_kvm_controller import CONTROLLER_SCHEMA


class ProvisionError(RuntimeError):
    pass


def _atomic_json(path: Path, value: dict[str, Any], *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        temporary.chmod(mode)
    except OSError:
        pass
    temporary.replace(path)
    try:
        path.chmod(mode)
    except OSError:
        pass


def _wifi_profile(ssid: str, password: str) -> str:
    if not ssid or len(ssid.encode("utf-8")) > 32 or any(ord(character) < 32 for character in ssid):
        raise ProvisionError("Wi-Fi SSID is invalid")
    if len(password) < 8 or len(password) > 63 or any(ord(character) < 32 for character in password):
        raise ProvisionError("Wi-Fi password must be from 8 to 63 characters")
    escaped_ssid = ssid.replace("\\", "\\\\").replace(";", "\\;")
    escaped_password = password.replace("\\", "\\\\").replace(";", "\\;")
    return (
        "[connection]\n"
        "id=aurum-early-kvm\n"
        "type=wifi\n"
        "autoconnect=true\n\n"
        "[wifi]\n"
        "mode=infrastructure\n"
        f"ssid={escaped_ssid}\n\n"
        "[wifi-security]\n"
        "key-mgmt=wpa-psk\n"
        f"psk={escaped_password}\n\n"
        "[ipv4]\n"
        "method=auto\n\n"
        "[ipv6]\n"
        "method=auto\n"
    )


def _read_public_key(path: Path) -> str:
    try:
        line = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ProvisionError(f"SSH public key is unreadable: {exc}") from exc
    parts = line.split()
    valid_type = len(parts) >= 1 and (parts[0] in {"ssh-ed25519", "ssh-rsa"} or parts[0].startswith("ecdsa-sha2-"))
    if "\n" in line or len(parts) < 2 or not valid_type:
        raise ProvisionError("SSH public key format is invalid")
    try:
        decoded = base64.b64decode(parts[1], validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ProvisionError("SSH public key payload is invalid") from exc
    if len(decoded) < 16:
        raise ProvisionError("SSH public key payload is too short")
    return line


def _generate_tls_identity() -> tuple[bytes, bytes]:
    openssl = shutil.which("openssl")
    with tempfile.TemporaryDirectory(prefix="aurum-early-kvm-") as temporary:
        root = Path(temporary)
        key = root / "server.key"
        certificate = root / "server.crt"
        if openssl is not None:
            command = [
                    openssl,
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-sha256",
                    "-nodes",
                    "-days",
                    "825",
                    "-subj",
                    "/CN=aurum-early-kvm",
                    "-keyout",
                    str(key),
                    "-out",
                    str(certificate),
                ]
            environment = None
        else:
            powershell = shutil.which("pwsh") or shutil.which("powershell")
            if powershell is None:
                raise ProvisionError("OpenSSL or PowerShell 7 is required to generate the pinned TLS identity")
            script = (
                "$ErrorActionPreference='Stop';"
                "$rsa=[System.Security.Cryptography.RSA]::Create(2048);"
                "$request=[System.Security.Cryptography.X509Certificates.CertificateRequest]::new("
                "'CN=aurum-early-kvm',$rsa,[System.Security.Cryptography.HashAlgorithmName]::SHA256,"
                "[System.Security.Cryptography.RSASignaturePadding]::Pkcs1);"
                "$now=[System.DateTimeOffset]::UtcNow;"
                "$certificate=$request.CreateSelfSigned($now.AddMinutes(-5),$now.AddDays(825));"
                "[System.IO.File]::WriteAllText($env:AURUM_KVM_CERT_PATH,$certificate.ExportCertificatePem());"
                "[System.IO.File]::WriteAllText($env:AURUM_KVM_KEY_PATH,$rsa.ExportPkcs8PrivateKeyPem())"
            )
            command = [powershell, "-NoProfile", "-NonInteractive", "-Command", script]
            environment = dict(os.environ)
            environment["AURUM_KVM_CERT_PATH"] = str(certificate)
            environment["AURUM_KVM_KEY_PATH"] = str(key)
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )
        if result.returncode != 0:
            raise ProvisionError("OpenSSL could not generate the pinned early KVM identity")
        return certificate.read_bytes(), key.read_bytes()


def provision(
    *,
    boot_root: Path,
    controller_config: Path,
    controller_cidr: str,
    target: str,
    controller: str,
    port: int = 19467,
    allow_framebuffer: bool = True,
    wifi_ssid: str | None = None,
    wifi_password: str | None = None,
    ssh_public_key: Path | None = None,
) -> dict[str, Any]:
    if not boot_root.is_dir() or not (boot_root / "config.txt").is_file():
        raise ProvisionError("boot_root is not a mounted Raspberry Pi boot partition")
    try:
        network = ipaddress.ip_network(controller_cidr, strict=True)
    except ValueError as exc:
        raise ProvisionError("controller CIDR is invalid") from exc
    minimum_prefix = 24 if network.version == 4 else 64
    if network.prefixlen < minimum_prefix:
        raise ProvisionError(f"controller CIDR must be /{minimum_prefix} or narrower")
    if not 1024 <= int(port) <= 65535:
        raise ProvisionError("port must be from 1024 to 65535")
    if not target or not controller:
        raise ProvisionError("target and controller identity are required")
    if (wifi_ssid is None) != (wifi_password is None):
        raise ProvisionError("Wi-Fi SSID and password must be provided together")

    # Validate every optional input before placing live authority on the boot
    # partition. A malformed secondary input must leave no half-enabled KVM.
    wifi_body = None
    if wifi_ssid is not None and wifi_password is not None:
        wifi_body = _wifi_profile(wifi_ssid, wifi_password)
    key_line = _read_public_key(ssh_public_key) if ssh_public_key is not None else None

    certificate_body, private_key_body = _generate_tls_identity()
    authority_key = secrets.token_bytes(32)
    authority = {
        "schema": AUTHORITY_SCHEMA,
        "enabled": True,
        "listen": "0.0.0.0",
        "port": int(port),
        "allowed_controller_cidrs": [str(network)],
        "authority_key_hex": authority_key.hex(),
        "session_seconds": 1800,
        "allow_framebuffer": bool(allow_framebuffer),
        "max_frame_bytes": 16 * 1024 * 1024,
        "video_fallback": "hdmi-capture",
        "transport": "tls-pinned",
        "tls_cert_path": "/etc/aurum/early-kvm-server.crt",
        "tls_key_path": "/etc/aurum/early-kvm-server.key",
    }
    controller_value = {
        "schema": CONTROLLER_SCHEMA,
        "target": target,
        "port": int(port),
        "controller": controller,
        "authority_key_hex": authority_key.hex(),
        "timeout_seconds": 8.0,
        "transport": "tls-pinned",
        "tls_ca_path": str(controller_config.with_suffix(controller_config.suffix + ".ca.crt").resolve()),
    }
    boot_config = boot_root / "aurum-kvm" / "authority.json"
    boot_config.parent.mkdir(parents=True, exist_ok=True)

    wifi_written = False
    if wifi_body is not None:
        wifi_path = boot_root / "aurum-kvm" / "aurum-early-kvm.nmconnection"
        wifi_path.write_text(wifi_body, encoding="utf-8")
        wifi_written = True

    ssh_key_fingerprint = None
    if key_line is not None:
        (boot_root / "aurum-kvm" / "authorized_key").write_text(key_line + "\n", encoding="utf-8")
        ssh_key_fingerprint = hashlib.sha256(key_line.encode("utf-8")).hexdigest()

    (boot_config.parent / "server.crt").write_bytes(certificate_body)
    (boot_config.parent / "server.key").write_bytes(private_key_body)
    tls_ca = Path(controller_value["tls_ca_path"])
    tls_ca.parent.mkdir(parents=True, exist_ok=True)
    tls_ca.write_bytes(certificate_body)
    _atomic_json(controller_config, controller_value)
    # Authority is written last: it is the single activation record.
    _atomic_json(boot_config, authority)
    (boot_root / "ssh").touch(exist_ok=True)
    return {
        "schema": "aurum-early-kvm-provision-receipt-v1",
        "state": "prepared",
        "boot_root": str(boot_root.resolve()),
        "controller_config": str(controller_config.resolve()),
        "controller_cidr": str(network),
        "target": target,
        "port": int(port),
        "framebuffer_allowed": bool(allow_framebuffer),
        "video_fallback": "hdmi-capture",
        "wifi_profile_written": wifi_written,
        "ssh_public_key_sha256": ssh_key_fingerprint,
        "authority_key_disclosed": False,
        "transport": "tls-pinned+hmac-sha256",
        "tls_certificate_sha256": hashlib.sha256(certificate_body).hexdigest(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare a TinySeed Pi boot partition for authenticated early KVM")
    parser.add_argument("--boot-root", type=Path, required=True)
    parser.add_argument("--controller-config", type=Path, required=True)
    parser.add_argument("--controller-cidr", required=True)
    parser.add_argument("--target", default="aurum-tinyseed.local")
    parser.add_argument("--controller", default="aurum-controller")
    parser.add_argument("--port", type=int, default=19467)
    parser.add_argument("--no-framebuffer", action="store_true")
    parser.add_argument("--wifi-ssid")
    parser.add_argument("--ssh-public-key", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        password = None
        if args.wifi_ssid:
            password = os.environ.get("AURUM_KVM_WIFI_PASSWORD")
            if password is None:
                password = getpass.getpass("Wi-Fi password (not stored in command history): ")
        receipt = provision(
            boot_root=args.boot_root,
            controller_config=args.controller_config,
            controller_cidr=args.controller_cidr,
            target=args.target,
            controller=args.controller,
            port=args.port,
            allow_framebuffer=not args.no_framebuffer,
            wifi_ssid=args.wifi_ssid,
            wifi_password=password,
            ssh_public_key=args.ssh_public_key,
        )
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    except ProvisionError as exc:
        print(json.dumps({"schema": "aurum-early-kvm-provision-receipt-v1", "state": "refused", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
