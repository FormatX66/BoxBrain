from __future__ import annotations

import json
import unittest

from trait_lineage_ledger import LineageInput, TraitLineageLedger


TRAIT = "a" * 64
TRAIT2 = "b" * 64
LKG = "c" * 64
E1 = "1" * 64
E2 = "2" * 64


def lineage_input(
    *,
    trait_digest=TRAIT,
    decision="candidate-evidence",
    evidence_digests=(E1,),
    parent_record_digest=None,
    reason="",
    source_node="pi3",
):
    return LineageInput(
        generation=3,
        trait_digest=trait_digest,
        source_node=source_node,
        decision=decision,
        evidence_digests=evidence_digests,
        lkg_digest=LKG,
        parent_record_digest=parent_record_digest,
        reason=reason,
    )


class TraitLineageLedgerTests(unittest.TestCase):
    def test_append_and_replay_are_digest_bound(self):
        ledger = TraitLineageLedger()
        first = ledger.append(lineage_input())
        second = ledger.append(
            lineage_input(
                decision="quarantined",
                evidence_digests=(E2,),
                parent_record_digest=first["record_digest"],
                reason="scope-mismatch",
            )
        )
        replayed = TraitLineageLedger.replay(
            ledger.serialize(), expected_ledger_digest=ledger.digest()
        )
        self.assertEqual(replayed.digest(), ledger.digest())
        self.assertEqual(replayed.tip_digest, second["record_digest"])
        self.assertEqual(len(replayed.trait_history(TRAIT)), 2)

    def test_tampered_record_is_rejected(self):
        ledger = TraitLineageLedger()
        ledger.append(lineage_input())
        payload = json.loads(ledger.serialize())
        payload["records"][0]["decision"] = "rejected"
        with self.assertRaisesRegex(ValueError, "record digest mismatch"):
            TraitLineageLedger.replay(json.dumps(payload))

    def test_wrong_parent_cannot_fork_current_ledger_silently(self):
        ledger = TraitLineageLedger()
        first = ledger.append(lineage_input())
        with self.assertRaisesRegex(ValueError, "current ledger tip"):
            ledger.append(
                lineage_input(
                    trait_digest=TRAIT2,
                    evidence_digests=(E2,),
                    parent_record_digest="f" * 64,
                )
            )
        ledger.append(
            lineage_input(
                trait_digest=TRAIT2,
                evidence_digests=(E2,),
                parent_record_digest=first["record_digest"],
            )
        )
        self.assertEqual(len(ledger.records), 2)

    def test_genesis_must_not_claim_a_parent(self):
        ledger = TraitLineageLedger()
        with self.assertRaisesRegex(ValueError, "current ledger tip"):
            ledger.append(lineage_input(parent_record_digest="f" * 64))

    def test_quarantine_and_rejection_remain_durable_evidence(self):
        ledger = TraitLineageLedger()
        first = ledger.append(
            lineage_input(decision="quarantined", reason="safety-veto")
        )
        ledger.append(
            lineage_input(
                trait_digest=TRAIT2,
                decision="rejected",
                evidence_digests=(E2,),
                parent_record_digest=first["record_digest"],
                reason="lineage-mismatch",
            )
        )
        gate = ledger.software_gate()
        self.assertTrue(gate["lineage_ledger"])
        self.assertTrue(gate["quarantined_records_retained"])
        self.assertEqual(gate["record_count"], 2)
        self.assertFalse(gate["lkg_mutated"])
        self.assertFalse(gate["trust_widened"])
        self.assertFalse(gate["grants_mutation_authority"])
        self.assertFalse(gate["grants_promotion_authority"])
        self.assertFalse(gate["infers_physical_exchange"])

    def test_noncanonical_record_fails_closed_even_with_recomputed_digest_absent(self):
        ledger = TraitLineageLedger()
        ledger.append(lineage_input(evidence_digests=(E1, E2)))
        payload = json.loads(ledger.serialize())
        payload["records"][0]["evidence_digests"] = list(
            reversed(payload["records"][0]["evidence_digests"])
        )
        # Existing record digest intentionally remains unchanged; replay must refuse.
        with self.assertRaisesRegex(ValueError, "record digest mismatch"):
            TraitLineageLedger.replay(json.dumps(payload))

    def test_invalid_decision_and_missing_evidence_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "unsupported lineage decision"):
            TraitLineageLedger().append(lineage_input(decision="promoted"))
        with self.assertRaisesRegex(ValueError, "at least one evidence"):
            TraitLineageLedger().append(lineage_input(evidence_digests=()))

    def test_ledger_digest_detects_whole_snapshot_mismatch(self):
        ledger = TraitLineageLedger()
        ledger.append(lineage_input())
        with self.assertRaisesRegex(ValueError, "ledger digest mismatch"):
            TraitLineageLedger.replay(
                ledger.serialize(), expected_ledger_digest="f" * 64
            )

    def test_source_node_is_part_of_the_record_and_digest(self):
        pi3 = TraitLineageLedger()
        pi4 = TraitLineageLedger()
        pi3_record = pi3.append(lineage_input(source_node="pi3"))
        pi4_record = pi4.append(lineage_input(source_node="pi4"))
        self.assertEqual(pi3_record["source_node"], "pi3")
        self.assertEqual(pi4_record["source_node"], "pi4")
        self.assertNotEqual(pi3_record["record_digest"], pi4_record["record_digest"])


if __name__ == "__main__":
    unittest.main()
