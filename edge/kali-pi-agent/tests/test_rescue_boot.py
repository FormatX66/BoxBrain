from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boxbrain.rescue_boot import (  # noqa: E402
    ARM_CONFIRMATION,
    CANCEL_CONFIRMATION,
    IMPORT_CONFIRMATION,
    REBOOT_NORMAL_CONFIRMATION,
    RescueBootError,
    RescueBootManager,
)
from boxbrain.cli import main as cli_main  # noqa: E402
from boxbrain.server import build_server  # noqa: E402


class RescueBootTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.manager = RescueBootManager(self.state)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_early_consumer_runs_as_the_boxbrain_service_account(self) -> None:
        self.manager.initialize()
        output = io.StringIO()
        with (
            patch.dict(os.environ, {"BOXBRAIN_STATE_DIR": str(self.state)}),
            patch.object(sys, "argv", ["boxbrainctl", "rescue", "consume-early"]),
            redirect_stdout(output),
        ):
            self.assertEqual(cli_main(), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["mode"], "normal")
        self.assertEqual(self.manager.status()["next_pi_boot"], "NORMAL BOXBRAIN")

    def _source(self, name: str, content: bytes) -> Path:
        path = self.root / name
        path.write_bytes(content)
        return path

    def _import(
        self,
        image_id: str,
        kind: str,
        architecture: str,
        content: bytes,
    ) -> dict[str, object]:
        source = self._source(f"source-{image_id}.img", content)
        return self.manager.import_image(
            source,
            image_id=image_id,
            kind=kind,
            architecture=architecture,
            boot_compatibility=("bios", "uefi"),
            secure_boot="unknown",
            signed=None,
            expected_sha256=hashlib.sha256(content).hexdigest(),
            checksum_source="test-fixture",
            authorization=IMPORT_CONFIRMATION,
        )

    def test_initial_state_is_normal_and_one_shot(self) -> None:
        status = self.manager.status()
        self.assertEqual(status["pending"]["mode"], "normal")
        self.assertEqual(status["next_pi_boot"], "NORMAL BOXBRAIN")
        self.assertTrue(status["one_shot"])

    def test_import_copies_verified_image_outside_source_tree(self) -> None:
        entry = self._import("windows-11", "windows", "x86_64", b"windows-media")
        stored = Path(str(entry["path"]))
        self.assertEqual(stored.parent, self.state / "rescue-images")
        self.assertEqual(stored.read_bytes(), b"windows-media")
        self.assertEqual(entry["write_mode"], "read-only")
        self.assertEqual(entry["checksum_source"], "test-fixture")
        self.assertEqual(entry["secure_boot"]["status"], "unknown")
        self.assertTrue(self.manager.list_images()[0]["checksum_valid"])

    def test_import_rejects_checksum_mismatch(self) -> None:
        source = self._source("bad.iso", b"not-the-expected-content")
        with self.assertRaisesRegex(RescueBootError, "checksum"):
            self.manager.import_image(
                source,
                image_id="bad",
                kind="windows",
                architecture="x86_64",
                boot_compatibility=("uefi",),
                secure_boot="unknown",
                signed=None,
                expected_sha256="0" * 64,
                checksum_source="test-fixture",
                authorization=IMPORT_CONFIRMATION,
            )
        self.assertFalse((self.state / "rescue-images" / "bad.iso").exists())

    def test_kali_and_windows_profiles_are_architecture_aware(self) -> None:
        self._import("kali-arm", "kali", "arm64", b"kali-arm")
        self._import("kali-pc", "kali", "x86_64", b"kali-pc")
        self._import("windows-pc", "windows", "x86_64", b"windows-pc")
        armed = self.manager.arm(
            "rescue:kali",
            target_architecture="arm64",
            authorization=ARM_CONFIRMATION,
            require_hardware=False,
        )
        self.assertEqual(armed["pending"]["image_id"], "kali-arm")
        armed = self.manager.arm(
            "rescue:windows",
            target_architecture="x86_64",
            authorization=ARM_CONFIRMATION,
            require_hardware=False,
        )
        self.assertEqual(armed["pending"]["image_id"], "windows-pc")

    def test_consumption_resets_next_boot_before_returning_active_image(self) -> None:
        self._import("rescue-a", "custom", "x86_64", b"rescue-a")
        self.manager.arm(
            "rescue:rescue-a",
            target_architecture=None,
            authorization=ARM_CONFIRMATION,
            require_hardware=False,
        )
        consumed = self.manager.consume_early_boot()
        self.assertEqual(consumed["mode"], "rescue:rescue-a")
        self.assertEqual(self.manager.status()["pending"]["mode"], "normal")
        self.assertEqual(self.manager.active_image()["id"], "rescue-a")

        following_boot = self.manager.consume_early_boot()
        self.assertEqual(following_boot["mode"], "normal")
        self.assertIsNone(self.manager.active_image())

    def test_checksum_failure_after_arm_still_resets_following_boot(self) -> None:
        entry = self._import("rescue-b", "custom", "x86_64", b"rescue-b")
        self.manager.arm(
            "rescue:rescue-b",
            target_architecture=None,
            authorization=ARM_CONFIRMATION,
            require_hardware=False,
        )
        Path(str(entry["path"])).write_bytes(b"tampered")
        with self.assertRaisesRegex(RescueBootError, "checksum"):
            self.manager.consume_early_boot()
        self.assertEqual(self.manager.status()["pending"]["mode"], "normal")
        self.assertIsNone(self.manager.active_image())

    def test_registry_cannot_export_file_outside_dedicated_image_store(self) -> None:
        external = self._source("boxbrain-filesystem.img", b"forbidden")
        self.manager.initialize()
        registry = {
            "schema_version": 1,
            "images": [
                {
                    "id": "forbidden",
                    "kind": "custom",
                    "architecture": "x86_64",
                    "path": str(external),
                    "sha256": hashlib.sha256(b"forbidden").hexdigest(),
                    "write_mode": "read-only",
                }
            ],
        }
        self.manager.registry_path.write_text(json.dumps(registry), encoding="utf-8")
        with self.assertRaisesRegex(RescueBootError, "filesystem is forbidden"):
            self.manager.arm(
                "rescue:forbidden",
                target_architecture=None,
                authorization=ARM_CONFIRMATION,
                require_hardware=False,
            )

    def test_registry_requires_checksum_source_before_arm(self) -> None:
        self.manager.initialize()
        image = self.manager.image_directory / "legacy.img"
        image.write_bytes(b"legacy")
        registry = {
            "schema_version": 1,
            "images": [
                {
                    "id": "legacy",
                    "kind": "custom",
                    "architecture": "x86_64",
                    "path": str(image),
                    "sha256": hashlib.sha256(b"legacy").hexdigest(),
                    "write_mode": "read-only",
                }
            ],
        }
        self.manager.registry_path.write_text(json.dumps(registry), encoding="utf-8")
        with self.assertRaisesRegex(RescueBootError, "checksum source"):
            self.manager.arm(
                "rescue:legacy",
                target_architecture=None,
                authorization=ARM_CONFIRMATION,
                require_hardware=False,
            )

    def test_cancel_and_reboot_normal_require_exact_confirmation(self) -> None:
        with self.assertRaises(RescueBootError):
            self.manager.cancel(authorization="yes")
        self.assertEqual(
            self.manager.cancel(authorization=CANCEL_CONFIRMATION)["pending"]["mode"],
            "normal",
        )

        commands: list[list[str]] = []
        manager = RescueBootManager(
            self.state / "reboot",
            reboot_runner=lambda command: commands.append(command),
        )
        preview = manager.reboot_normal(
            authorization=REBOOT_NORMAL_CONFIRMATION,
            execute=False,
        )
        self.assertFalse(preview["reboot_requested"])
        manager.reboot_normal(
            authorization=REBOOT_NORMAL_CONFIRMATION,
            execute=True,
        )
        self.assertEqual(commands, [["systemctl", "reboot"]])

    def test_hardware_check_requires_pi4_configfs_and_one_udc(self) -> None:
        system = self.root / "system"
        (system / "proc/device-tree").mkdir(parents=True)
        (system / "proc/device-tree/model").write_text(
            "Raspberry Pi 4 Model B Rev 1.5\x00",
            encoding="utf-8",
        )
        (system / "sys/kernel/config/usb_gadget").mkdir(parents=True)
        (system / "sys/class/udc/fe980000.usb").mkdir(parents=True)
        manager = RescueBootManager(self.state / "hardware", system_root=system)
        result = manager.hardware_check()
        self.assertTrue(result["ready"])
        self.assertEqual(result["mass_storage_lun_count"], 0)
        self.assertEqual(result["unapproved_mass_storage_lun_count"], 0)
        self.assertFalse(result["actual_boxbrain_filesystem_exported"])

    def test_hardware_check_rejects_mass_storage_outside_rescue_store(self) -> None:
        system = self.root / "unsafe-system"
        (system / "proc/device-tree").mkdir(parents=True)
        (system / "proc/device-tree/model").write_text(
            "Raspberry Pi 4 Model B Rev 1.5\x00",
            encoding="utf-8",
        )
        lun = (
            system
            / "sys/kernel/config/usb_gadget/boxbrain/functions"
            / "mass_storage.rescue/lun.0/file"
        )
        lun.parent.mkdir(parents=True)
        lun.write_text("/dev/mmcblk0p2\n", encoding="utf-8")
        (system / "sys/class/udc/fe980000.usb").mkdir(parents=True)
        manager = RescueBootManager(self.state / "unsafe-hardware", system_root=system)

        result = manager.hardware_check()

        self.assertFalse(result["ready"])
        self.assertEqual(result["mass_storage_lun_count"], 1)
        self.assertEqual(result["unapproved_mass_storage_lun_count"], 1)
        self.assertTrue(result["actual_boxbrain_filesystem_exported"])

    def test_state_updates_create_recoverable_backups(self) -> None:
        self.manager.initialize()
        self.manager.cancel(authorization=CANCEL_CONFIRMATION)
        backups = list((self.state / "rescue/backups").glob("next-boot.json.*.bak"))
        self.assertTrue(backups)

    def test_root_state_updates_match_parent_ownership(self) -> None:
        self.manager.initialize()
        parent = self.manager.rescue_directory.stat()
        with (
            patch("boxbrain.rescue_boot.os.geteuid", return_value=0, create=True),
            patch("boxbrain.rescue_boot.os.chown", create=True) as change_owner,
        ):
            self.manager.cancel(authorization=CANCEL_CONFIRMATION)
        change_owner.assert_any_call(
            self.manager.next_boot_path,
            parent.st_uid,
            parent.st_gid,
        )

    def test_failed_state_replace_restores_previous_pending_state(self) -> None:
        self.manager.initialize()
        before = self.manager.next_boot_path.read_bytes()
        with patch("boxbrain.rescue_boot.os.replace", side_effect=OSError("simulated write failure")):
            with self.assertRaisesRegex(OSError, "simulated"):
                self.manager.cancel(authorization=CANCEL_CONFIRMATION)
        self.assertEqual(self.manager.next_boot_path.read_bytes(), before)

    def test_local_web_controls_enforce_csrf_and_exact_confirmation(self) -> None:
        system = self.root / "web-system"
        (system / "proc/device-tree").mkdir(parents=True)
        (system / "proc/device-tree/model").write_text(
            "Raspberry Pi 4 Model B\x00",
            encoding="utf-8",
        )
        (system / "sys/kernel/config/usb_gadget").mkdir(parents=True)
        (system / "sys/class/udc/fe980000.usb").mkdir(parents=True)
        manager = RescueBootManager(self.state / "web", system_root=system)
        source = self._source("web-rescue.img", b"web-rescue")
        manager.import_image(
            source,
            image_id="web-rescue",
            kind="custom",
            architecture="x86_64",
            boot_compatibility=("uefi",),
            secure_boot="unknown",
            signed=None,
            expected_sha256=hashlib.sha256(b"web-rescue").hexdigest(),
            checksum_source="test-fixture",
            authorization=IMPORT_CONFIRMATION,
        )
        server = build_server(
            "127.0.0.1",
            0,
            rescue_manager=manager,
            rescue_csrf_token="rescue-test-token",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with urlopen(f"http://{host}:{port}/rescue", timeout=3) as response:
                page = response.read().decode("utf-8")
            self.assertIn("BoxBrain One-Shot Rescue", page)
            self.assertIn("rescue-test-token", page)

            with patch.object(manager, "list_images", wraps=manager.list_images) as list_images:
                with urlopen(
                    f"http://{host}:{port}/api/v1/rescue/images",
                    timeout=3,
                ) as response:
                    images = json.load(response)
                self.assertEqual(len(images["images"]), 1)
                list_images.assert_called_once_with(verify=False)

            payload = json.dumps(
                {
                    "action": "arm",
                    "mode": "rescue:web-rescue",
                    "target_architecture": "x86_64",
                    "confirmation": ARM_CONFIRMATION,
                }
            ).encode("utf-8")
            rejected = Request(
                f"http://{host}:{port}/api/v1/rescue/control",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as error:
                urlopen(rejected, timeout=3)
            self.assertEqual(error.exception.code, 403)

            accepted = Request(
                f"http://{host}:{port}/api/v1/rescue/control",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-BoxBrain-CSRF": "rescue-test-token",
                },
                method="POST",
            )
            with urlopen(accepted, timeout=3) as response:
                result = json.load(response)
            self.assertTrue(result["ok"])
            self.assertEqual(
                result["result"]["pending"]["mode"],
                "rescue:web-rescue",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
