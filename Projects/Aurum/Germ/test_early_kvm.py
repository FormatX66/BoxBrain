#!/usr/bin/env python3
from __future__ import annotations

import json
import base64
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import early_kvm
import early_kvm_bootstrap
import early_kvm_controller
import prepare_early_kvm


class RecordingBackend(early_kvm.InputBackend):
    def __init__(self) -> None:
        self.events: list[tuple] = []

    def key(self, name: str, value: int) -> None:
        self.events.append(("key", name, value))

    def mouse(self, dx: int, dy: int, wheel: int, buttons) -> None:
        self.events.append(("mouse", dx, dy, wheel, dict(buttons)))

    def release_all(self) -> None:
        self.events.append(("release_all",))


def authority(path: Path, **overrides) -> dict:
    value = {
        "schema": early_kvm.AUTHORITY_SCHEMA,
        "enabled": True,
        "listen": "127.0.0.1",
        "port": 19467,
        "allowed_controller_cidrs": ["127.0.0.1/32"],
        "authority_key_hex": "42" * 32,
        "session_seconds": 60,
        "allow_framebuffer": False,
        "max_frame_bytes": 1024 * 1024,
        "video_fallback": "hdmi-capture",
        "receipt_path": str(path.parent / "events.jsonl"),
        "transport": "tls-pinned",
        "tls_cert_path": str(path.parent / "server.crt"),
        "tls_key_path": str(path.parent / "server.key"),
    }
    value.update(overrides)
    path.write_text(json.dumps(value), encoding="utf-8")
    return value


def fixture_tls_identity(root: Path) -> tuple[Path, Path]:
    certificate_body, private_key_body = prepare_early_kvm._generate_tls_identity()
    certificate = root / "server.crt"
    private_key = root / "server.key"
    certificate.write_bytes(certificate_body)
    private_key.write_bytes(private_key_body)
    return certificate, private_key


