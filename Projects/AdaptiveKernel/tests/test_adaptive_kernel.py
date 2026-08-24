import unittest

from Projects.AdaptiveKernel.adaptive_kernel import (
    CapabilityRule,
    future_branch_proposals,
    plan,
)


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

    def test_future_branch_proposal_preserves_missing_evidence(self):
        proposals = future_branch_proposals(
            {"net.link": True, "net.stack": False},
            [CapabilityRule("network", ("net.link", "net.stack"), ("network",))],
        )
        proposal = proposals[0]
        self.assertEqual(proposal["branch_id"], "kernel-network")
        self.assertEqual(proposal["confidence"], 0.5)
        self.assertEqual(proposal["rollback_target"], "current-proven-kernel")
        self.assertTrue(proposal["evidence"][0]["supports"])
        self.assertFalse(proposal["evidence"][1]["supports"])

    def test_high_risk_future_requires_authority_instead_of_auto_selection(self):
        proposal = future_branch_proposals(
            {},
            [CapabilityRule("firmware write", (), ("firmware-write",), risk="high")],
        )[0]
        self.assertEqual(proposal["branch_id"], "kernel-firmware-write")
        self.assertGreater(proposal["risk"], 0.8)
        self.assertTrue(proposal["requires_authorization"])
        self.assertFalse(proposal["authorized"])


if __name__ == "__main__":
    unittest.main()
