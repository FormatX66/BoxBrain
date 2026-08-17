from __future__ import annotations

import json
import unittest
from pathlib import Path


BUILD_SCRIPT = Path(__file__).parents[1] / "build-iso.sh"
WORKSPACE_SCRIPT = Path(__file__).parents[1] / "aurum_workspace.py"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
QEMU_SMOKE = REPOSITORY_ROOT / "Projects" / "AurumVirtualLab" / "qemu-pc-smoke.sh"
PC_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "aurum-pc-v001.yml"
NATIVE_STATE = REPOSITORY_ROOT / "Projects" / "Codelation" / "autobuild" / "native_chain_state.json"


class BuildIsoContractTests(unittest.TestCase):
    def test_live_boot_ignores_stale_persistence_and_has_git_trust_bootstrap(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn(" persistence ", script)
        self.assertNotIn("persistence-label=AURUM_PERSIST", script)
        self.assertIn("preempt=voluntary", script)
        self.assertIn("transparent_hugepage=madvise", script)
        self.assertIn("Projects/Codelation/autobuild/native_chain_state.json", script)
        self.assertIn("usr/lib/aurum/native-chain-state.json", script)
        self.assertIn("systemd-timesyncd", script)
        self.assertIn("SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt", script)
        self.assertIn("GIT_SSL_CAINFO=/etc/ssl/certs/ca-certificates.crt", script)
        self.assertIn("git config --system http.sslCAInfo /etc/ssl/certs/ca-certificates.crt", script)
        self.assertIn("modprobe.blacklist=nouveau", script)
        self.assertIn("nouveau.modeset=0", script)
        self.assertIn('BRANCH = "aurum/trunk-v0.01"', WORKSPACE_SCRIPT.read_text(encoding="utf-8"))

    def test_pc01_wired_interface_is_covered_by_debian_networkd_and_dns(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("--distribution bookworm", script)
        self.assertIn("Name=en* eth*", script)
        self.assertTrue("enp4s0".startswith(("en", "eth")))
        self.assertIn("DHCP=yes", script)
        self.assertIn("systemd-networkd.service", script)
        self.assertIn("systemd-resolved.service", script)
        self.assertIn("/run/systemd/resolve/stub-resolv.conf", script)

    def test_authoritative_checkpoint_remains_generation_64(self) -> None:
        state = json.loads(NATIVE_STATE.read_text(encoding="utf-8"))

        self.assertEqual(state["completed_generations"], 64)
        self.assertEqual(state["blocked_reason"], "generation-bound-reached")

    def test_qemu_runtime_gate_requires_on_machine_self_build(self) -> None:
        smoke = QEMU_SMOKE.read_text(encoding="utf-8")
        workflow = PC_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("printf 'self-build\\n'", smoke)
        self.assertIn("AURUM_SELF_BUILD_FINISHED status=passed", smoke)
        self.assertIn("timeout 900s qemu-system-x86_64", smoke)
        self.assertIn("wait_for_self_build 720", smoke)
        self.assertIn("AURUM_VIRTUAL_PC_UEFI_RUNTIME_SELF_BUILD_OK", smoke)
        self.assertIn('"completed_generations": 64', smoke)
        self.assertIn('"blocked_reason": "generation-bound-reached"', smoke)
        self.assertIn("Projects/AurumVirtualLab/qemu-pc-smoke.sh", workflow)

    def test_qemu_gate_covers_pc01_runtime_surfaces_without_touching_nvme(self) -> None:
        smoke = QEMU_SMOKE.read_text(encoding="utf-8")

        self.assertIn("readonly=on,id=nvme-sentinel", smoke)
        self.assertIn("AURUMROPC01", smoke)
        self.assertIn("nvme_sha_after", smoke)
        self.assertIn("network-status", smoke)
        self.assertIn("AURUM_NETWORK status=ready", smoke)
        self.assertIn("git-sync authorize-network", smoke)
        self.assertIn('"configured_branch": "aurum/trunk-v0.01"', smoke)
        self.assertIn("printf 'reboot\\n'", smoke)
        self.assertIn("printf 'poweroff\\n'", smoke)
        self.assertIn("seed-status", smoke)
        self.assertIn("AURUM_VIRTUAL_PC_PERSISTENCE_REBOOT_OK", smoke)
        self.assertIn("AURUM_VIRTUAL_PC_READ_ONLY_NVME_OK", smoke)
        self.assertIn("AURUM_VIRTUAL_PC_REBOOT_POWEROFF_CLEANUP_OK", smoke)

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


if __name__ == "__main__":
    unittest.main()
