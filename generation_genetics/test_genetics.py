import unittest

from generation_genetics.genetics import Gene, RepresentationMetrics, inherit_genes, representation_preference


class GenerationGeneticsTests(unittest.TestCase):
    def test_excludes_node_local_and_unproven_state(self) -> None:
        genes = [
            Gene("pc01-nic-timing", "hardware-fact", "node-local", 0.99, 5, True, "a"),
            Gene("usb-recovery", "capability", "portable", 0.95, 3, True, "b"),
            Gene("new-idea", "optimization", "portable", 0.99, 1, True, "c"),
            Gene("regressed", "optimization", "portable", 0.99, 4, False, "d"),
        ]
        inherited = inherit_genes(genes)
        self.assertEqual([gene.name for gene in inherited], ["usb-recovery"])

    def test_deduplicates_payloads(self) -> None:
        genes = [
            Gene("lesson-a", "failure-lesson", "portable", 0.95, 2, True, "same"),
            Gene("lesson-b", "failure-lesson", "portable", 0.96, 3, True, "same"),
        ]
        self.assertEqual(len(inherit_genes(genes)), 1)

    def test_codelation_preference_requires_both_dimensions_to_improve(self) -> None:
        baseline = RepresentationMetrics(4, 16, 40, 60)
        better = RepresentationMetrics(8, 12, 80, 20)
        only_machine_native = RepresentationMetrics(4, 16, 90, 10)
        self.assertTrue(representation_preference(better, baseline))
        self.assertFalse(representation_preference(only_machine_native, baseline))


if __name__ == "__main__":
    unittest.main()
