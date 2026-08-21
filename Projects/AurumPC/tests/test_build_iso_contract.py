from __future__ import annotations

import unittest
from pathlib import Path


BUILD_SCRIPT = Path(__file__).parents[1] / "build-iso.sh"
BOOTSTRAP = Path(__file__).parents[1] / "aurum_bootstrap.py"
WIFI_DIAG = Path(__file__).parents[1] / "aurum_wifi_diag.py"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
QEMU_SMOKE = REPOSITORY_ROOT / "Projects" / "AurumVirtualLab" / "qemu-pc-smoke.sh"
QEMU_ACCELERATION = REPOSITORY_ROOT / "Projects" / "AurumVirtualLab" / "qemu-acceleration.sh"
HP_TWIN = REPOSITORY_ROOT / "Projects" / "AurumVirtualLab" / "qemu-hp-physical-twin.sh"
HP_TWIN_SPEC = REPOSITORY_ROOT / "Projects" / "AurumVirtualLab" / "hp-physical-twin-v1.json"
PC_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "aurum-pc-v001.yml"
HOPPER_PREPARE = REPOSITORY_ROOT / "installer" / "prepare-hopper-gui-input-test.sh"


class BuildIsoContractTests(unittest.TestCase):
    def test_physical_discovery_does_not_mount_stale_root_persistence(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")
        boot_line = next(line for line in script.splitlines() if "--bootappend-live" in line)
        self.assertNotIn("persistence", boot_line)
        self.assertNotIn("persistence-label", boot_line)
        self.assertIn("preempt=voluntary", boot_line)
        self.assertIn("transparent_hugepage=madvise", boot_line)
        self.assertIn("Projects/Codelation/autobuild/native_chain_state.json", script)
        self.assertIn("usr/lib/aurum/native-chain-state.json", script)

    def test_qemu_runtime_gate_requires_on_machine_self_build(self) -> None:
        smoke = QEMU_SMOKE.read_text(encoding="utf-8")
        acceleration = QEMU_ACCELERATION.read_text(encoding="utf-8")
        workflow = PC_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("printf 'self-build\\n'", smoke)
        self.assertIn("AURUM_SELF_BUILD_FINISHED status=passed", smoke)
        self.assertIn("timeout 900s qemu-system-x86_64", smoke)
        self.assertIn("wait_for_self_build 720", smoke)
        self.assertIn("AURUM_VIRTUAL_PC_UEFI_RUNTIME_SELF_BUILD_OK", smoke)
        self.assertIn('QEMU_ACCEL=${AURUM_QEMU_ACCEL:-tcg}', smoke)
        self.assertIn("-machine q35,accel=kvm", acceleration)
        self.assertIn("AURUM_QEMU_ACCEL=tcg", acceleration)
        self.assertIn("Projects/AurumVirtualLab/qemu-pc-smoke.sh", workflow)

    def test_live_image_contains_guarded_recovery_and_autonomy_dependencies(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("--debian-installer none", script)
        for package in (
            "aurum_installer.py", "aurum_time.py", "aurum_wifi_recovery.py", "aurum_runtime_update.py",
            "aurum_gui_runtime.py", "aurum_autonomy.py", "aurum_driver_synthesis.py", "pc01_autonomy_policy.json",
            "systemd-timesyncd", "kmod", "parted", "rsync", "dosfstools", "e2fsprogs",
            "grub-efi-amd64-bin", "grub2-common", "build-essential", "linux-headers-amd64",
            "aurum_boot_screen.py", "aurum_input.py", "libinput-tools",
        ):
            self.assertIn(package, script)
        self.assertIn("Name=en* eth* usb*", script)

    def test_hopper_input_bootstrap_and_resume_policy_are_packaged(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")
        for module in ("i2c_hid_acpi", "hid_multitouch", "psmouse", "usbhid"):
            self.assertIn(f"modprobe {module}", script)
        self.assertIn("aurum-input-bootstrap.service", script)
        self.assertIn("--apply-wake-policy", script)
        self.assertIn("system-sleep/aurum-input-wake", script)
        self.assertIn('MatchIsTouchpad "on"', script)
        self.assertIn('Option "Tapping" "on"', script)
        self.assertIn("AURUM_BOOT_SCREEN=1", script)

    def test_hopper_live_prepare_is_guarded_and_receipted(self) -> None:
        script = HOPPER_PREPARE.read_text(encoding="utf-8")
        self.assertIn("aurum/hopper-gui-input-test-20260821", script)
        self.assertIn("status --porcelain", script)
        self.assertIn("aurum_runtime_update.py\" apply", script)
        self.assertIn("systemctl restart aurum-input-bootstrap.service", script)
        self.assertIn("previous_head", script)
        self.assertIn("ready-for-physical-test", script)

    def test_qemu_gate_installs_then_boots_the_virtual_internal_disk(self) -> None:
        smoke = QEMU_SMOKE.read_text(encoding="utf-8")
        self.assertIn("AURUM_INSTALL_PLAN status=ready", smoke)
        self.assertIn("AURUM_INSTALL_FINISHED status=passed", smoke)
        self.assertIn("mode=installed", smoke)

    def test_wifi_diagnostics_are_packaged_and_automatic_when_interface_is_missing(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")
        bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
        diag = WIFI_DIAG.read_text(encoding="utf-8")
        self.assertIn("aurum_wifi_diag.py", script)
        self.assertIn("recover_existing_wifi_driver", bootstrap)
        self.assertIn("AURUM_WIFI_RECOVERY", bootstrap)
        self.assertIn("AURUM_WIFI_DIAG", bootstrap)
        self.assertIn("pci_network_candidates", diag)
        self.assertIn("read_only", diag)

    def test_hp_physical_twin_matches_observed_failure_classes(self) -> None:
        twin = HP_TWIN.read_text(encoding="utf-8")
        spec = HP_TWIN_SPEC.read_text(encoding="utf-8")
        workflow = PC_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("-m 7680", twin)
        self.assertIn("-device nvme", twin)
        self.assertIn("usb-storage,drive=seed", twin)
        self.assertIn("set_link hpeth off", twin)
        self.assertIn('mkfifo "$monitor.in" "$monitor.out"', twin)
        self.assertIn("printf 'set_link hpeth off\\n' >&4", twin)
        self.assertIn("2026-04-27T19:50:12", twin)
        self.assertIn("AURUM_HP_TWIN_NVME_PRESERVED_OK", twin)
        self.assertIn('} | tee -a "$LOG"', twin)
        self.assertIn("wifi-interface-missing", spec)
        self.assertIn("qemu-hp-physical-twin.sh", workflow)


if __name__ == "__main__":
    unittest.main()
