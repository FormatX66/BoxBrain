from __future__ import annotations

import unittest

from speculative_feasibility import (
    FeasibilityProbe,
    PreRunDecision,
    decide_prerun,
    expected_information_value,
)


class SpeculativeFeasibilityTests(unittest.TestCase):
    def probe(self, name: str, **changes) -> FeasibilityProbe:
        values = {
            "name": name,
            "success_probability": 0.7,
            "success_value": 3.0,
            "failure_learning_value": 1.0,
            "downstream_cost_avoided_if_failure": 1.0,
            "run_cost": 1.0,
            "risk_exposure": 0.1,
            "resource_headroom": 0.8,
        }
        values.update(changes)
        return FeasibilityProbe(**values)

    def test_high_failure_heavy_probe_runs_when_failure_saves_downstream_work(self):
        probe = self.probe(
            "tiny-seed-heavy-feasibility",
            success_probability=0.20,
            success_value=2.0,
            failure_learning_value=4.0,
            downstream_cost_avoided_if_failure=10.0,
            run_cost=5.0,
            risk_exposure=0.2,
        )
        value = expected_information_value(probe)
        self.assertGreater(value["failure_information_component"], value["success_component"])
        self.assertGreater(value["net_value"], 0.0)
        self.assertEqual(decide_prerun(probe), PreRunDecision.PRE_RUN)

    def test_heavy_probe_is_skipped_when_it_teaches_little(self):
        probe = self.probe(
            "expensive-low-information",
            success_probability=0.40,
            success_value=1.0,
            failure_learning_value=0.1,
            downstream_cost_avoided_if_failure=0.2,
            run_cost=5.0,
            risk_exposure=0.5,
        )
        self.assertLess(expected_information_value(probe)["net_value"], 0.0)
        self.assertEqual(decide_prerun(probe), PreRunDecision.SKIP_LOW_VALUE)

    def test_irreversible_or_external_work_waits_even_with_huge_information_value(self):
        probe = self.probe(
            "physical-flash",
            success_probability=0.10,
            failure_learning_value=100.0,
            downstream_cost_avoided_if_failure=100.0,
            run_cost=0.1,
            risk_exposure=0.1,
            reversible=False,
            external_side_effects=True,
        )
        self.assertGreater(expected_information_value(probe)["net_value"], 0.0)
        self.assertEqual(decide_prerun(probe), PreRunDecision.WAIT_BOUNDARY)

    def test_resource_starved_probe_waits_without_discarding_its_value(self):
        probe = self.probe(
            "valuable-but-starved",
            resource_headroom=0.05,
            minimum_resource_headroom=0.15,
            failure_learning_value=8.0,
            downstream_cost_avoided_if_failure=8.0,
        )
        self.assertGreater(expected_information_value(probe)["net_value"], 0.0)
        self.assertEqual(decide_prerun(probe), PreRunDecision.HOLD_RESOURCES)

    def test_cheap_feasibility_probe_runs_ahead(self):
        probe = self.probe(
            "cheap-build-smoke",
            success_probability=0.55,
            success_value=2.0,
            failure_learning_value=2.0,
            downstream_cost_avoided_if_failure=3.0,
            run_cost=0.25,
            risk_exposure=0.05,
        )
        self.assertEqual(decide_prerun(probe), PreRunDecision.PRE_RUN)


if __name__ == "__main__":
    unittest.main()
