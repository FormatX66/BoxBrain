from __future__ import annotations

import unittest
from pathlib import Path


BUILD_SCRIPT = Path(__file__).parents[1] / "build-iso.sh"
CONSOLE = Path(__file__).parents[1] / "aurum_console.py"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
QEMU_SMOKE = REPOSITORY_ROOT / "Projects" / "AurumVirtualLab" / "qemu-pc-smoke.sh"
PC_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "aurum-pc-v001.yml"


class BuildIsoContractTests(unittest.TestCase):
    def test_boot_requests_only_the_aurum_persistence_volume(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")

        self.assertIn(" persistence ", script)
        self.assertIn("persistence-label=AURUM_PERSIST", script)
        self.assertIn("preempt=voluntary", script)
        self.assertIn("transparent_hugepage=madvise", script)
        self.assertIn("Projects/Codelation/autobuild/native_chain_state.json", script)
        self.assertIn("usr/lib/aurum/native-chain-state.json", script)

    def test_pc01_wired_network_and_resolver_are_in_the_image(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")
        console = CONSOLE.read_text(encoding="utf-8")

        self.assertIn("Name=en* eth*", script)
        self.assertIn("DHCP=yes", script)
        self.assertIn("systemd-networkd.service", script)
        self.assertIn("systemd-resolved.service", script)
        self.assertIn("/run/systemd/resolve/stub-resolv.conf", script)
        self.assertIn("network-status", console)
        self.assertIn("network-repair", console)
        self.assertIn("getent", console)
        self.assertIn("github.com", console)

    def test_qemu_runtime_gate_requires_on_machine_self_build(self) -> None:
        smoke = QEMU_SMOKE.read_text(encoding="utf-8")
        workflow = PC_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("printf 'self-build\\n'", smoke)
        self.assertIn("AURUM_SELF_BUILD_FINISHED status=passed", smoke)
        self.assertIn("timeout 900s qemu-system-x86_64", smoke)
        self.assertIn("wait_for_self_build 720", smoke)
        self.assertIn("Projects/AurumVirtualLab/qemu-pc-smoke.sh", workflow)

    def test_pc01_qemu_gate_exercises_network_readonly_nvme_git_and_reboot(self) -> None:
        smoke = QEMU_SMOKE.read_text(encoding="utf-8")

        self.assertIn("-nic user,model=virtio-net-pci", smoke)
        self.assertIn("PC01NVME0001", smoke)
        self.assertIn("readonly=on", smoke)
        self.assertIn("AURUM_NETWORK_REPAIR status=ready", smoke)
        self.assertIn("AURUM_STORAGE_STATUS status=ok", smoke)
        self.assertIn("readonly_nvme=1", smoke)
        self.assertIn("git-sync authorize-network", smoke)
        self.assertIn('/var/lib/aurum/workspace/BoxBrain', smoke)
        self.assertIn("AURUM_PC_REBOOT requested=true", smoke)

    def test_live_image_contains_only_the_guarded_installer_path(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("--debian-installer none", script)
        self.assertIn("aurum_installer.py", script)
        for package in (
            "parted",
            "rsync",
            "dosfstools",
            "e2fsprogs",
            "grub-efi-amd64-bin",
            "grub2-common",
        ):
            self.assertIn(package, script)

    def test_qemu_gate_installs_then_boots_the_virtual_internal_disk(self) -> None:
        smoke = QEMU_SMOKE.read_text(encoding="utf-8")

        self.assertIn("AURUM_INSTALL_PLAN status=ready", smoke)
        self.assertIn("AURUM_INSTALL_FINISHED status=passed", smoke)
        self.assertIn("mode=installed", smoke)
        self.assertIn("AURUM_INSTALL_TARGET device=/dev/nvme", smoke)
        self.assertIn("incorrectly offered the read-only NVMe", smoke)


if __name__ == "__main__":
    unittest.main()
