import unittest

from Projects.Codelation.driver_synthesis import (
    CANDIDATE_SCHEMA,
    EvidenceClaim,
    reconcile_evidence,
    synthesize_candidate_interface,
)


class DriverSynthesisTests(unittest.TestCase):
    def test_independent_agreement_promotes_verified_claim(self):
        model = reconcile_evidence([
            EvidenceClaim("register.dma_enable", 8, "datasheet", "vendor-manual", 0.95),
            EvidenceClaim("register.dma_enable", 8, "reference_driver", "linux-driver", 0.90),
        ])
        entry = model["claims"]["register.dma_enable"]
        self.assertEqual("verified", entry["state"])
        self.assertEqual(8, entry["value"])
        self.assertEqual(["datasheet", "reference_driver"], entry["supporting_source_kinds"])

    def test_conflict_is_preserved_and_observation_can_corrobate_reference(self):
        model = reconcile_evidence([
            EvidenceClaim("irq.transfer_complete", 4, "datasheet", "manual", 0.90),
            EvidenceClaim("irq.transfer_complete", 7, "reference_driver", "bsd-driver", 0.95),
            EvidenceClaim("irq.transfer_complete", 7, "observation", "read-only-trace", 0.95),
        ])
        entry = model["claims"]["irq.transfer_complete"]
        self.assertEqual("verified", entry["state"])
        self.assertEqual(7, entry["value"])
        self.assertEqual(1, len(entry["contradictions"]))
        self.assertEqual(4, entry["contradictions"][0]["value"])

    def test_duplicate_same_kind_cannot_outvote_independent_sources(self):
        claims = [
            EvidenceClaim("reset.ready_value", 1, "reference_driver", f"driver-copy-{i}", 1.0)
            for i in range(20)
        ]
        claims.extend([
            EvidenceClaim("reset.ready_value", 0, "datasheet", "manual", 1.0),
            EvidenceClaim("reset.ready_value", 0, "schematic", "board", 1.0),
            EvidenceClaim("reset.ready_value", 0, "observation", "trace", 1.0),
        ])
        model = reconcile_evidence(claims)
        entry = model["claims"]["reset.ready_value"]
        self.assertEqual("verified", entry["state"])
        self.assertEqual(0, entry["value"])

    def test_single_source_claim_remains_uncertain(self):
        model = reconcile_evidence([
            EvidenceClaim("undocumented.mode", "x", "reference_driver", "one-driver", 1.0),
        ])
        entry = model["claims"]["undocumented.mode"]
        self.assertEqual("uncertain", entry["state"])
        self.assertIsNone(entry["value"])
        self.assertEqual("x", entry["candidate_value"])

    def test_invalid_or_unbounded_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            reconcile_evidence([
                EvidenceClaim("register.x", 1, "unknown-source", "mystery", 1.0),
            ])
        with self.assertRaises(ValueError):
            reconcile_evidence([
                EvidenceClaim("register.x", 1, "datasheet", "manual", 1.01),
            ])
        with self.assertRaises(ValueError):
            reconcile_evidence([
                EvidenceClaim("", 1, "datasheet", "manual", 1.0),
            ])

    def test_candidate_is_non_actuating_and_excludes_uncertain_claims(self):
        model = reconcile_evidence([
            EvidenceClaim("register.status", 16, "datasheet", "manual", 0.95),
            EvidenceClaim("register.status", 16, "reference_driver", "linux", 0.95),
            EvidenceClaim("register.mystery", 99, "reference_driver", "linux", 1.0),
        ])
        candidate = synthesize_candidate_interface(model)
        self.assertEqual(CANDIDATE_SCHEMA, candidate["schema"])
        self.assertEqual("non-actuating", candidate["mode"])
        self.assertEqual({"register.status": 16}, candidate["resolved_claims"])
        self.assertFalse(candidate["promotion_gates"]["physical_write_authorized"])
        self.assertFalse(candidate["promotion_gates"]["firmware_change_authorized"])
        self.assertTrue(candidate["promotion_gates"]["recovery_path_required_before_physical_actuation"])
        self.assertEqual(["linux"], candidate["reference_driver_teachers"])

    def test_model_identity_is_deterministic_across_input_order(self):
        a = EvidenceClaim("x", 1, "datasheet", "manual", 0.9)
        b = EvidenceClaim("x", 1, "reference_driver", "driver", 0.9)
        first = reconcile_evidence([a, b])
        second = reconcile_evidence([b, a])
        self.assertEqual(first["model_identity"], second["model_identity"])
        self.assertEqual(
            synthesize_candidate_interface(first)["candidate_identity"],
            synthesize_candidate_interface(second)["candidate_identity"],
        )


if __name__ == "__main__":
    unittest.main()