class EarlyKVMTests(unittest.TestCase):
    def test_authority_requires_bounded_controller_network_and_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "authority.json"
            authority(path, allowed_controller_cidrs=["0.0.0.0/0"])
            with self.assertRaises(early_kvm.EarlyKVMError):
                early_kvm.load_authority(path)
            authority(path, allowed_controller_cidrs=["10.0.0.0/8"])
            with self.assertRaises(early_kvm.EarlyKVMError):
                early_kvm.load_authority(path)
            authority(path, authority_key_hex="00" * 32)
            with self.assertRaises(early_kvm.EarlyKVMError):
                early_kvm.load_authority(path)

    def test_authenticated_session_types_moves_and_rejects_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "authority.json"
            certificate, private_key = fixture_tls_identity(Path(temporary))
            authority(path, tls_cert_path=str(certificate), tls_key_path=str(private_key))
            config = early_kvm.load_authority(path)
            config["port"] = 0
            backend = RecordingBackend()
            server = early_kvm.build_server(config, backend=backend)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
            thread.start()
            try:
                controller_path = Path(temporary) / "controller.json"
                controller_path.write_text(json.dumps({
                    "schema": early_kvm_controller.CONTROLLER_SCHEMA,
                    "target": "127.0.0.1",
                    "port": server.server_address[1],
                    "controller": "test-controller",
                    "authority_key_hex": "42" * 32,
                    "timeout_seconds": 2.0,
                    "transport": "tls-pinned",
                    "tls_ca_path": str(certificate),
                }), encoding="utf-8")
                controller = early_kvm_controller.load_controller(controller_path)
                with early_kvm_controller.Session(controller) as session:
                    status = session.command("status")
                    self.assertEqual(status["outcome"], "succeeded")
                    typed = session.command("text", text="A1\n")
                    self.assertEqual(typed["characters"], 3)
                    moved = session.command("mouse", dx=4, dy=-3, wheel=1, buttons={"left": 1})
                    self.assertEqual(moved["buttons"], {"left": 1})
                    session.sequence -= 1
                    with self.assertRaises(early_kvm_controller.ControllerError):
                        session.command("status")
                self.assertIn(("key", "KEY_LEFTSHIFT", 1), backend.events)
                self.assertIn(("key", "KEY_A", 1), backend.events)
                self.assertIn(("key", "KEY_ENTER", 0), backend.events)
                self.assertIn(("mouse", 4, -3, 1, {"left": 1}), backend.events)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
            self.assertIn(("release_all",), backend.events)
            event_text = (Path(temporary) / "events.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("A1", event_text)
            self.assertIn('"operation":"text"', event_text)

    def test_framebuffer_snapshot_is_hash_bound_and_has_hdmi_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sysfs = root / "sys"
            sysfs.mkdir()
            (sysfs / "virtual_size").write_text("2,2\n", encoding="ascii")
            (sysfs / "bits_per_pixel").write_text("32\n", encoding="ascii")
            raw = bytes(range(16))
            device = root / "fb0"
            device.write_bytes(raw)
            framebuffer = early_kvm.FrameBuffer(device=device, sysfs=sysfs)
            disabled = framebuffer.snapshot(
                {"allow_framebuffer": False, "video_fallback": "hdmi-capture", "max_frame_bytes": 1024}
            )
            self.assertFalse(disabled["available"])
            self.assertEqual(disabled["video_fallback"], "hdmi-capture")
            enabled = framebuffer.snapshot(
                {"allow_framebuffer": True, "video_fallback": "hdmi-capture", "max_frame_bytes": 1024}
            )
            self.assertTrue(enabled["available"])
            output = root / "frame.raw"
            metadata = early_kvm_controller.save_frame(enabled, output)
            self.assertEqual(output.read_bytes(), raw)
            self.assertEqual(metadata["raw_sha256"], __import__("hashlib").sha256(raw).hexdigest())

    def test_tls_session_refuses_a_different_physical_pin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            certificate, private_key = fixture_tls_identity(root)
            wrong_root = root / "wrong"
            wrong_root.mkdir()
            wrong_certificate, _ = fixture_tls_identity(wrong_root)
            config_path = root / "authority.json"
            authority(config_path, tls_cert_path=str(certificate), tls_key_path=str(private_key))
            config = early_kvm.load_authority(config_path)
            config["port"] = 0
            server = early_kvm.build_server(config, backend=RecordingBackend())
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
            thread.start()
            try:
                controller_path = root / "wrong-controller.json"
                controller_path.write_text(json.dumps({
                    "schema": early_kvm_controller.CONTROLLER_SCHEMA,
                    "target": "127.0.0.1",
                    "port": server.server_address[1],
                    "controller": "wrong-pin-controller",
                    "authority_key_hex": "42" * 32,
                    "timeout_seconds": 2.0,
                    "transport": "tls-pinned",
                    "tls_ca_path": str(wrong_certificate),
                }), encoding="utf-8")
                with self.assertRaises(early_kvm_controller.ControllerError):
                    early_kvm_controller.Session(early_kvm_controller.load_controller(controller_path))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_bootstrap_consumes_authority_wifi_and_key_without_secret_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            boot = root / "boot/firmware/aurum-kvm"
            boot.mkdir(parents=True)
            authority(boot / "authority.json")
            fixture_tls_identity(boot)
            (boot / "aurum-early-kvm.nmconnection").write_text(
                "[connection]\nid=fixture\ntype=wifi\n[wifi]\nmode=infrastructure\nssid=test\n[ipv4]\nmethod=auto\n",
                encoding="utf-8",
            )
            key_payload = base64.b64encode(b"fixture-public-key-material-32b").decode("ascii")
            (boot / "authorized_key").write_text(f"ssh-ed25519 {key_payload} fixture\n", encoding="utf-8")
            receipt = early_kvm_bootstrap.bootstrap(root)
            self.assertEqual(receipt["state"], "prepared")
            self.assertFalse((boot / "authority.json").exists())
            self.assertFalse((boot / "aurum-early-kvm.nmconnection").exists())
            installed = root / "etc/aurum/early-kvm.json"
            self.assertTrue(installed.is_file())
            if os.name == "posix":
                self.assertEqual(os.stat(installed).st_mode & 0o777, 0o600)
            receipt_text = (root / "var/lib/aurum/evidence/early-kvm-bootstrap.json").read_text(encoding="utf-8")
            self.assertNotIn("42" * 32, receipt_text)
            self.assertTrue((root / "home/aurum/.ssh/authorized_keys").is_file())

    def test_invalid_boot_optional_input_cannot_activate_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            boot = root / "boot/firmware/aurum-kvm"
            boot.mkdir(parents=True)
            authority(boot / "authority.json")
            fixture_tls_identity(boot)
            (boot / "authorized_key").write_text("ssh-ed25519 not-base64 fixture\n", encoding="utf-8")
            with self.assertRaises(early_kvm_bootstrap.BootstrapError):
                early_kvm_bootstrap.bootstrap(root)
            self.assertFalse((root / "etc/aurum/early-kvm.json").exists())
            self.assertTrue((boot / "authority.json").exists())

    def test_boot_partition_provisioner_creates_matching_private_configs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            boot = root / "boot"
            boot.mkdir()
            (boot / "config.txt").write_text("# fixture\n", encoding="utf-8")
            controller = root / "controller.json"
            with mock.patch.object(prepare_early_kvm.secrets, "token_bytes", return_value=b"K" * 32):
                receipt = prepare_early_kvm.provision(
                    boot_root=boot,
                    controller_config=controller,
                    controller_cidr="169.254.129.121/32",
                    target="169.254.129.122",
                    controller="aurum-laptop",
                    wifi_ssid="Fixture WiFi",
                    wifi_password="fixture-secret",
                )
            target = json.loads((boot / "aurum-kvm/authority.json").read_text(encoding="utf-8"))
            host = json.loads(controller.read_text(encoding="utf-8"))
            self.assertEqual(target["authority_key_hex"], host["authority_key_hex"])
            self.assertEqual(host["target"], "169.254.129.122")
            self.assertFalse(receipt["authority_key_disclosed"])
            self.assertNotIn(target["authority_key_hex"], json.dumps(receipt))
            self.assertTrue((boot / "ssh").is_file())
            self.assertIn("psk=fixture-secret", (boot / "aurum-kvm/aurum-early-kvm.nmconnection").read_text())
            self.assertEqual(target["transport"], "tls-pinned")
            self.assertTrue(Path(host["tls_ca_path"]).is_file())

    def test_provisioner_validates_all_inputs_before_writing_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            boot = root / "boot"
            boot.mkdir()
            (boot / "config.txt").write_text("# fixture\n", encoding="utf-8")
            bad_key = root / "bad.pub"
            bad_key.write_text("ssh-ed25519 not-base64 fixture\n", encoding="utf-8")
            with self.assertRaises(prepare_early_kvm.ProvisionError):
                prepare_early_kvm.provision(
                    boot_root=boot,
                    controller_config=root / "controller.json",
                    controller_cidr="169.254.129.121/32",
                    target="169.254.129.122",
                    controller="aurum-laptop",
                    ssh_public_key=bad_key,
                )
            self.assertFalse((boot / "aurum-kvm/authority.json").exists())
            self.assertFalse((root / "controller.json").exists())

    def test_pi_builder_masks_vendor_wizard_and_starts_kvm_before_tinyseed(self) -> None:
        script = Path(__file__).with_name("build-pi-tinyseed.sh").read_text(encoding="utf-8")
        self.assertIn('ln -sfn /dev/null "$SYSTEMD/userconfig.service"', script)
        self.assertIn("Description=Aurum early-boot authenticated KVM", script)
        self.assertIn("Before=aurum-tinyseed.service", script)
        self.assertIn("python3-evdev", script)


if __name__ == "__main__":
    unittest.main()
