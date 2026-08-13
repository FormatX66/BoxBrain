from __future__ import annotations

import random
import unittest

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aurum_continuum import (  # noqa: E402
    CanonicalValueError,
    CarrierCorruption,
    Continuum,
    FRAME_SYNC,
    STREAM_MAGIC,
    encode_value,
)


class AurumContinuumTests(unittest.TestCase):
    def test_canonical_values_ignore_map_insertion_order_and_normalize_text(self) -> None:
        left = {"z": 3, "a": [1, True, None], "name": "Cafe\u0301"}
        right = {"name": "Caf\u00e9", "a": [1, True, None], "z": 3}
        self.assertEqual(encode_value(left), encode_value(right))

    def test_non_finite_numbers_and_non_text_keys_are_rejected(self) -> None:
        with self.assertRaises(CanonicalValueError):
            encode_value(float("nan"))
        with self.assertRaises(CanonicalValueError):
            encode_value({1: "not canonical"})
        with self.assertRaises(CanonicalValueError):
            encode_value(1 << 63)

    def test_identical_meaning_converges_without_duplication(self) -> None:
        continuum = Continuum()
        first = continuum.remember("observation", {"temperature": 21}, facets={"unit": "C"})
        second = continuum.remember("observation", {"temperature": 21}, facets={"unit": "C"})
        self.assertEqual(first.identity, second.identity)
        self.assertEqual(len(continuum), 1)

    def test_relation_projection_replaces_folder_or_program_ownership(self) -> None:
        continuum = Continuum()
        evidence = continuum.remember(
            "aurum.evidence",
            {"suite": "deterministic", "passed": 10},
            facets={"status": "verified"},
        )
        capability = continuum.remember(
            "aurum.capability",
            {"name": "continuum-storage", "state": "available"},
            facets={"scope": "aurum-self"},
            links=[evidence.identity],
        )
        checkpoint = continuum.remember(
            "aurum.checkpoint",
            {"cycle": 17},
            links=[capability.identity],
        )

        projected = continuum.select(kind="aurum.capability", facets={"scope": "aurum-self"})
        self.assertEqual([item.identity for item in projected], [capability.identity])
        self.assertEqual(
            {item.identity for item in continuum.closure([checkpoint.identity])},
            {checkpoint.identity, capability.identity, evidence.identity},
        )

    def test_merge_is_commutative_associative_and_idempotent(self) -> None:
        a = Continuum()
        b = Continuum()
        c = Continuum()
        shared_a = a.remember("shared", {"value": 1})
        shared_b = b.remember("shared", {"value": 1})
        self.assertEqual(shared_a.identity, shared_b.identity)
        a.remember("source", "a")
        b.remember("source", "b")
        c.remember("source", "c")

        left = Continuum()
        left.merge(a)
        left.merge(b)
        left.merge(c)
        before = left.root_digest
        self.assertEqual(left.merge(a), 0)
        self.assertEqual(left.root_digest, before)

        right = Continuum()
        bc = Continuum()
        bc.merge(b)
        bc.merge(c)
        right.merge(a)
        right.merge(bc)
        self.assertEqual(left.identities, right.identities)
        self.assertEqual(left.root_digest, right.root_digest)

    def test_export_is_independent_of_insertion_order(self) -> None:
        specifications = [
            ("state", {"n": 1}, {"phase": "alpha"}),
            ("state", {"n": 2}, {"phase": "beta"}),
            ("evidence", b"abc", {"verified": True}),
        ]
        first = Continuum()
        second = Continuum()
        for kind, essence, facets in specifications:
            first.remember(kind, essence, facets=facets)
        for kind, essence, facets in reversed(specifications):
            second.remember(kind, essence, facets=facets)
        self.assertEqual(first.root_digest, second.root_digest)
        self.assertEqual(first.export(), second.export())

    def test_arbitrary_carrier_chunk_boundaries_do_not_change_meaning(self) -> None:
        continuum = Continuum()
        for number in range(50):
            continuum.remember("sample", {"number": number, "square": number * number})
        carrier = continuum.export()
        rng = random.Random(6604)
        cuts = sorted(rng.sample(range(1, len(carrier)), 100))
        chunks = []
        start = 0
        for cut in cuts:
            chunks.append(carrier[start:cut])
            start = cut
        chunks.append(carrier[start:])

        restored, report = Continuum.import_chunks(chunks)
        self.assertTrue(report.clean)
        self.assertEqual(restored.root_digest, continuum.root_digest)
        self.assertEqual(restored.export(), carrier)

    def test_frame_order_is_not_logical_order(self) -> None:
        continuum = Continuum()
        for number in range(8):
            continuum.remember("unordered", number)
        reversed_carrier = continuum.export(reverse=True)
        restored, report = Continuum.import_chunks([reversed_carrier])
        self.assertTrue(report.clean)
        self.assertEqual(restored.root_digest, continuum.root_digest)
        self.assertEqual(restored.export(), continuum.export())

    def test_duplicate_frames_are_converged_during_import(self) -> None:
        continuum = Continuum()
        continuum.remember("single", {"v": 1})
        carrier = continuum.export()
        frame = carrier[len(STREAM_MAGIC) :]
        restored, report = Continuum.import_chunks([carrier + frame])
        self.assertEqual(len(restored), 1)
        self.assertEqual(report.accepted, 1)
        self.assertEqual(report.duplicates, 1)
        self.assertTrue(report.clean)

    def test_local_corruption_is_detected_and_unaffected_meaning_is_salvaged(self) -> None:
        continuum = Continuum()
        for index in range(5):
            continuum.remember("cell", {"index": index})
        carrier = bytearray(continuum.export())
        frame_positions = []
        cursor = 0
        while True:
            cursor = carrier.find(FRAME_SYNC, cursor)
            if cursor < 0:
                break
            frame_positions.append(cursor)
            cursor += len(FRAME_SYNC)
        self.assertEqual(len(frame_positions), 5)
        middle_start = frame_positions[2]
        next_start = frame_positions[3]
        corrupted_identity = continuum.identities[2]
        carrier[middle_start + len(FRAME_SYNC) + 3] ^= 0x55

        with self.assertRaises(CarrierCorruption):
            Continuum.import_chunks([bytes(carrier)])

        restored, report = Continuum.import_chunks([bytes(carrier)], salvage=True)
        self.assertEqual(report.rejected, 1)
        self.assertEqual(len(restored), 4)
        self.assertNotIn(corrupted_identity, restored)
        self.assertGreaterEqual(report.skipped_bytes, next_start - middle_start)

    def test_unknown_trailing_carrier_data_is_strictly_rejected_or_reported(self) -> None:
        continuum = Continuum()
        continuum.remember("state", "ok")
        carrier = continuum.export() + b"foreign-carrier-tail"
        with self.assertRaises(CarrierCorruption):
            Continuum.import_chunks([carrier])
        restored, report = Continuum.import_chunks([carrier], salvage=True)
        self.assertEqual(len(restored), 1)
        self.assertEqual(report.trailing_bytes, len(b"foreign-carrier-tail"))
        self.assertFalse(report.clean)

    def test_thousand_impression_round_trip(self) -> None:
        continuum = Continuum()
        previous = None
        for number in range(1000):
            links = [] if previous is None else [previous]
            impression = continuum.remember(
                "aurum.state",
                {"sequence": number, "parity": number % 2},
                facets={"stream": "stress"},
                links=links,
            )
            previous = impression.identity
        carrier = continuum.export()
        restored, report = Continuum.import_chunks([carrier])
        self.assertTrue(report.clean)
        self.assertEqual(report.accepted, 1000)
        self.assertEqual(restored.root_digest, continuum.root_digest)
        self.assertEqual(len(restored.closure([previous])), 1000)


if __name__ == "__main__":
    unittest.main()
