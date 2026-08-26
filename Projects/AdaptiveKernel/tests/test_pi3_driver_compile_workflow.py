from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "aurum-pi3-driver-candidate-compile-only.yml"


class Pi3DriverCompileWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_is_manual_compile_only_and_serialized_with_kernel_lab(self):
        self.assertIn("workflow_dispatch:", self.text)
        self.assertNotIn("pull_request:", self.text)
        self.assertNotIn("branches:", self.text)
        self.assertIn("group: aurum-pi3-adaptive-kernel-overnight", self.text)
        self.assertIn("compile_only.py", self.text)

    def test_strict_pinned_key_only_identity_and_exact_board_are_required(self):
        for token in (
            "BatchMode=yes",
            "PasswordAuthentication=no",
            "KbdInteractiveAuthentication=no",
            "IdentitiesOnly=yes",
            "StrictHostKeyChecking=yes",
            "pi3_known_hosts",
            "Raspberry Pi 3 Model B Rev 1.2",
            "smsc95xx",
            "/dev/mmcblk0p2",
        ):
            self.assertIn(token, self.text)

    def test_workflow_has_no_loader_installer_binding_or_sudo_command(self):
        lowered = self.text.casefold()
        for forbidden in (
            "insmod ",
            "modprobe ",
            "depmod ",
            "modules_install",
            "driver_override",
            "/bind",
            "/unbind",
            "sudo ",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_receipts_preserve_zero_authority_and_cleanup(self):
        for token in (
            "verified-inert-artifact",
            "temporary_build_removed",
            "loader_invoked",
            "installer_invoked",
            "module_load_allowed = $false",
            "driver_binding_change_allowed = $false",
            "replacement_kernel_allowed = $false",
            "mutation_authority_granted = $false",
            "Remove remote temporary compile directory",
            "Remove staged Pi3 SSH identity",
        ):
            self.assertIn(token, self.text)

    def test_windows_runner_uses_farmer_python_and_base64_cleanup_script(self):
        for token in (
            "AurumFarmer\\runtime",
            "install-receipt.json",
            "python_exe",
            "runner-control.json",
            "$cleanupEncoded",
            "base64 -d | sh",
        ):
            self.assertIn(token, self.text)


if __name__ == "__main__":
    unittest.main()
