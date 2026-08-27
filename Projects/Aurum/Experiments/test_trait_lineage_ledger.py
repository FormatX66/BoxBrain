from __future__ import annotations

import json
import unittest

from trait_lineage_ledger import LineageInput, TraitLineageLedger


TRAIT = "a" * 64
TRAIT2 = "b" * 64
LKG = "c" * 64
E1 = "1" * 64
E2 = "2" * 64


class TraitLineageLedgerTests(unittest.TestCase):
    def test_append_and_replay_are_digest_bound(self):
        ledger = TraitLineageLedger()
        first = ledger.append(
            LineageInput(3, TRAIT, "pi3", "candidate-evidence", (E1,), LKG)
        )
        second = ledger.append(
            LineageInput(
                3,
                TRAIT,
                "quarantined",
                (E2,),
                LKG,
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
        ledger.append(LineageInput(3, TRAIT, "candidate-evidence", (E1,), LKG))
        payload = json.loads(ledger.serialize())
        payload["records"][0]["decision"] = "rejected"
        with self.assertRaisesRegex(ValueError, "record digest mismatch"):
            TraitLineageLedger.replay(json.dumps(payload))

    def test_wrong_parent_cannot_fork_current_ledger_silently(self):
        ledger = TraitLineageLedger()
        first = ledger.append(LineageInput(3, TRAIT, "candidate-evidence", (E1,), LKG))
        with self.assertRaisesRegex(ValueError, "current ledger tip"):
            ledger.append(
                LineageInput(
                    3,
                    TRAIT2,
                    "candidate-evidence",
                    (E2,),
                    LKG,
                    parent_record_digest="f" * 64,
                )
            )
        ledger.append(
            LineageInput(
                3,
                TRAIT2,
                "candidate-evidence",
                (E2,),
                LKG,
                parent_record_digest=first["record_digest"],
            )
        )
        self.assertEqual(len(ledger.records), 2)

    def test_genesis_must_not_claim_a_parent(self):
        ledger = TraitLineageLedger()
        with self.assertRaisesRegex(ValueError, "current ledger tip"):
            ledger.append(
                LineageInput(
                    3,
                    TRAIT,
                    "candidate-evidence",
                    (E1,),
                    LKG,
                    parent_record_digest="f" * 64,
                )
            )

    def test_quarantine_and_rejection_remain_durable_evidence(self):
        ledger = TraitLineageLedger()
        first = ledger.append(LineageInput(3, TRAIT, "quarantined", (E1,), LKG, reason="safety-veto"))
        ledger.append(
            LineageInput(
                3,
                TRAIT2,
                "rejected",
                (E2,),
                LKG,
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
        ledger.append(LineageInput(3, TRAIT, "candidate-evidence", (E1, E2), LKG))
        payload = json.loads(ledger.serialize())
        payload["records"][0]["evidence_digests"] = list(reversed(payload["records"][0]["evidence_digests"]))
        # Existing record digest intentionally remains unchanged; replay must refuse.
        with self.assertRaisesRegex(ValueError, "record digest mismatch"):
            TraitLineageLedger.replay(json.dumps(payload))

    def test_invalid_decision_and_missing_evidence_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "unsupported lineage decision"):
            TraitLineageLedger().append(LineageInput(3, TRAIT, "promoted", (E1,), LKG))
        with self.assertRaisesRegex(ValueError, "at least one evidence"):
            TraitLineageLedger().append(LineageInput(3, TRAIT, "candidate-evidence", (), LKG))

    def test_ledger_digest_detects_whole_snapshot_mismatch(self):
        ledger = TraitLineageLedger()
        ledger.append(LineageInput(3, TRAIT, "candidate-evidence", (E1,), LKG))
        with self.assertRaisesRegex(ValueError, "ledger digest mismatch"):
            TraitLineageLedger.replay(ledger.serialize(), expected_ledger_digest="f" * 64)


if __name__ == "__main__":
    unittest.main()
