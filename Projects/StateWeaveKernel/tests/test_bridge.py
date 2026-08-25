import unittest

from Projects.AdaptiveKernel.adaptive_kernel import CapabilityRule
from Projects.AdaptiveKernel.runtime import (
    AdaptiveKernelRuntime,
    RealizationCandidate,
)
from Projects.StateWeave.stateweave import State
from Projects.StateWeaveKernel.bridge import (
    describe_future_branches_in_state,
    describe_plan_in_state,
    future_branches_from_state,
    plan_from_state,
)


class StateWeaveKernelBridgeTests(unittest.TestCase):
    def test_state_facts_drive_kernel_plan(self):
        state = State.from_mapping({"fact.input.pointer": True, "fact.net.link": False})
        rules = [
            CapabilityRule("pointer", ("input.pointer",), ("pointer",)),
            CapabilityRule("network", ("net.link",), ("network",)),
        ]
        kernel_plan = plan_from_state(state, rules)
        self.assertEqual([c.rule.name for c in kernel_plan.selected], ["pointer"])
        self.assertEqual([c.rule.name for c in kernel_plan.rejected], ["network"])

        result = describe_plan_in_state(state, kernel_plan).as_dict()
        self.assertTrue(result["kernel.capability.pointer"])
        self.assertEqual(result["kernel.plan.selected_count"], 1)
        self.assertEqual(result["kernel.plan.rejected_count"], 1)

    def test_combined_lane_does_not_bypass_high_risk_gate(self):
        state = State.from_mapping({"fact.hardware.present": True})
        rules = [CapabilityRule("dangerous", ("hardware.present",), ("dangerous",), risk="high")]
        kernel_plan = plan_from_state(state, rules)
        self.assertEqual(kernel_plan.selected, ())
        result = describe_plan_in_state(state, kernel_plan).as_dict()
        self.assertNotIn("kernel.capability.dangerous", result)

    def test_combined_lane_records_warm_futures_and_contradictory_evidence(self):
        state = State.from_mapping(
            {
                "fact.input.pointer": True,
                "fact.resume.stable": False,
                "kernel.active": "proven-A",
            }
        )
        rules = [
            CapabilityRule(
                "pointer-next",
                ("input.pointer", "resume.stable"),
                ("pointer-v2",),
            )
        ]

        proposals = future_branches_from_state(
            state,
            rules,
            rollback_target="proven-A",
        )
        self.assertEqual(proposals[0]["status"], "warm")
        self.assertEqual(proposals[0]["confidence"], 0.5)
        self.assertFalse(proposals[0]["evidence"][1]["supports"])

        recorded = describe_future_branches_in_state(state, proposals).as_dict()
        self.assertEqual(recorded["future.branch.kernel-pointer-next.status"], "warm")
        self.assertEqual(
            recorded["future.branch.kernel-pointer-next.rollback_target"],
            "proven-A",
        )
        self.assertEqual(
            recorded["future.branch.kernel-pointer-next.basis_state_digest"],
            state.digest(),
        )
        self.assertFalse(
            recorded["future.branch.kernel-pointer-next.evidence.1.supports"]
        )
        self.assertEqual(recorded["kernel.active"], "proven-A")

    def test_stateweave_plan_can_enter_bounded_generation_one_runtime(self):
        state = State.from_mapping(
            {
                "fact.input.pointer": True,
                "kernel.active": "proven-A",
            }
        )
        rules = [CapabilityRule("pointer", ("input.pointer",), ("pointer",))]
        kernel_plan = plan_from_state(state, rules)
        runtime = AdaptiveKernelRuntime(state.as_dict())
        realization = RealizationCandidate(
            candidate_id="pointer-simulated",
            rule_name="pointer",
            propose=lambda current: {
                **current,
                "kernel.capability.pointer": True,
            },
            confidence=0.8,
            cost=0.2,
        )

        run = runtime.adapt(kernel_plan, [realization])

        self.assertEqual(run.status, "success")
        self.assertTrue(run.final_state["kernel.capability.pointer"])
        self.assertEqual(run.final_state["kernel.active"], "proven-A")
        self.assertEqual(run.attempts[0].reason, "verified")


if __name__ == "__main__":
    unittest.main()
