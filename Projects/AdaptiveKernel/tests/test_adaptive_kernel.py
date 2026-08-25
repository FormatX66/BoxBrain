import unittest

from Projects.AdaptiveKernel.adaptive_kernel import (
    CanaryEvidence,
    CapabilityRule,
    future_branch_proposals,
    kernel_canary_branch_field,
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

    def test_canary_field_preserves_proven_rollback_and_gather_branches(self):
        proposals = future_branch_proposals(
            {"input.pointer": True},
            [CapabilityRule("pointer", ("input.pointer",), ("pointer",))],
        )
        field = kernel_canary_branch_field(proposals, {})
        by_id = {item["branch_id"]: item for item in field["branches"]}
        self.assertTrue(by_id["kernel-proven-lkg"]["is_last_known_good"])
        self.assertEqual(by_id["kernel-proven-lkg"]["status"], "verified")
        self.assertEqual(by_id["kernel-rollback"]["rollback_target"], "current-proven-kernel")
        self.assertEqual(by_id["kernel-gather-evidence"]["status"], "warm")
        self.assertFalse(field["promotion_performed"])
        self.assertFalse(field["invariants"]["proven_state_destroy_allowed"])

    def test_strong_regression_vetoes_candidate_despite_other_positive_dimensions(self):
        proposals = future_branch_proposals(
            {"input.pointer": True},
            [CapabilityRule("pointer", ("input.pointer",), ("pointer",))],
        )
        field = kernel_canary_branch_field(
            proposals,
            {
                "kernel-pointer": CanaryEvidence(
                    boot=True,
                    resume=True,
                    hardware=True,
                    performance=True,
                    regression=False,
                )
            },
            guardian_approved_branches=("kernel-pointer",),
        )
        candidate = next(item for item in field["branches"] if item["branch_id"] == "kernel-pointer")
        self.assertEqual(candidate["status"], "rejected")
        self.assertEqual(candidate["hold_reason"], "strong-regression-evidence")
        self.assertFalse(candidate["promotion_eligible"])
        self.assertFalse(field["promotion_performed"])

    def test_complete_positive_canary_requires_guardian_before_promotion_eligibility(self):
        proposals = future_branch_proposals(
            {"input.pointer": True},
            [CapabilityRule("pointer", ("input.pointer",), ("pointer",))],
        )
        proof = CanaryEvidence(True, True, True, True, True)
        held = kernel_canary_branch_field(proposals, {"kernel-pointer": proof})
        held_candidate = next(item for item in held["branches"] if item["branch_id"] == "kernel-pointer")
        self.assertEqual(held_candidate["status"], "verified")
        self.assertEqual(held_candidate["hold_reason"], "guardian-approval-required")
        self.assertFalse(held_candidate["promotion_eligible"])

        approved = kernel_canary_branch_field(
            proposals,
            {"kernel-pointer": proof},
            guardian_approved_branches=("kernel-pointer",),
        )
        approved_candidate = next(item for item in approved["branches"] if item["branch_id"] == "kernel-pointer")
        self.assertTrue(approved_candidate["promotion_eligible"])
        self.assertFalse(approved["promotion_performed"])


if __name__ == "__main__":
    unittest.main()
