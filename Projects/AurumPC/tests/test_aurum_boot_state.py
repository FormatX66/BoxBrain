from __future__ import annotations

import unittest

from Projects.AurumPC.aurum_boot_state import (
    FAILURE_RECOVERIES,
    PC01_BOOT_OBSERVATION,
    all_test_world_recoveries_are_autonomous,
    boot_solver,
    recovery_for,
)


class AurumBootStateTests(unittest.TestCase):
    def test_bounded_state_space_prunes_and_converges(self) -> None:
        report = boot_solver().solve()
        self.assertGreater(report.raw_states, report.valid_states)
        self.assertGreater(report.valid_states, 0)
        self.assertEqual(report.pruned_states, report.raw_states - report.valid_states)

        counts = [report.valid_states, *(count for _, count in report.convergence)]
        self.assertEqual(counts, sorted(counts, reverse=True))
        self.assertEqual(report.convergence[-1], ("aurum-runtime-ready", 1))

    def test_known_impossible_loader_states_are_rejected(self) -> None:
        solver = boot_solver()
        base = {
            "firmware": "uefi",
            "media_layout": "gpt",
            "boot_filesystem": "fat",
            "loader": "grub_efi",
            "payload_strategy": "same_device_signature",
            "storage_transport": "usb_msd",
            "root_strategy": "label_signature",
            "display": "efi_gop",
            "network": "wired_link",
        }
        self.assertTrue(solver.is_valid(base))

        bios_with_efi = dict(base, firmware="bios")
        self.assertFalse(solver.is_valid(bios_with_efi))
        self.assertIn("bios-cannot-use-efi-loader", solver.rejection_reasons(bios_with_efi))

        uefi_with_bios_loader = dict(base, loader="syslinux_bios")
        self.assertFalse(solver.is_valid(uefi_with_bios_loader))
        self.assertIn("uefi-cannot-use-bios-loader", solver.rejection_reasons(uefi_with_bios_loader))

        direct_efi_on_ext = dict(base, loader="direct_efi", boot_filesystem="ext")
        self.assertFalse(solver.is_valid(direct_efi_on_ext))
        self.assertIn("direct-efi-needs-fat", solver.rejection_reasons(direct_efi_on_ext))

    def test_pc01_grub_shell_is_now_a_model_input_not_a_human_procedure(self) -> None:
        self.assertEqual(PC01_BOOT_OBSERVATION["observation"], "grub-shell-config-unreadable")
        recovery = recovery_for("grub-shell-config-unreadable")
        self.assertFalse(recovery.requires_operator_in_test_world)
        self.assertEqual(recovery.converges_to, "payload-verified")
        for action in (
            "validate-efi-image-self-location",
            "embed-rescue-config",
            "embed-partition-and-filesystem-modules",
            "scan-boot-device-by-signature",
            "verify-kernel-and-initrd-before-release",
            "emit-machine-readable-evidence",
        ):
            self.assertIn(action, recovery.actions)

    def test_every_test_world_failure_has_an_autonomous_recovery_path(self) -> None:
        self.assertTrue(all_test_world_recoveries_are_autonomous())
        self.assertGreaterEqual(len(FAILURE_RECOVERIES), 10)
        for recovery in FAILURE_RECOVERIES:
            self.assertTrue(recovery.detection)
            self.assertTrue(recovery.actions)
            self.assertTrue(recovery.converges_to)
            self.assertFalse(any("operator-shell" in action for action in recovery.actions))
            self.assertFalse(any("ask-human" in action for action in recovery.actions))

    def test_unknown_physical_evidence_expands_then_replays_the_model(self) -> None:
        recovery = recovery_for("unmodeled-physical-observation")
        self.assertTrue(recovery.physical_only)
        self.assertEqual(recovery.converges_to, "observation-ingested")
        self.assertEqual(
            recovery.actions,
            (
                "record-observation",
                "derive-minimal-new-variable-or-domain-value",
                "fork-hypothesis-branch",
                "replay-virtual-state-space-with-new-evidence",
            ),
        )


if __name__ == "__main__":
    unittest.main()
