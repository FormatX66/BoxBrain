from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "aurum-pi3-kernel-canary-preflight.yml"


class Pi3KernelCanaryPreflightWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_physical_watchdog_receipt_has_a_fail_closed_consumption_path(self):
        for token in (
            "pi3-oob-watchdog-physical.json",
            "physical_watchdog_receipt.py",
            "physical-watchdog-receipt-invalid",
            "physical_proof_validated",
            "physical_proof_inferred",
            "watchdog_receipt_sha256",
        ):
            self.assertIn(token, self.text)

    def test_missing_receipt_remains_a_hold_and_never_grants_mutation(self):
        self.assertIn("$outOfBandWatchdogProven = $false", self.text)
        self.assertIn("$watchdogReceiptState = 'missing'", self.text)
        self.assertIn("$explicitKernelMutationAuthority = $false", self.text)
        self.assertIn("mutation_allowed=false", self.text)

    def test_validator_uses_the_farmer_pinned_python_runtime(self):
        for token in (
            "BoxBrain\\AurumFarmer\\runtime",
            "install-receipt.json",
            "python_exe",
            "farmer-python-receipt-missing",
        ):
            self.assertIn(token, self.text)


if __name__ == "__main__":
    unittest.main()
