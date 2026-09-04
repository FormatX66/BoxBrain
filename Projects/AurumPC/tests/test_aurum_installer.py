from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import json
from copy import deepcopy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "aurum_installer.py"
SPEC = importlib.util.spec_from_file_location("aurum_installer", MODULE_PATH)
assert SPEC and SPEC.loader
installer_module = importlib.util.module_from_spec(SPEC)
# Python 3.12 dataclasses resolve annotations through sys.modules while the
# class decorators execute.  Register the deliberately direct-loaded test
# module before exec_module so this harness matches normal import semantics.
sys.modules[SPEC.name] = installer_module
SPEC.loader.exec_module(installer_module)


def inventory() -> dict:
    return {
        "blockdevices": [
            {
                "name": "/dev/nvme0n1",
                "kname": "/dev/nvme0n1",
                "path": "/dev/nvme0n1",
                "type": "disk",
                "size": 512_000_000_000,
                "model": "Internal NVMe",
                "serial": "NVME-SERIAL-1",
                "tran": "nvme",
                "rm": False,
                "ro": False,
                "hotplug": False,
                "mountpoints": [None],
                "children": [
                    {
                        "name": "/dev/nvme0n1p1",
                        "path": "/dev/nvme0n1p1",
                        "type": "part",
                        "size": 511_000_000_000,
                        "fstype": "ntfs",
                        "label": "Windows",
                        "mountpoints": [None],
                    }
                ],
            },
            {
                "name": "/dev/sda",
                "kname": "sda",
                "path": "/dev/sda",
                "type": "disk",
                "size": 16_000_000_000,
                "model": "Aurum USB",
                "serial": "USB-SERIAL",
                "tran": "usb",
                "rm": True,
                "ro": False,
                "hotplug": True,
                "mountpoints": [None],
            },
            {
                "name": "/dev/sdb",
                "kname": "sdb",
                "path": "/dev/sdb",
                "type": "disk",
                "size": 64_000_000_000,
                "model": "Protected active internal disk",
                "serial": "MOUNTED-SERIAL",
                "tran": "sata",
                "rm": False,
                "ro": False,
                "hotplug": False,
                "mountpoints": [None],
                "children": [
                    {
                        "name": "/dev/sdb1",
                        "path": "/dev/sdb1",
                        "type": "part",
                        "size": 63_000_000_000,
                        "fstype": "ext4",
                        "label": "mounted",
                        "mountpoints": ["/"],
                    }
                ],
            },
        ]
    }


