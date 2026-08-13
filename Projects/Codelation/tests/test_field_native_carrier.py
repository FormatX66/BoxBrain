from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

FIELD = Path(__file__).resolve().parents[1] / "field"
sys.path.insert(0, str(FIELD))

from field_native_carrier import (
    NativeCarrierError,
    make_native_program_carrier,
    restore_native_program,
    verify_native_program_carrier,
)
from field_native_vm import compile_native, execute_native


class FieldNativeCarrierTests(unittest.TestCase):
    def make_program(self):
        return compile_native(
            ("before", "after"),
            {
                "op": "length",
                "value": {
                    "op": "symmetric_difference",
                    "left": {"op": "split", "value": {"op": "input", "name": "before"}},
                    "right": {"op": "split", "value": {"op": "input", "name": "after"}},
                },
            },
        )

    def test_round_trip_preserves_native_identity_and_execution(self):
        program = self.make_program()
        wrapped = make_native_program_carrier(program)
        restored = restore_native_program(wrapped.carrier)
        self.assertEqual(restored.identity, program.identity)
        self.assertEqual(restored.tape_identity, program.tape_identity)
        self.assertEqual(restored.parameters, program.parameters)
        self.assertEqual(
            execute_native(restored, {"before": "field slush", "after": "field aurum slush"}),
            1,
        )

    def test_carrier_bytes_and_digest_are_deterministic(self):
        program = self.make_program()
        first = make_native_program_carrier(program)
        second = make_native_program_carrier(program)
        self.assertEqual(first.carrier, second.carrier)
        self.assertEqual(first.carrier_sha256, second.carrier_sha256)
        self.assertEqual(first.carrier_sha256, hashlib.sha256(first.carrier).hexdigest())

    def test_expected_identities_gate_resolution(self):
        program = self.make_program()
        wrapped = make_native_program_carrier(program)
        restored = verify_native_program_carrier(
            wrapped.carrier,
            expected_sha256=wrapped.carrier_sha256,
            expected_program_identity=program.identity,
            expected_tape_identity=program.tape_identity,
        )
        self.assertEqual(restored, program)
        with self.assertRaises(NativeCarrierError):
            verify_native_program_carrier(wrapped.carrier, expected_sha256="0" * 64)
        with self.assertRaises(NativeCarrierError):
            verify_native_program_carrier(wrapped.carrier, expected_program_identity="wrong")

    def test_tampered_carrier_is_rejected(self):
        program = self.make_program()
        wrapped = make_native_program_carrier(program)
        damaged = bytearray(wrapped.carrier)
        damaged[-1] ^= 1
        with self.assertRaises((NativeCarrierError, ValueError)):
            restore_native_program(bytes(damaged))


if __name__ == "__main__":
    unittest.main(verbosity=2)
