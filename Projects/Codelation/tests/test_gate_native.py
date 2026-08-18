from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Projects.Codelation.gate_native import Gate, GateField, atom
from Projects.Codelation import run_gate_frontier as frontier


class GateNativeTests(unittest.TestCase):
    def test_event_driven_gate_propagation(self) -> None:
        a = atom(b"\x10")
        b = atom(b"\x11")
        c = atom(b"\x12")
        d = atom(b"\x13")
        field = GateField(
            active=(a,),
            gates=(
                Gate((a, b), c),
                Gate((c,), d),
            ),
        )
        self.assertFalse(field.is_active(c))
        changed = field.activate(b)
        self.assertIn(c, changed)
        self.assertIn(d, changed)
        self.assertTrue(field.is_active(d))

    def test_binary_roundtrip_is_canonical(self) -> None:
        a = atom(b"\x01")
        b = atom(b"\x02")
        c = atom(b"\x03")
        one = GateField(active=(b, a), gates=(Gate((b, a), c),))
        two = GateField(active=(a, b), gates=(Gate((a, b), c),))
        self.assertEqual(one.to_bytes(), two.to_bytes())
        self.assertEqual(GateField.from_bytes(one.to_bytes()).to_bytes(), one.to_bytes())
        self.assertEqual(one.identity(), two.identity())

    def test_authoritative_machine_blob_contains_no_human_labels(self) -> None:
        bootstrap_state = {
            "next_gap": "learning_delta_score",
            "_checkpoint": {
                "schema": "aurum-native-chain-resume-v1",
                "learned_expressions": {},
                "verified_local_capabilities": [],
            },
        }
        with patch.object(frontier, "native_semantic_gap_names", return_value=("learning_delta_score",)):
            machine, projection = frontier.bootstrap(bootstrap_state)
        payload = machine.to_bytes()
        for forbidden in (
            b"learning_delta_score",
            b"generation",
            b"python",
            b"json",
            b"frontier",
            b"capability",
        ):
            self.assertNotIn(forbidden, payload.lower())
        self.assertEqual(projection["role"], "codelation-only-not-authoritative")
        self.assertEqual(projection["machine_state_sha256"], machine.identity())

    def test_pending_work_is_opaque_state_not_label(self) -> None:
        with patch.object(frontier, "native_semantic_gap_names", return_value=("some_human_name",)):
            machine, projection = frontier.bootstrap({"next_gap": "some_human_name"})
        state = frontier.capability_id("some_human_name")
        self.assertIn(state, machine.pending)
        self.assertEqual(len(state), 32)
        self.assertNotEqual(state, b"some_human_name")
        self.assertEqual(projection["labels"][state.hex()], "some_human_name")

    def test_evidence_and_authority_are_ordinary_gate_inputs(self) -> None:
        capability = atom(b"\x21")
        evidence = atom(b"\x22")
        authority = atom(b"\x23")
        result = atom(b"\x24")
        field = GateField(gates=(Gate((capability, evidence, authority), result),))
        field.activate(capability, evidence)
        self.assertFalse(field.is_active(result))
        field.activate(authority)
        self.assertTrue(field.is_active(result))

    def test_machine_frontier_binary_roundtrip(self) -> None:
        pending = atom(b"\x31")
        parked = atom(b"\x32")
        resolved = atom(b"\x33")
        field = GateField(active=(pending, parked, resolved))
        machine = frontier.MachineFrontier(
            pending=(pending,),
            parked=(parked,),
            resolved=(resolved,),
            field=field,
        )
        clone = frontier.MachineFrontier.from_bytes(machine.to_bytes())
        self.assertEqual(clone.to_bytes(), machine.to_bytes())
        self.assertEqual(clone.pending, (pending,))
        self.assertEqual(clone.parked, (parked,))
        self.assertEqual(clone.resolved, (resolved,))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.bin"
            path.write_bytes(machine.to_bytes())
            restored = frontier.MachineFrontier.from_bytes(path.read_bytes())
            self.assertEqual(restored.identity(), machine.identity())

    def test_blocked_state_does_not_globally_stall_independent_state(self) -> None:
        blocked_state = frontier.capability_id("blocked")
        open_state = frontier.capability_id("open")
        field = GateField(active=(blocked_state, open_state))
        machine = frontier.MachineFrontier(
            pending=(blocked_state, open_state),
            parked=(),
            resolved=(),
            field=field,
        )
        checkpoint = {
            "schema": "aurum-native-chain-resume-v1",
            "learned_expressions": {},
            "verified_local_capabilities": [],
        }
        projection = {
            "schema": "aurum-gate-projection-v2",
            "role": "codelation-only-not-authoritative",
            "machine_state_sha256": machine.identity(),
            "labels": {
                blocked_state.hex(): "blocked",
                open_state.hex(): "open",
            },
            "blocked": {},
            "external_evidence": {},
            "reasoning_requests": {},
            "executor_checkpoint": checkpoint,
        }

        def fake_run_chain(*, start_gap: str, seed_state, **_: object) -> dict:
            if start_gap == "blocked":
                return {
                    "generations": [],
                    "blocked_reason": "external-prerequisite-blocked",
                    "reasoning_required": False,
                    "reasoning_request": None,
                    "external_evidence": {"applied": False},
                    "_checkpoint": seed_state["_checkpoint"],
                    "next_gap": "blocked",
                }
            return {
                "generations": [{"gap": "open", "external_evidence": None}],
                "blocked_reason": "generation-bound-reached",
                "reasoning_required": False,
                "reasoning_request": None,
                "external_evidence": None,
                "_checkpoint": seed_state["_checkpoint"],
                "next_gap": "",
            }

        with (
            patch.object(frontier, "native_semantic_gap_names", return_value=("blocked", "open")),
            patch.object(frontier.legacy_executor, "run_chain", side_effect=fake_run_chain),
        ):
            advanced, sidecar = frontier.advance(machine, projection, work_budget=8)

        self.assertIn(blocked_state, advanced.parked)
        self.assertIn(open_state, advanced.resolved)
        self.assertNotIn(open_state, advanced.parked)
        self.assertEqual(sidecar["yield_reason"], "waiting-on-external-state")
        self.assertEqual(sidecar["work_done_this_burst"], 1)
        self.assertEqual(sidecar["blocked"][blocked_state.hex()], "external-prerequisite-blocked")

    def test_parked_work_retries_only_when_no_runnable_work_remains(self) -> None:
        parked_state = frontier.capability_id("parked")
        pending_state = frontier.capability_id("pending")
        field = GateField(active=(parked_state, pending_state))
        machine = frontier.MachineFrontier(
            pending=(pending_state,),
            parked=(parked_state,),
            resolved=(),
            field=field,
        )
        projection = {
            "schema": "aurum-gate-projection-v2",
            "role": "codelation-only-not-authoritative",
            "machine_state_sha256": machine.identity(),
            "labels": {
                parked_state.hex(): "parked",
                pending_state.hex(): "pending",
            },
            "blocked": {parked_state.hex(): "external-prerequisite-blocked"},
            "external_evidence": {},
            "reasoning_requests": {},
            "executor_checkpoint": {
                "schema": "aurum-native-chain-resume-v1",
                "learned_expressions": {},
                "verified_local_capabilities": [],
            },
        }
        calls: list[str] = []

        def fake_run_chain(*, start_gap: str, seed_state, **_: object) -> dict:
            calls.append(start_gap)
            return {
                "generations": [{"gap": start_gap, "external_evidence": None}],
                "blocked_reason": "generation-bound-reached",
                "reasoning_required": False,
                "reasoning_request": None,
                "external_evidence": None,
                "_checkpoint": seed_state["_checkpoint"],
                "next_gap": "",
            }

        with (
            patch.object(frontier, "native_semantic_gap_names", return_value=("parked", "pending")),
            patch.object(frontier.legacy_executor, "run_chain", side_effect=fake_run_chain),
        ):
            advanced, _ = frontier.advance(machine, projection, work_budget=1)

        self.assertEqual(calls, ["pending"])
        self.assertIn(parked_state, advanced.parked)
        self.assertIn(pending_state, advanced.resolved)


if __name__ == "__main__":
    unittest.main()
