import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))
from aurum_field import Field, FieldError, Ref, decode, encode, make_capability, make_grain  # noqa: E402


class AurumFieldTests(unittest.TestCase):
    def test_canonical_map_is_not_insertion_order_dependent(self):
        a = {"z": 9, "a": [1, 2, 3], "m": {"x": True}}
        b = {"m": {"x": True}, "a": [1, 2, 3], "z": 9}
        self.assertEqual(encode(a), encode(b))
        self.assertEqual(make_grain("fact", a).identity, make_grain("fact", b).identity)

    def test_codec_round_trip(self):
        source = {
            "none": None,
            "bool": [True, False],
            "ints": [0, -1, 1, -(2**80), 2**80],
            "bytes": b"\x00\xfffield",
            "text": "Aurum λ",
            "ref": Ref(bytes(range(32))),
        }
        self.assertEqual(decode(encode(source)), source)

    def test_field_identity_is_insertion_order_independent(self):
        grains = [make_grain("fact", {"n": i, "square": i * i}) for i in range(20)]
        f1 = Field(grains)
        f2 = Field(reversed(grains))
        self.assertEqual(f1.identity, f2.identity)

    def test_duplicate_grain_collapses_without_changing_identity(self):
        f = Field()
        r1 = f.add("fact", {"sensor": "x", "value": 12})
        before = f.identity
        r2 = f.add("fact", {"value": 12, "sensor": "x"})
        self.assertEqual(r1, r2)
        self.assertEqual(len(f), 1)
        self.assertEqual(before, f.identity)

    def test_projection_round_trip(self):
        f = Field()
        a = f.add("fact", "alpha")
        b = f.add("relation", {"from": a, "to": "ready"})
        f.add_grain(make_capability("remember", accepts=["fact"], provides=["recall"]))
        f.add("view", {"head": b})
        restored = Field.absorb(f.project())
        self.assertEqual(restored.identity, f.identity)
        self.assertEqual(restored.missing_refs(), set())

    def test_physical_record_order_is_not_semantic(self):
        f = Field()
        for i in range(50):
            f.add("fact", {"i": i, "payload": "x" * (i % 7)})
        ids = list(f.identities())
        random.Random(194).shuffle(ids)
        restored = Field.absorb(f.project(order=ids))
        self.assertEqual(restored.identity, f.identity)

    def test_merge_is_commutative_and_location_free(self):
        left = Field()
        right = Field()
        for i in range(0, 30, 2):
            left.add("fact", i)
        for i in range(1, 30, 2):
            right.add("fact", i)
        self.assertEqual(left.merge(right).identity, right.merge(left).identity)

    def test_partial_field_can_exist_and_close_later(self):
        source = Field()
        target = source.add("fact", {"state": "ready"})
        relation = make_grain("relation", {"points_to": target})
        partial = Field([relation])
        self.assertEqual(partial.missing_refs(), {target})
        closed = partial.merge(source)
        self.assertEqual(closed.missing_refs(), set())

    def test_corruption_is_detected(self):
        f = Field([make_grain("fact", {"critical": "value"})])
        blob = bytearray(f.project())
        blob[-1] ^= 0x01
        with self.assertRaises(FieldError):
            Field.absorb(bytes(blob))

    def test_recovery_can_skip_damaged_carrier_region(self):
        grains = [make_grain("fact", {"i": i}) for i in range(3)]
        f = Field(grains)
        pieces = [Field([grain]).project() for grain in grains]
        damaged = pieces[0] + b"BROKEN-CARRIER-BYTES" + pieces[1] + pieces[2]
        recovered = Field.absorb(damaged, recover=True)
        self.assertEqual(recovered.identity, f.identity)

    def test_capability_is_declarative_data_not_executable_payload(self):
        cap = make_capability(
            "field-store",
            accepts=["grain", "relation"],
            provides=["identity", "merge", "projection"],
            traits={"location_free": True, "immutable_grains": True},
        )
        self.assertEqual(cap.kind, 3)
        self.assertEqual(cap.value["name"], "field-store")
        self.assertNotIn("command", cap.value)
        self.assertNotIn("executable", cap.value)

    def test_deterministic_randomized_codec_and_field_stress(self):
        rnd = random.Random(660194)
        field = Field()
        samples = []
        for _ in range(500):
            value = {
                "n": rnd.randint(-(2**40), 2**40),
                "flag": bool(rnd.getrandbits(1)),
                "text": "".join(chr(97 + rnd.randrange(26)) for _ in range(rnd.randrange(20))),
                "data": bytes(rnd.randrange(256) for _ in range(rnd.randrange(20))),
                "list": [rnd.randrange(1000) for _ in range(rnd.randrange(8))],
            }
            samples.append(value)
            self.assertEqual(decode(encode(value)), value)
            field.add("fact", value)
        carrier = field.project()
        restored = Field.absorb(carrier)
        self.assertEqual(restored.identity, field.identity)
        self.assertEqual(len(restored), len({make_grain("fact", x).identity for x in samples}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
