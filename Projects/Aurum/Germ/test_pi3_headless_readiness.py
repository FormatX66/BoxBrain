#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pi3_headless_readiness


HOST_KEY = "AAAAC3NzaC1lZDI1NTE5AAAAILO5jlISyFFEFSbDeF4Ngod7AVWWhLDTDyoxC3A2mWj1"
HOST_FINGERPRINT = "SHA256:HUeYvmzLc5X487o4EnfNAqmANJFnsbUU6uc3oON+vlQ"


class Pi3HeadlessReadinessTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path, Path]:
        private_key = root / "id_ed25519"
        private_key.write_text("test fixture only\n", encoding="utf-8")
        identity = root / "pi3-identity.json"
        identity.write_text(
            json.dumps(
                {
                    "schema": "aurum-pi3-pinned-identity-v1",
                    "target": "raspberry-pi-3-experimental",
                    "model_marker": "Raspberry Pi 3",
                    "serial": "00000000a6a7df7f",
                    "ethernet_mac": "B8-27-EB-A7-DF-7F",
                    "ssh_user": "aurum",
                    "pinned_ipv4": "169.254.129.122",
                    "host_key_algorithm": "ssh-ed25519",
                    "host_key_sha256": HOST_FINGERPRINT,
                    "windows_key_locator": str(private_key),
                    "scope": "experimental-pi3-only",
                    "production_nodes_allowed": False,
                }
            ),
            encoding="utf-8",
        )
        known_hosts = root / "pi3_known_hosts"
        known_hosts.write_text(f"169.254.129.122 ssh-ed25519 {HOST_KEY}\n", encoding="utf-8")
        return identity, known_hosts, private_key

    def test_prepares_zero_authority_receipt_without_live_claims(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            identity, known_hosts, private_key = self.fixture(Path(temporary))
            receipt = pi3_headless_readiness.build_receipt(
                identity_path=identity,
                known_hosts_path=known_hosts,
                private_key_path=private_key,
                public_fingerprint_reader=lambda _: "SHA256:fixture-controller",
            )
        self.assertEqual(receipt["status"], "prepared")
        self.assertEqual(receipt["selected_route"]["id"], "strict-key-only-ssh")
        self.assertIn("exact 00000000a6a7df7f serial match", receipt["selected_route"]["live_gate"])
        self.assertEqual(receipt["live_deployment_gate"]["state"], "waiting")
        self.assertFalse(receipt["live_deployment_gate"]["authority_granted"])
        self.assertFalse(receipt["protected_boundaries"]["network_activity_performed"])
        self.assertFalse(receipt["protected_boundaries"]["adaptive_drivers_files_changed"])
        self.assertNotIn("test fixture only", json.dumps(receipt))

    def test_refuses_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            identity, known_hosts, private_key = self.fixture(Path(temporary))
            value = json.loads(identity.read_text(encoding="utf-8"))
            value["serial"] = "0000000000000000"
            identity.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(pi3_headless_readiness.ReadinessError):
                pi3_headless_readiness.build_receipt(
                    identity_path=identity,
                    known_hosts_path=known_hosts,
                    private_key_path=private_key,
                    public_fingerprint_reader=lambda _: "SHA256:fixture-controller",
                )

    def test_refuses_extra_or_changed_host_trust(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            identity, known_hosts, private_key = self.fixture(Path(temporary))
            known_hosts.write_text(
                known_hosts.read_text(encoding="utf-8") + f"169.254.129.123 ssh-ed25519 {HOST_KEY}\n",
                encoding="utf-8",
            )
            with self.assertRaises(pi3_headless_readiness.ReadinessError):
                pi3_headless_readiness.build_receipt(
                    identity_path=identity,
                    known_hosts_path=known_hosts,
                    private_key_path=private_key,
                    public_fingerprint_reader=lambda _: "SHA256:fixture-controller",
                )

    def test_refuses_unpinned_controller_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            identity, known_hosts, _ = self.fixture(root)
            other_key = root / "other-key"
            other_key.write_text("other fixture\n", encoding="utf-8")
            with self.assertRaises(pi3_headless_readiness.ReadinessError):
                pi3_headless_readiness.build_receipt(
                    identity_path=identity,
                    known_hosts_path=known_hosts,
                    private_key_path=other_key,
                    public_fingerprint_reader=lambda _: "SHA256:fixture-controller",
                )


if __name__ == "__main__":
    unittest.main()
