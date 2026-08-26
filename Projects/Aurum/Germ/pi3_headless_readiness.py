#!/usr/bin/env python3
"""Prepare a zero-authority headless-control receipt for the experimental Pi 3.

This program is deliberately offline.  It validates the local identity, SSH
trust, and controller-key material needed by the already-proven strict SSH
route, then records the still-closed gates for richer KVM routes.  It never
opens a socket, scans a network, writes to a Pi, or grants deployment authority.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Callable


RECEIPT_SCHEMA = "aurum.pi3.headless-readiness.v1"
IDENTITY_SCHEMA = "aurum-pi3-pinned-identity-v1"
PINNED_IDENTITY = {
    "target": "raspberry-pi-3-experimental",
    "model_marker": "Raspberry Pi 3",
    "serial": "00000000a6a7df7f",
    "ssh_user": "aurum",
    "pinned_ipv4": "169.254.129.122",
    "host_key_algorithm": "ssh-ed25519",
    "scope": "experimental-pi3-only",
}


class ReadinessError(RuntimeError):
    """The local preparation evidence failed closed."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _openssh_fingerprint(public_key_body: str) -> str:
    parts = public_key_body.strip().split()
    if len(parts) < 2:
        raise ReadinessError("SSH public key material is incomplete")
    try:
        decoded = base64.b64decode(parts[1], validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ReadinessError("SSH public key material is invalid") from exc
    if len(decoded) < 16:
        raise ReadinessError("SSH public key material is too short")
    encoded = base64.b64encode(hashlib.sha256(decoded).digest()).decode("ascii").rstrip("=")
    return f"SHA256:{encoded}"


def _load_identity(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"pinned Pi 3 identity is unreadable: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != IDENTITY_SCHEMA:
        raise ReadinessError("pinned Pi 3 identity schema changed")
    for field, expected in PINNED_IDENTITY.items():
        if value.get(field) != expected:
            raise ReadinessError(f"pinned Pi 3 identity field changed: {field}")
    if value.get("production_nodes_allowed") is not False:
        raise ReadinessError("pinned Pi 3 identity no longer excludes production nodes")
    host_fingerprint = value.get("host_key_sha256")
    if not isinstance(host_fingerprint, str) or not host_fingerprint.startswith("SHA256:"):
        raise ReadinessError("pinned Pi 3 host-key fingerprint is invalid")
    key_locator = value.get("windows_key_locator")
    if not isinstance(key_locator, str) or not key_locator.strip():
        raise ReadinessError("pinned Pi 3 controller-key locator is missing")
    return value


def _validate_known_hosts(path: Path, identity: dict[str, Any]) -> dict[str, str]:
    try:
        lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except (OSError, UnicodeError) as exc:
        raise ReadinessError(f"pinned Pi 3 known-hosts file is unreadable: {exc}") from exc
    if len(lines) != 1:
        raise ReadinessError("pinned Pi 3 known-hosts file must contain exactly one trust entry")
    parts = lines[0].split()
    if len(parts) < 3:
        raise ReadinessError("pinned Pi 3 known-hosts entry is incomplete")
    if parts[0] != identity["pinned_ipv4"]:
        raise ReadinessError("pinned Pi 3 known-hosts target changed")
    if parts[1] != identity["host_key_algorithm"]:
        raise ReadinessError("pinned Pi 3 known-hosts algorithm changed")
    fingerprint = _openssh_fingerprint(f"{parts[1]} {parts[2]}")
    if fingerprint != identity["host_key_sha256"]:
        raise ReadinessError("pinned Pi 3 known-hosts fingerprint does not match identity")
    return {"algorithm": parts[1], "fingerprint": fingerprint}


def _private_key_public_fingerprint(path: Path) -> str:
    if not path.is_file() or path.stat().st_size == 0:
        raise ReadinessError("pinned Pi 3 controller private key is unavailable")
    try:
        result = subprocess.run(
            ["ssh-keygen", "-y", "-f", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReadinessError("controller public-key derivation could not run") from exc
    if result.returncode != 0:
        raise ReadinessError("controller private key could not be validated")
    return _openssh_fingerprint(result.stdout)


def build_receipt(
    *,
    identity_path: Path,
    known_hosts_path: Path,
    private_key_path: Path | None = None,
    public_fingerprint_reader: Callable[[Path], str] = _private_key_public_fingerprint,
) -> dict[str, Any]:
    identity = _load_identity(identity_path)
    configured_key = Path(identity["windows_key_locator"])
    selected_key = private_key_path or configured_key
    try:
        same_key = selected_key.resolve(strict=False) == configured_key.resolve(strict=False)
    except OSError:
        same_key = False
    if not same_key:
        raise ReadinessError("controller private key differs from the pinned identity locator")
    trust = _validate_known_hosts(known_hosts_path, identity)
    controller_fingerprint = public_fingerprint_reader(selected_key)

    return {
        "schema": RECEIPT_SCHEMA,
        "status": "prepared",
        "semantic_state": "local-headless-control-evidence-prepared",
        "target": {
            "name": identity["target"],
            "address": identity["pinned_ipv4"],
            "ssh_user": identity["ssh_user"],
            "expected_model_marker": identity["model_marker"],
            "expected_serial": identity["serial"],
            "scope": identity["scope"],
            "production_nodes_allowed": False,
        },
        "local_evidence": {
            "identity_sha256": _sha256_file(identity_path),
            "known_hosts_sha256": _sha256_file(known_hosts_path),
            "host_key_algorithm": trust["algorithm"],
            "host_key_fingerprint": trust["fingerprint"],
            "controller_public_key_fingerprint": controller_fingerprint,
            "private_key_recorded": False,
        },
        "selected_route": {
            "id": "strict-key-only-ssh",
            "execution_route": "direct-local",
            "state": "prepared",
            "autonomy": "no-typing-after-live-identity-proof",
            "live_gate": [
                "one bounded TCP/22 check after a material boot or link-state change",
                "strict host-key checking with the validated single-entry trust file",
                "BatchMode and IdentitiesOnly key-only authentication",
                "exact Raspberry Pi 3 model-marker match",
                "exact 00000000a6a7df7f serial match",
            ],
            "visual_evidence": "keep USB3 HDMI capture as the independent boot-state reference",
        },
        "warm_routes": [
            {
                "id": "ssh-tunneled-software-console",
                "state": "waiting",
                "reason": "depends on the same running OS and SSH path, so it improves convenience but is not recovery",
                "deployment_required": True,
            },
            {
                "id": "tinyseed-authenticated-early-kvm",
                "state": "waiting",
                "reason": "implemented for a Tiny Seed image; the current Raspberry Pi OS card is not a proven retrofit target",
                "deployment_required": True,
                "physical_pi3_proof_required": True,
            },
            {
                "id": "external-physical-kvm",
                "state": "waiting",
                "reason": "requires separately identified and authorized capture/input hardware",
                "deployment_required": True,
            },
        ],
        "live_deployment_gate": {
            "state": "waiting",
            "authority_granted": False,
            "required_before_full_kvm": [
                "verified rollback image/receipt for the current experimental card",
                "fresh exact Pi 3 model and serial proof",
                "an immutable target-compatible KVM payload with hashes",
                "an independently usable visual path through USB3 HDMI capture",
                "explicit authority for the selected service/input/network changes",
                "post-deployment input, disconnect-release, and rollback verification",
            ],
        },
        "protected_boundaries": {
            "network_activity_performed": False,
            "device_mutation_performed": False,
            "boot_or_firmware_change_performed": False,
            "kernel_module_or_driver_change_performed": False,
            "adaptive_drivers_files_changed": False,
            "new_authority_granted": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare the pinned experimental Pi 3 headless-control receipt")
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument("--private-key", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(
            identity_path=args.identity,
            known_hosts_path=args.known_hosts,
            private_key_path=args.private_key,
        )
        body = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.output.with_suffix(args.output.suffix + ".tmp")
            temporary.write_text(body, encoding="utf-8")
            temporary.replace(args.output)
        print(body, end="")
        return 0
    except (ReadinessError, OSError, UnicodeError) as exc:
        print(json.dumps({"schema": RECEIPT_SCHEMA, "status": "refused", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
