import unittest

from Projects.AdaptiveKernel.adaptive_kernel import CapabilityRule, plan


class AdaptiveKernelTests(unittest.TestCase):
    def test_complete_low_risk_rule_is_selected(self):
        rules = [CapabilityRule("pointer", ("input.pointer",), ("pointer",))]
        result = plan({"input.pointer": True}, rules)
        self.assertEqual([c.rule.name for c in result.selected], ["pointer"])
        self.assertEqual(result.rejected, ())

    def test_missing_evidence_is_rejected(self):
        rules = [CapabilityRule("network", ("net.link", "net.stack"), ("network",))]
        result = plan({"net.link": True, "net.stack": False}, rules)
        self.assertEqual(result.selected, ())
        self.assertEqual(result.rejected[0].confidence, 0.5)

    def test_non_low_risk_rule_never_auto_selects(self):
        rules = [CapabilityRule("firmware-write", (), ("firmware-write",), risk="high")]
        result = plan({}, rules)
        self.assertEqual(result.selected, ())
        self.assertEqual(result.rejected[0].rule.name, "firmware-write")


if __name__ == "__main__":
    unittest.main()
