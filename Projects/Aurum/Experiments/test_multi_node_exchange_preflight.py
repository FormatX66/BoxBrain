from __future__ import annotations

import json
import unittest

from multi_node_exchange_preflight import (
    build_exchange_envelope,
    evaluate_exchange_preflight,
    gen3_live_exchange_preflight_gate,
    replay_exchange_envelope,
    serialize_exchange_envelope,
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


def candidate(*, source: str = "pi3-a", veto: bool = False) -> TraitCandidate:
    return TraitCandidate(
        trait_id="ethernet-adaptation",
        version="1",
        source_node=source,
        lineage_digest=LINEAGE,
        payload_digest=PAYLOAD,
        scope=SCOPE,
        evidence=(TraitEvidence("ev-a", EVIDENCE, 0.93, veto),),
    )


def envelope(*, receiver: str = "pi3-b", source: str = "pi3-a") -> dict:
    return build_exchange_envelope(
        candidate(source=source),
        claimed_sender_node=source,
        receiver_node=receiver,
        exchange_id="session-1:trait-1",
        sequence=1,
        source_lkg_digest=SOURCE_LKG,
    )


class MultiNodeExchangePreflightTests(unittest.TestCase):
    def test_deterministic_round_trip_is_zero_authority(self):
        first = envelope()
        second = envelope()
        self.assertEqual(first, second)
        serialized = serialize_exchange_envelope(first)
        replayed = replay_exchange_envelope(serialized, expected_digest=first["envelope_digest"])
        self.assertEqual(replayed, first)
        self.assertFalse(replayed["sender_identity_authenticated"])
        self.assertFalse(replayed["network_delivery_proven"])
        self.assertFalse(replayed["live_multi_node_exchange_proven"])
        self.assertFalse(replayed["infers_physical_proof"])

    def test_matching_trusted_receiver_can_pass_software_preflight_only(self):
        result = evaluate_exchange_preflight(
            envelope(),
            expected_receiver_node="pi3-b",
            trusted_claimed_senders=frozenset({"pi3-a"}),
            target_scope=SCOPE,
            receiver_lkg_digest=RECEIVER_LKG,
            expected_parent_lineage=LINEAGE,
        )
        self.assertEqual(result["state"], "software-preflight-accepted")
        self.assertTrue(result["software_exchange_preflight"])
        self.assertEqual(result["receiver_lkg_digest_before"], RECEIVER_LKG)
        self.assertEqual(result["receiver_lkg_digest_after"], RECEIVER_LKG)
        self.assertFalse(result["sender_identity_authenticated"])
        self.assertFalse(result["network_delivery_proven"])
        self.assertFalse(result["live_multi_node_exchange_proven"])
        gate = gen3_live_exchange_preflight_gate(result)
        self.assertTrue(gate["multi_node_exchange_software_preflight"])
        self.assertFalse(gate["live_multi_node_exchange"])
        self.assertFalse(gate["authenticated_peer_identity"])
        self.assertFalse(gate["independent_node_recovery"])

    def test_wrong_receiver_is_quarantined(self):
        result = evaluate_exchange_preflight(
            envelope(receiver="pi3-b"),
            expected_receiver_node="pi3-c",
            trusted_claimed_senders=frozenset({"pi3-a"}),
            target_scope=SCOPE,
            receiver_lkg_digest=RECEIVER_LKG,
            expected_parent_lineage=LINEAGE,
        )
        self.assertFalse(result["software_exchange_preflight"])
        self.assertIn("receiver-mismatch", result["quarantine_reasons"])
        self.assertEqual(result["receiver_lkg_digest_after"], RECEIVER_LKG)

    def test_untrusted_claimed_sender_is_quarantined(self):
        result = evaluate_exchange_preflight(
            envelope(source="unknown"),
            expected_receiver_node="pi3-b",
            trusted_claimed_senders=frozenset({"pi3-a"}),
            target_scope=SCOPE,
            receiver_lkg_digest=RECEIVER_LKG,
            expected_parent_lineage=LINEAGE,
        )
        self.assertFalse(result["software_exchange_preflight"])
        self.assertIn("untrusted-claimed-sender", result["quarantine_reasons"])
        self.assertIn("untrusted-source-node", result["quarantine_reasons"])

    def test_trait_safety_veto_remains_quarantined(self):
        item = build_exchange_envelope(
            candidate(veto=True),
            claimed_sender_node="pi3-a",
            receiver_node="pi3-b",
            exchange_id="session-1:trait-veto",
            sequence=2,
            source_lkg_digest=SOURCE_LKG,
        )
        result = evaluate_exchange_preflight(
            item,
            expected_receiver_node="pi3-b",
            trusted_claimed_senders=frozenset({"pi3-a"}),
            target_scope=SCOPE,
            receiver_lkg_digest=RECEIVER_LKG,
            expected_parent_lineage=LINEAGE,
        )
        self.assertFalse(result["software_exchange_preflight"])
        self.assertIn("safety-veto", result["quarantine_reasons"])
        self.assertFalse(result["grants_mutation_authority"])

    def test_scope_or_lineage_mismatch_remains_fail_closed(self):
        scope_result = evaluate_exchange_preflight(
            envelope(),
            expected_receiver_node="pi3-b",
            trusted_claimed_senders=frozenset({"pi3-a"}),
            target_scope=TraitScope(hardware=("other",), phenotype=("pi4",)),
            receiver_lkg_digest=RECEIVER_LKG,
            expected_parent_lineage=LINEAGE,
        )
        self.assertIn("out-of-scope", scope_result["quarantine_reasons"])

        lineage_result = evaluate_exchange_preflight(
            envelope(),
            expected_receiver_node="pi3-b",
            trusted_claimed_senders=frozenset({"pi3-a"}),
            target_scope=SCOPE,
            receiver_lkg_digest=RECEIVER_LKG,
            expected_parent_lineage="e" * 64,
        )
        self.assertIn("lineage-mismatch", lineage_result["quarantine_reasons"])

    def test_tampering_and_false_live_proof_are_rejected(self):
        item = envelope()
        tampered = dict(item)
        tampered["receiver_node"] = "attacker"
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            replay_exchange_envelope(json.dumps(tampered))

        false_proof = dict(item)
        false_proof["live_multi_node_exchange_proven"] = True
        body = dict(false_proof)
        body.pop("envelope_digest")
        import hashlib
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        false_proof["envelope_digest"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        with self.assertRaisesRegex(ValueError, "widen proof or authority"):
            replay_exchange_envelope(json.dumps(false_proof))

    def test_claimed_sender_must_match_candidate_source(self):
        with self.assertRaisesRegex(ValueError, "claimed sender"):
            build_exchange_envelope(
                candidate(source="pi3-a"),
                claimed_sender_node="pi3-b",
                receiver_node="pi3-c",
                exchange_id="bad",
                sequence=0,
                source_lkg_digest=SOURCE_LKG,
            )


if __name__ == "__main__":
    unittest.main()
