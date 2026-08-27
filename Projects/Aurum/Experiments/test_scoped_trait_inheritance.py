from __future__ import annotations

import unittest

from scoped_trait_inheritance import (
    ReceivingContext,
    TraitCandidate,
    TraitEvidence,
    TraitScope,
    evaluate_trait,
    gen3_inheritance_gate,
    merge_cross_node_evidence,
    provenance_replay,
)


LINEAGE = "a" * 64
PAYLOAD = "b" * 64
LKG = "c" * 64
E1 = "1" * 64
E2 = "2" * 64
PARENT1 = "3" * 64
PARENT2 = "4" * 64


def trait(*, source="pi3", scope=None, veto=False, confidence=0.9,
          evidence_id="e1", evidence_digest=E1, parent=None):
    return TraitCandidate(
        trait_id="ethernet-adaptation",
        version="1",
        source_node=source,
        lineage_digest=LINEAGE,
        payload_digest=PAYLOAD,
        scope=scope or TraitScope(hardware=("lan9514",), workload=("network",), phenotype=("pi3",)),
        evidence=(TraitEvidence(evidence_id, evidence_digest, confidence, veto),),
        parent_trait_digest=parent,
    )


def context(*, trusted=frozenset({"pi3"}), scope=None, lineage=LINEAGE):
    return ReceivingContext(
        node_id="receiver",
        trusted_nodes=trusted,
        target_scope=scope or TraitScope(hardware=("lan9514",), workload=("network",), phenotype=("pi3",)),
        current_lkg_digest=LKG,
        expected_parent_lineage=lineage,
    )


class ScopedTraitInheritanceTests(unittest.TestCase):
    def test_exact_scope_trusted_candidate_is_evidence_only(self):
        result = evaluate_trait(trait(), context())
        self.assertEqual(result["state"], "candidate-evidence-accepted")
        self.assertTrue(result["accepted_as_evidence"])
        self.assertEqual(result["lkg_digest_before"], LKG)
        self.assertEqual(result["lkg_digest_after"], LKG)
        self.assertFalse(result["grants_mutation_authority"])
        self.assertFalse(result["grants_promotion_authority"])
        self.assertFalse(result["may_bind_driver"])
        self.assertFalse(result["may_replace_kernel"])

    def test_out_of_scope_trait_is_quarantined(self):
        result = evaluate_trait(
            trait(scope=TraitScope(hardware=("lan9514",), phenotype=("pi3",))),
            context(scope=TraitScope(hardware=("different-controller",), phenotype=("pi4",))),
        )
        self.assertEqual(result["state"], "quarantined")
        self.assertIn("out-of-scope", result["quarantine_reasons"])
        self.assertEqual(result["lkg_digest_after"], LKG)

    def test_unscoped_dimension_is_not_a_wildcard(self):
        result = evaluate_trait(
            trait(scope=TraitScope(hardware=("lan9514",))),
            context(scope=TraitScope(hardware=("lan9514",), workload=("network",), phenotype=("pi3",))),
        )
        self.assertEqual(result["state"], "quarantined")
        self.assertIn("out-of-scope", result["quarantine_reasons"])
        self.assertFalse(result["scope_widened"])

    def test_unknown_peer_does_not_widen_trust(self):
        result = evaluate_trait(trait(source="unknown-peer"), context())
        self.assertIn("untrusted-source-node", result["quarantine_reasons"])
        self.assertFalse(result["trust_widened"])

    def test_lineage_mismatch_quarantines(self):
        result = evaluate_trait(trait(), context(lineage="d" * 64))
        self.assertIn("lineage-mismatch", result["quarantine_reasons"])

    def test_safety_veto_beats_high_confidence(self):
        result = evaluate_trait(trait(veto=True, confidence=1.0), context())
        self.assertIn("safety-veto", result["quarantine_reasons"])
        self.assertFalse(result["accepted_as_evidence"])

    def test_many_peers_cannot_vote_scope_or_trust_wider(self):
        peer1 = trait(source="pi3", evidence_id="e1", evidence_digest=E1)
        peer2 = trait(source="pi4", evidence_id="e2", evidence_digest=E2)
        merged = merge_cross_node_evidence([peer1, peer2])
        self.assertTrue(merged["merged"])
        self.assertEqual(merged["source_nodes"], ["pi3", "pi4"])
        self.assertFalse(merged["scope_widened"])
        self.assertFalse(merged["trust_widened"])
        self.assertFalse(merged["grants_authority"])

    def test_cross_node_merge_rejects_scope_conflict(self):
        a = trait(source="pi3")
        b = trait(
            source="pi4",
            scope=TraitScope(hardware=("other",), workload=("network",), phenotype=("pi4",)),
            evidence_id="e2",
            evidence_digest=E2,
        )
        merged = merge_cross_node_evidence([a, b])
        self.assertEqual(merged["state"], "quarantined-conflict")
        self.assertFalse(merged["merged"])
        self.assertFalse(merged["grants_authority"])

    def test_cross_node_merge_rejects_parent_trait_conflict(self):
        a = trait(source="pi3", parent=PARENT1)
        b = trait(source="pi4", parent=PARENT2, evidence_id="e2", evidence_digest=E2)
        merged = merge_cross_node_evidence([a, b])
        self.assertEqual(merged["state"], "quarantined-conflict")
        self.assertFalse(merged["merged"])
        self.assertFalse(merged["grants_authority"])

    def test_cross_node_veto_is_preserved_not_outvoted(self):
        a = trait(source="pi3", confidence=1.0, evidence_id="e1", evidence_digest=E1)
        b = trait(source="pi4", veto=True, confidence=0.1, evidence_id="e2", evidence_digest=E2)
        merged = merge_cross_node_evidence([a, b])
        self.assertTrue(merged["merged"])
        self.assertTrue(merged["safety_veto"])
        self.assertEqual(merged["state"], "merged-evidence-vetoed")

    def test_provenance_replay_is_digest_bound(self):
        candidate = trait()
        replay = provenance_replay(candidate, expected_trait_digest=candidate.digest())
        self.assertTrue(replay["replay_verified"])
        self.assertEqual(replay["source_node"], "pi3")
        self.assertEqual(replay["lineage_digest"], LINEAGE)
        self.assertFalse(replay["grants_authority"])
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            provenance_replay(candidate, expected_trait_digest="f" * 64)

    def test_generation_gate_uses_literal_true_and_never_infers_physical_proof(self):
        gate = gen3_inheritance_gate(
            lineage_verified=True,
            scoped_inheritance_verified=True,
            cross_node_merge_verified=True,
            phenotype_scope_verified=True,
            provenance_replay_verified=True,
            non_widening_trust_verified=True,
        )
        for key in (
            "lineage_ledger",
            "scoped_trait_inheritance",
            "cross_node_evidence_merge",
            "phenotype_scope_guard",
            "provenance_replay",
            "non_widening_trust_guard",
        ):
            self.assertTrue(gate[key])
        self.assertFalse(gate["grants_mutation_authority"])
        self.assertFalse(gate["infers_multi_node_physical_proof"])

        malformed = gen3_inheritance_gate(
            lineage_verified="true",
            scoped_inheritance_verified=True,
            cross_node_merge_verified=True,
            phenotype_scope_verified=True,
            provenance_replay_verified=True,
            non_widening_trust_verified=True,
        )
        self.assertFalse(malformed["lineage_ledger"])


if __name__ == "__main__":
    unittest.main()
