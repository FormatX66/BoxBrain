import unittest

from driver_lab.model import Evidence, build_behavioral_fact, select_probe


class DriverLabTests(unittest.TestCase):
    def test_requires_independent_corroboration_for_probe(self) -> None:
        fact = build_behavioral_fact([
            Evidence("datasheet", "status-register-is-read-only", 0.97, "vendor"),
            Evidence("vendor-example", "status-register-is-read-only", 0.95, "vendor"),
        ])
        self.assertFalse(fact.safe_for_read_only_probe)
        self.assertEqual(select_probe(fact)["action"], "defer")

    def test_two_independent_sources_can_unlock_read_only_observation(self) -> None:
        fact = build_behavioral_fact([
            Evidence("datasheet", "status-register-is-read-only", 0.96, "vendor"),
            Evidence("proven-driver", "status-register-is-read-only", 0.92, "linux"),
        ])
        probe = select_probe(fact)
        self.assertTrue(fact.safe_for_read_only_probe)
        self.assertEqual(probe["action"], "read-only-observe")
        self.assertFalse(probe["writes_allowed"])

    def test_conflicting_hypotheses_are_not_silently_merged(self) -> None:
        with self.assertRaises(ValueError):
            build_behavioral_fact([
                Evidence("datasheet", "bit-7-ready", 0.9, "vendor"),
                Evidence("driver", "bit-7-error", 0.9, "linux"),
            ])


if __name__ == "__main__":
    unittest.main()
