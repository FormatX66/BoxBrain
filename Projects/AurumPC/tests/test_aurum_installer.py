from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "aurum_installer.py"
SPEC = importlib.util.spec_from_file_location("aurum_installer", MODULE_PATH)
assert SPEC and SPEC.loader
installer_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer_module)


def inventory() -> dict:
    return {
        "blockdevices": [
            {
                "name": "/dev/nvme0n1",
                "kname": "nvme0n1",
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
                "model": "Mounted internal disk",
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
                        "mountpoints": ["/mnt/existing"],
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
        if arguments[0] != "lsblk":
            raise AssertionError(f"unexpected command: {arguments}")
        return subprocess.CompletedProcess(arguments, 0, json.dumps(self.payload), "")


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

    def test_plan_offers_only_unmounted_non_usb_internal_disks(self) -> None:
        plan = self.make_installer().plan()

        self.assertTrue(plan["available"])
        self.assertEqual(plan["mode"], "guided-whole-disk-uefi")
        self.assertEqual(len(plan["targets"]), 1)
        target = plan["targets"][0]
        self.assertEqual(target["device"], "/dev/nvme0n1")
        self.assertEqual(target["model"], "Internal NVMe")
        self.assertRegex(target["confirmation_code"], r"^ERASE-[A-F0-9]{8}$")
        self.assertEqual(
            target["confirm_command"],
            f"install confirm {target['confirmation_code']}",
        )
        self.assertEqual(target["existing_partitions"][0]["label"], "Windows")

    def test_plan_refuses_installed_or_legacy_boot_runtime(self) -> None:
        self.live.rmdir()
        plan = self.make_installer().plan()
        self.assertFalse(plan["available"])
        self.assertEqual(plan["reason"], "installer-runs-only-from-aurum-live-media")

        self.live.mkdir(parents=True)
        self.efi.rmdir()
        plan = self.make_installer().plan()
        self.assertFalse(plan["available"])
        self.assertEqual(plan["reason"], "uefi-boot-required")

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


if __name__ == "__main__":
    unittest.main()
