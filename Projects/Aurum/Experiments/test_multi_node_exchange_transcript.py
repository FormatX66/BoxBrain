from __future__ import annotations

import unittest

from multi_node_exchange_preflight import build_exchange_envelope, evaluate_exchange_preflight
from multi_node_exchange_transcript import (
    append_exchange_receipt,
    build_exchange_receipt,
    gen3_live_exchange_transcript_gate,
    verify_exchange_transcript,
)
from scoped_trait_inheritance import TraitCandidate, TraitEvidence, TraitScope


LINEAGE = "a" * 64
PAYLOAD = "b" * 64
SOURCE_LKG = "c" * 64
RECEIVER_LKG = "d" * 64
EVIDENCE = "1" * 64
SCOPE = TraitScope(
    hardware=("lan9514",),
    workload=("network",),
    environment=("linux",),
    phenotype=("pi3",),
)


def candidate() -> TraitCandidate:
    return TraitCandidate(
        trait_id="ethernet-adaptation",
        version="1",
        source_node="pi3-a",
        lineage_digest=LINEAGE,
        payload_digest=PAYLOAD,
        scope=SCOPE,
        evidence=(TraitEvidence("ev-a", EVIDENCE, 0.94, False),),
    )


def envelope(sequence: int, *, receiver: str = "pi3-b", exchange_id: str = "session-1") -> dict:
    return build_exchange_envelope(
        candidate(),
        claimed_sender_node="pi3-a",
        receiver_node=receiver,
        exchange_id=exchange_id,
        sequence=sequence,
        source_lkg_digest=SOURCE_LKG,
    )


def decision(
    item: dict,
    *,
    expected_receiver: str = "pi3-b",
    trusted: frozenset[str] = frozenset({"pi3-a"}),
) -> dict:
    return evaluate_exchange_preflight(
        item,
        expected_receiver_node=expected_receiver,
        trusted_claimed_senders=trusted,
        target_scope=SCOPE,
        receiver_lkg_digest=RECEIVER_LKG,
        expected_parent_lineage=LINEAGE,
    )


class MultiNodeExchangeTranscriptTests(unittest.TestCase):
    def test_chain_preserves_accepted_and_quarantined_evidence(self):
        first = envelope(7)
        receipts = append_exchange_receipt([], first, decision(first))

        second = envelope(8)
        quarantined = decision(second, trusted=frozenset())
        self.assertFalse(quarantined["software_exchange_preflight"])
        receipts = append_exchange_receipt(receipts, second, quarantined)

        summary = verify_exchange_transcript(receipts)
        self.assertEqual(summary["state"], "software-transcript-verified")
        self.assertEqual(summary["receipt_count"], 2)
        self.assertEqual(summary["accepted_receipts"], 1)
        self.assertEqual(summary["quarantined_receipts"], 1)
        self.assertEqual(summary["first_sequence"], 7)
        self.assertEqual(summary["last_sequence"], 8)
        self.assertTrue(summary["lkg_preserved"])
        self.assertFalse(summary["sender_identity_authenticated"])
        self.assertFalse(summary["network_delivery_proven"])
        self.assertFalse(summary["live_multi_node_exchange_proven"])

    def test_duplicate_or_stale_sequence_is_refused(self):
        first = envelope(1)
        receipts = append_exchange_receipt([], first, decision(first))
        duplicate = envelope(1)
        with self.assertRaisesRegex(ValueError, "duplicate, stale, or out of sequence"):
            append_exchange_receipt(receipts, duplicate, decision(duplicate))

    def test_sequence_gap_is_refused(self):
        first = envelope(3)
        receipts = append_exchange_receipt([], first, decision(first))
        gap = envelope(5)
        with self.assertRaisesRegex(ValueError, "duplicate, stale, or out of sequence"):
            append_exchange_receipt(receipts, gap, decision(gap))

    def test_different_session_or_node_pair_is_refused(self):
        first = envelope(1)
        receipts = append_exchange_receipt([], first, decision(first))

        different_session = envelope(2, exchange_id="session-2")
        with self.assertRaisesRegex(ValueError, "different session or node pair"):
            append_exchange_receipt(receipts, different_session, decision(different_session))

        different_receiver = envelope(2, receiver="pi3-c")
        with self.assertRaisesRegex(ValueError, "different session or node pair"):
            append_exchange_receipt(
                receipts,
                different_receiver,
                decision(different_receiver, expected_receiver="pi3-c"),
            )

    def test_receipt_tampering_breaks_chain_integrity(self):
        first = envelope(1)
        receipt = build_exchange_receipt(first, decision(first))
        receipt["quarantine_reasons"] = ["tampered"]
        with self.assertRaisesRegex(ValueError, "receipt digest mismatch"):
            verify_exchange_transcript([receipt])

    def test_software_receipt_refuses_lkg_mutation(self):
        item = envelope(1)
        result = decision(item)
        result["receiver_lkg_digest_after"] = "e" * 64
        with self.assertRaisesRegex(ValueError, "cannot record LKG mutation"):
            build_exchange_receipt(item, result)

    def test_software_receipt_refuses_proof_or_authority_widening(self):
        item = envelope(1)
        result = decision(item)
        result["sender_identity_authenticated"] = True
        with self.assertRaisesRegex(ValueError, "widen proof or authority"):
            build_exchange_receipt(item, result)

    def test_live_gate_remains_held_after_verified_transcript(self):
        item = envelope(1)
        receipts = append_exchange_receipt([], item, decision(item))
        summary = verify_exchange_transcript(receipts)
        gate = gen3_live_exchange_transcript_gate(summary)

        self.assertTrue(gate["exchange_transcript_software_preflight"])
        self.assertFalse(gate["live_multi_node_exchange"])
        self.assertFalse(gate["authenticated_peer_identity"])
        self.assertFalse(gate["network_delivery_proof"])
        self.assertFalse(gate["peer_liveness_proof"])
        self.assertFalse(gate["independent_node_recovery"])
        self.assertFalse(gate["lkg_mutated"])
        self.assertFalse(gate["trust_widened"])
        self.assertFalse(gate["grants_mutation_authority"])
        self.assertFalse(gate["grants_promotion_authority"])
        self.assertFalse(gate["infers_physical_proof"])


if __name__ == "__main__":
    unittest.main()
