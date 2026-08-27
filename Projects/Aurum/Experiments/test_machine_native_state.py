from __future__ import annotations

import json
import unittest

from machine_native_state import (
    EvidenceRef,
    NativeEntity,
    NativeRelation,
    NativeState,
    gen2_state_gate,
    stateweave_basis_is_current,
)


D1 = "1" * 64
D2 = "2" * 64


def sample_state(reverse: bool = False) -> NativeState:
    entities = [
        NativeEntity(
            "hopper",
            "node",
            {"arch": "x86_64"},
            persistence="protected",
            usefulness=1.0,
            evidence=(EvidenceRef("physical-inventory", D1, 1.0),),
        ),
        NativeEntity(
            "wifi",
            "capability",
            {"role": "network"},
            persistence="slush",
            reachability=0.8,
            usefulness=0.9,
            evidence=(EvidenceRef("seed-contract", D2, 0.9),),
        ),
    ]
    relation = NativeRelation(
        "hopper",
        "has-capability",
        "wifi",
        0.9,
        (EvidenceRef("seed-contract", D2, 0.9),),
    )
    if reverse:
        entities.reverse()
    return NativeState(entities=entities, relations=[relation])


class MachineNativeStateTests(unittest.TestCase):
    def test_digest_is_independent_of_insertion_order(self):
        self.assertEqual(sample_state().digest(), sample_state(reverse=True).digest())
        self.assertEqual(sample_state().serialize(), sample_state(reverse=True).serialize())

    def test_replay_is_deterministic_and_digest_bound(self):
        original = sample_state()
        replayed = NativeState.replay(original.serialize(), expected_digest=original.digest())
        self.assertEqual(replayed.serialize(), original.serialize())
        self.assertEqual(replayed.digest(), original.digest())

    def test_replay_rejects_modified_or_noncanonical_snapshot(self):
        original = sample_state()
        payload = json.loads(original.serialize())
        payload["entities"] = list(reversed(payload["entities"]))
        with self.assertRaisesRegex(ValueError, "not canonical"):
            NativeState.replay(json.dumps(payload))

        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            NativeState.replay(original.serialize(), expected_digest="f" * 64)

    def test_conflicting_entity_definition_fails_closed(self):
        state = NativeState([NativeEntity("a", "node")])
        with self.assertRaisesRegex(ValueError, "contradictory entity"):
            state.add_entity(NativeEntity("a", "different-kind"))

    def test_relation_to_unknown_entity_fails_closed(self):
        state = NativeState([NativeEntity("a", "node")])
        state.add_relation(NativeRelation("a", "knows", "missing"))
        with self.assertRaisesRegex(ValueError, "unknown relation object"):
            state.canonical()

    def test_malformed_provenance_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "64-character"):
            NativeState([NativeEntity("a", "node", evidence=(EvidenceRef("x", "bad"),))])
        with self.assertRaisesRegex(ValueError, "within"):
            NativeState([NativeEntity("a", "node", evidence=(EvidenceRef("x", D1, 1.1),))])

    def test_human_projection_is_bound_but_never_canonical(self):
        state = sample_state()
        projection = state.compatibility_projection()
        self.assertFalse(projection["canonical"])
        self.assertFalse(projection["grants_authority"])
        self.assertEqual(projection["source_native_digest"], state.digest())
        self.assertEqual(
            projection["entries"],
            sample_state(reverse=True).compatibility_projection()["entries"],
        )
        self.assertEqual(
            [item["entity"] for item in projection["entries"]],
            ["hopper", "wifi"],
        )

    def test_stateweave_basis_expires_when_native_state_changes(self):
        before = sample_state()
        basis = before.digest()
        self.assertTrue(stateweave_basis_is_current(before, basis))
        after = NativeState(
            entities=[
                NativeEntity("hopper", "node", {"arch": "x86_64"}),
                NativeEntity("wifi", "capability", {"role": "network"}),
                NativeEntity("browser", "capability", {"role": "web"}),
            ],
            relations=[NativeRelation("hopper", "has-capability", "wifi")],
        )
        self.assertFalse(stateweave_basis_is_current(after, basis))

    def test_gen2_gate_never_converts_software_replay_into_physical_or_mutation_authority(self):
        state = sample_state()
        digest = state.digest()
        result = gen2_state_gate(
            state,
            replayed_digest=digest,
            compatibility_source_digest=digest,
        )
        self.assertTrue(result["machine_native_state_projection"])
        self.assertTrue(result["slush_relationship_model"])
        self.assertTrue(result["replay_verified"])
        self.assertFalse(result["compatibility_projection_is_canonical"])
        self.assertFalse(result["grants_mutation_authority"])
        self.assertFalse(result["may_promote_candidate"])
        self.assertFalse(result["infers_physical_recovery"])

    def test_gen2_gate_refuses_unbound_compatibility_projection(self):
        state = sample_state()
        result = gen2_state_gate(
            state,
            replayed_digest=state.digest(),
            compatibility_source_digest="0" * 64,
        )
        self.assertFalse(result["machine_native_state_projection"])
        self.assertFalse(result["slush_relationship_model"])


if __name__ == "__main__":
    unittest.main()