class FakeRunner:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[list[str]] = []

    def __call__(self, arguments: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        self.calls.append(arguments)
        stdout = json.dumps(self.payload) if arguments[0] == "lsblk" else ""
        return subprocess.CompletedProcess(arguments, 0, stdout, "")


class RecordingInstaller(installer_module.AurumInstaller):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.selected = None

    @contextmanager
    def _exclusive_install(self):
        yield

    def _execute(self, target, callback):
        self.selected = target
        return {"status": "installed", "device": target.device}


class AurumInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.live = self.root / "run" / "live" / "medium"
        self.efi = self.root / "sys" / "firmware" / "efi"
        self.live.mkdir(parents=True)
        self.efi.mkdir(parents=True)
        self.runner = FakeRunner(inventory())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_installer(self, cls=installer_module.AurumInstaller):
        return cls(
            runner=self.runner,
            live_medium=self.live,
            efi_runtime=self.efi,
            sys_block=self.root / "sys" / "class" / "block",
            install_lock=self.root / "run" / "install.lock",
            install_work=self.root / "run" / "install",
        )

    def test_plan_offers_only_non_usb_non_active_internal_disks(self) -> None:
        plan = self.make_installer().plan()
        self.assertTrue(plan["available"])
        self.assertEqual(plan["mode"], "guided-whole-disk-dual-boot")
        self.assertEqual(plan["live_boot_mode"], "uefi")
        self.assertEqual(len(plan["targets"]), 1)
        target = plan["targets"][0]
        self.assertEqual(target["device"], "/dev/nvme0n1")
        self.assertEqual(target["kernel_name"], "nvme0n1")
        self.assertEqual(target["model"], "Internal NVMe")
        self.assertRegex(target["confirmation_code"], r"^ERASE-[A-F0-9]{8}$")
        self.assertEqual(target["confirm_command"], f"install confirm {target['confirmation_code']}")
        self.assertEqual(target["existing_partitions"][0]["label"], "Windows")
        self.assertFalse(target["repair_available"])

    def test_plan_refuses_installed_runtime_but_allows_legacy_live_boot(self) -> None:
        self.live.rmdir()
        plan = self.make_installer().plan()
        self.assertFalse(plan["available"])
        self.assertEqual(plan["reason"], "installer-runs-only-from-aurum-live-media")
        self.live.mkdir(parents=True)
        self.efi.rmdir()
        plan = self.make_installer().plan()
        self.assertTrue(plan["available"])
        self.assertEqual(plan["live_boot_mode"], "legacy")

    def test_safe_live_automount_is_eligible_and_released_before_erasing(self) -> None:
        payload = deepcopy(inventory())
        payload["blockdevices"][0]["children"][0]["mountpoints"] = ["/media/old-aurum"]
        self.runner = FakeRunner(payload)
        installer = self.make_installer()
        target = installer.discover_targets()[0]
        self.assertEqual(target.existing_partitions[0]["mountpoints"], ("/media/old-aurum",))
        installer._release_existing_mounts(target)
        self.assertIn(["umount", "/media/old-aurum"], self.runner.calls)

    def test_wrong_or_stale_confirmation_never_reaches_destructive_executor(self) -> None:
        installer = self.make_installer(RecordingInstaller)
        with self.assertRaisesRegex(installer_module.InstallError, "exactly one eligible"):
            installer.install("ERASE-00000000")
        self.assertIsNone(installer.selected)

    def test_current_device_specific_confirmation_selects_only_that_disk(self) -> None:
        installer = self.make_installer(RecordingInstaller)
        code = installer.plan()["targets"][0]["confirmation_code"]
        result = installer.install(code)
        self.assertEqual(result, {"status": "installed", "device": "/dev/nvme0n1"})
        self.assertEqual(installer.selected.device, "/dev/nvme0n1")

    def test_missing_fixed_tool_is_reported_without_an_unhandled_traceback(self) -> None:
        def missing_runner(arguments: list[str], **_kwargs):
            raise FileNotFoundError(2, "No such file or directory", arguments[0])
        installer = installer_module.AurumInstaller(runner=missing_runner)
        with self.assertRaisesRegex(installer_module.InstallError, "lsblk is unavailable"):
            installer.discover_targets()

    def test_machine_identity_is_generated_for_the_selected_pc(self) -> None:
        target = self.make_installer().discover_targets()[0]
        installed = self.root / "installed"
        (installed / "opt" / "aurum").mkdir(parents=True)
        (installed / "etc").mkdir(parents=True)
        (installed / "opt" / "aurum" / "pc01_autonomy_policy.json").write_text(
            json.dumps({"schema": "aurum-pc-autonomy-policy-v1", "enabled": True}),
            encoding="utf-8",
        )
        receipt = {"schema": installer_module.INSTALLER_SCHEMA, "target": {}}
        installer_module.AurumInstaller._write_machine_identity(installed, target, receipt)
        policy = json.loads((installed / "opt" / "aurum" / "pc01_autonomy_policy.json").read_text())
        self.assertEqual(policy["machine_display_name"], "Aurum PC")
        self.assertEqual(policy["hostname"], "aurum-pc")
        self.assertEqual(policy["machine_match"]["installed_target_serial"], "NVME-SERIAL-1")

    def test_boot_config_has_only_normal_and_graphics_recovery_entries(self) -> None:
        target = self.make_installer().discover_targets()[0]
        installed = self.root / "installed"
        (installed / "boot").mkdir(parents=True)
        (installed / "boot" / "vmlinuz-6.1-test").write_bytes(b"kernel")
        (installed / "boot" / "initrd.img-6.1-test").write_bytes(b"initrd")

        installer_module.AurumInstaller._write_boot_config(installed, "abcd-1234", target)

        grub = (installed / "boot" / "grub" / "grub.cfg").read_text(encoding="utf-8")
        self.assertEqual(grub.count("menuentry "), 2)
        self.assertIn("menuentry 'Aurum PC'", grub)
        self.assertIn("menuentry 'Aurum PC (graphics recovery)'", grub)
        self.assertIn("set default=0\nset timeout=5", grub)
        self.assertEqual(grub.count("root=UUID=abcd-1234"), 2)
        self.assertEqual(grub.count("nomodeset"), 1)
        self.assertNotIn("nouveau.modeset=0", grub)

    def test_hopper_normal_boot_excludes_only_the_failed_nouveau_path(self) -> None:
        target = installer_module.InstallTarget(
            device="/dev/nvme0n1",
            kernel_name="nvme0n1",
            model="Hopper internal drive",
            serial=installer_module.HOPPER_TARGET_SERIAL,
            transport="nvme",
            size_bytes=installer_module.HOPPER_TARGET_SIZE_BYTES,
            size_gib=round(installer_module.HOPPER_TARGET_SIZE_BYTES / (1024**3), 1),
            existing_partitions=(),
            confirmation_code="ERASE-12345678",
        )
        installed = self.root / "hopper-installed"
        (installed / "boot").mkdir(parents=True)
        (installed / "boot" / "vmlinuz-6.1-test").write_bytes(b"kernel")
        (installed / "boot" / "initrd.img-6.1-test").write_bytes(b"initrd")

        installer_module.AurumInstaller._write_boot_config(installed, "abcd-1234", target)

        grub = (installed / "boot" / "grub" / "grub.cfg").read_text(encoding="utf-8")
        normal, recovery = grub.split("menuentry 'Aurum PC (graphics recovery)'", maxsplit=1)
        self.assertIn("modprobe.blacklist=nouveau nouveau.modeset=0", normal)
        self.assertNotIn("nomodeset", normal)
        self.assertIn("nomodeset", recovery)
        self.assertNotIn("modprobe.blacklist=nouveau", recovery)

    def test_repair_detection_requires_exact_aurum_partition_labels(self) -> None:
        payload = deepcopy(inventory())
        payload["blockdevices"][0]["children"] = [
            {
                "name": "/dev/nvme0n1p2", "path": "/dev/nvme0n1p2", "type": "part",
                "size": 512_000_000, "fstype": "vfat", "label": "AURUM_EFI", "mountpoints": [None],
            },
            {
                "name": "/dev/nvme0n1p3", "path": "/dev/nvme0n1p3", "type": "part",
                "size": 511_000_000_000, "fstype": "ext4", "label": "AURUM_ROOT", "mountpoints": [None],
            },
        ]
        self.runner = FakeRunner(payload)
        installer = self.make_installer()
        plan = installer.plan()
        self.assertTrue(plan["targets"][0]["repair_available"])
        efi, root = installer._repair_partitions(installer.discover_targets()[0])
        self.assertEqual(efi.as_posix(), "/dev/nvme0n1p2")
        self.assertEqual(root.as_posix(), "/dev/nvme0n1p3")


if __name__ == "__main__":
    unittest.main()
