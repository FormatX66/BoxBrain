from __future__ import annotations

import unittest

from Projects.Codelation.state_space import (
    ConvergenceFabric,
    ConvergenceStage,
    FiniteStateSolver,
    Variable,
)


class ConvergenceFabricTests(unittest.TestCase):
    def test_converged_subsystems_are_composed_by_contract_not_cross_product(self) -> None:
        boot = FiniteStateSolver(
            variables=(
                Variable("firmware", ("uefi", "bios")),
                Variable("media", ("usb", "disk", "embedded")),
            ),
            convergence_stages=(
                ConvergenceStage("payload-ready", lambda state: ("payload-ready",)),
            ),
        )
        runtime = FiniteStateSolver(
            variables=(
                Variable("mode", ("interactive", "headless")),
                Variable("network", ("online", "offline")),
            ),
            convergence_stages=(
                ConvergenceStage("runtime-ready", lambda state: ("runtime-ready",)),
            ),
        )

        report = ConvergenceFabric({"boot": boot, "runtime": runtime}).solve()

        self.assertEqual(report.naive_cross_product_states, 24)
        self.assertEqual(report.factorized_raw_cases, 10)
        self.assertEqual(report.factorized_valid_cases, 10)
        self.assertEqual(report.terminal_contract_classes, 1)
        self.assertTrue(report.all_subsystems_converged)
        self.assertLess(report.factorized_raw_cases, report.naive_cross_product_states)


if __name__ == "__main__":
    unittest.main()
