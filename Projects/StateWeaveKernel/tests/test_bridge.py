import unittest

from Projects.AdaptiveKernel.adaptive_kernel import CapabilityRule
from Projects.StateWeave.stateweave import State
from Projects.StateWeaveKernel.bridge import describe_plan_in_state, plan_from_state


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


if __name__ == "__main__":
    unittest.main()
