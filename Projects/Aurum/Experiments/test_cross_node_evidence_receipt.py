from __future__ import annotations

import json
import unittest

from cross_node_evidence_receipt import (
    build_cross_node_evidence_receipt,
    gen3_cross_node_evidence_gate,
    replay_cross_node_evidence_receipt,
    serialize_cross_node_evidence_receipt,
)
from scoped_trait_inheritance import TraitCandidate, TraitEvidence, TraitScope


LINEAGE = "a" * 64
PAYLOAD = "b" * 64
E1 = "1" * 64
E2 = "2" * 64


def trait(*, source: str, evidence_id: str, evidence_digest: str,
          veto: bool = False, confidence: float = 0.9,
          payload_digest: str = PAYLOAD) -> TraitCandidate:
    return TraitCandidate(
        trait_id="ethernet-adaptation",
        version="1",
        source_node=source,
        lineage_digest=LINEAGE,
        payload_digest=payload_digest,
        scope=TraitScope(
            hardware=("lan9514",),
            workload=("network",),
            environment=("linux",),
            phenotype=("pi3",),
        ),
        evidence=(TraitEvidence(evidence_id, evidence_digest, confidence, veto),),
    )


class CrossNodeEvidenceReceiptTests(unittest.TestCase):
    def test_two_trusted_nodes_produce_replayable_zero_authority_receipt(self):
        receipt = build_cross_node_evidence_receipt(
            [
                trait(source="pi3-a", evidence_id="ev-a", evidence_digest=E1),
                trait(source="pi3-b", evidence_id="ev-b", evidence_digest=E2),
            ],
            trusted_nodes=frozenset({"pi3-a", "pi3-b"}),
        )
        self.assertEqual(receipt["state"], "verified-cross-node-evidence")
        self.assertTrue(receipt["cross_node_evidence_merge"])
        self.assertFalse(receipt["multi_node_live_exchange_proven"])
        self.assertFalse(receipt["independent_node_recovery_proven"])
        self.assertFalse(receipt["lkg_mutated"])
        self.assertFalse(receipt["grants_mutation_authority"])
        self.assertFalse(receipt["grants_promotion_authority"])
        self.assertFalse(receipt["infers_physical_proof"])

        serialized = serialize_cross_node_evidence_receipt(receipt)
        replayed = replay_cross_node_evidence_receipt(
            serialized, expected_digest=receipt["receipt_digest"]
        )
        self.assertEqual(replayed, receipt)

        gate = gen3_cross_node_evidence_gate(receipt)
        self.assertTrue(gate["cross_node_evidence_merge"])
        self.assertTrue(gate["receipt_replay_verified"])
        self.assertFalse(gate["multi_node_live_exchange"])
        self.assertFalse(gate["independent_node_recovery"])
        self.assertFalse(gate["infers_physical_proof"])

    def test_candidate_order_does_not_change_receipt_digest(self):
        a = trait(source="pi3-a", evidence_id="ev-a", evidence_digest=E1)
        b = trait(source="pi3-b", evidence_id="ev-b", evidence_digest=E2)
        trusted = frozenset({"pi3-a", "pi3-b"})
        forward = build_cross_node_evidence_receipt([a, b], trusted_nodes=trusted)
        reverse = build_cross_node_evidence_receipt([b, a], trusted_nodes=trusted)
        self.assertEqual(forward["receipt_digest"], reverse["receipt_digest"])
        self.assertEqual(forward, reverse)

    def test_untrusted_source_is_quarantined(self):
        receipt = build_cross_node_evidence_receipt(
            [
                trait(source="pi3-a", evidence_id="ev-a", evidence_digest=E1),
                trait(source="unknown", evidence_id="ev-b", evidence_digest=E2),
            ],
            trusted_nodes=frozenset({"pi3-a"}),
        )
        self.assertEqual(receipt["state"], "quarantined-untrusted-source")
        self.assertEqual(receipt["untrusted_sources"], ["unknown"])
        self.assertFalse(receipt["cross_node_evidence_merge"])
        gate = gen3_cross_node_evidence_gate(receipt)
        self.assertFalse(gate["cross_node_evidence_merge"])

    def test_conflicting_trait_identity_is_quarantined(self):
        receipt = build_cross_node_evidence_receipt(
            [
                trait(source="pi3-a", evidence_id="ev-a", evidence_digest=E1),
                trait(
                    source="pi3-b",
                    evidence_id="ev-b",
                    evidence_digest=E2,
                    payload_digest="c" * 64,
                ),
            ],
            trusted_nodes=frozenset({"pi3-a", "pi3-b"}),
        )
        self.assertEqual(receipt["state"], "quarantined-conflict")
        self.assertFalse(receipt["cross_node_evidence_merge"])
        self.assertFalse(receipt["lkg_mutated"])
        self.assertFalse(receipt["trust_widened"])

    def test_safety_veto_remains_fail_closed(self):
        receipt = build_cross_node_evidence_receipt(
            [
                trait(source="pi3-a", evidence_id="ev-a", evidence_digest=E1),
                trait(
                    source="pi3-b",
                    evidence_id="ev-b",
                    evidence_digest=E2,
                    veto=True,
                ),
            ],
            trusted_nodes=frozenset({"pi3-a", "pi3-b"}),
        )
        self.assertEqual(receipt["state"], "merged-evidence-vetoed")
        self.assertFalse(receipt["cross_node_evidence_merge"])
        self.assertTrue(receipt["merge_result"]["safety_veto"])
        self.assertFalse(receipt["grants_mutation_authority"])

    def test_single_node_cannot_satisfy_cross_node_gate(self):
        receipt = build_cross_node_evidence_receipt(
            [trait(source="pi3-a", evidence_id="ev-a", evidence_digest=E1)],
            trusted_nodes=frozenset({"pi3-a"}),
        )
        self.assertEqual(receipt["state"], "single-node-evidence")
        self.assertFalse(receipt["cross_node_evidence_merge"])

    def test_tampering_or_authority_widening_is_rejected(self):
        receipt = build_cross_node_evidence_receipt(
            [
                trait(source="pi3-a", evidence_id="ev-a", evidence_digest=E1),
                trait(source="pi3-b", evidence_id="ev-b", evidence_digest=E2),
            ],
            trusted_nodes=frozenset({"pi3-a", "pi3-b"}),
        )
        payload = dict(receipt)
        payload["grants_mutation_authority"] = True
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            replay_cross_node_evidence_receipt(json.dumps(payload))

        payload = dict(receipt)
        payload["multi_node_live_exchange_proven"] = True
        body = dict(payload)
        body.pop("receipt_digest")
        import hashlib
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        payload["receipt_digest"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        with self.assertRaisesRegex(ValueError, "cannot prove live multi-node exchange"):
            replay_cross_node_evidence_receipt(json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
