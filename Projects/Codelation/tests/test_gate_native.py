from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Projects.Codelation.gate_native import Gate, GateField, atom
from Projects.Codelation.run_gate_frontier import MachineFrontier, bootstrap, capability_id


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
        machine, projection = bootstrap(bootstrap_state)
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

    def test_machine_focus_is_opaque_state_not_label(self) -> None:
        machine, projection = bootstrap({"next_gap": "some_human_name"})
        self.assertEqual(machine.focus, capability_id("some_human_name"))
        self.assertEqual(len(machine.focus), 32)
        self.assertNotEqual(machine.focus, b"some_human_name")
        self.assertEqual(projection["labels"][machine.focus.hex()], "some_human_name")

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
        focus = atom(b"\x31")
        field = GateField(active=(focus,))
        machine = MachineFrontier(focus=focus, field=field)
        clone = MachineFrontier.from_bytes(machine.to_bytes())
        self.assertEqual(clone.to_bytes(), machine.to_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.bin"
            path.write_bytes(machine.to_bytes())
            restored = MachineFrontier.from_bytes(path.read_bytes())
            self.assertEqual(restored.identity(), machine.identity())


if __name__ == "__main__":
    unittest.main()
