from __future__ import annotations

import unittest

from anticipatory_state import (
    CandidateIntent,
    ResourceBudget,
    SpeculationPolicy,
    build_speculative_plan,
)


class AnticipatoryStateTests(unittest.TestCase):
    def budget(self):
        return ResourceBudget(
            idle_cpu_capacity=0.70,
            free_ram_mb=2048,
            foreground_ram_reserve_mb=1024,
            storage_write_budget_mb=256,
            max_privacy_cost=0.5,
        )

    def test_high_value_low_cost_branch_is_prepared_first(self):
        plan = build_speculative_plan(
            [
                CandidateIntent("movie", 0.6, 2.0, 5000, 0.1, 128),
                CandidateIntent("expensive-low-probability", 0.1, 1.0, 1000, 0.5, 768),
            ],
            self.budget(),
        )
        self.assertEqual(plan["prepared"][0]["intent"], "movie")

    def test_foreground_ram_reserve_is_never_consumed(self):
        plan = build_speculative_plan(
            [CandidateIntent("too-large", 1.0, 10.0, 10000, 0.1, 1500)],
            self.budget(),
        )
        self.assertEqual(plan["held"][0]["held_reason"], "foreground-ram-reserve")
        self.assertGreaterEqual(plan["remaining"]["reclaimable_ram_mb"], 0)

    def test_privacy_budget_fails_closed(self):
        plan = build_speculative_plan(
            [CandidateIntent("private-context", 1.0, 10.0, 10000, 0.1, 64, privacy_cost=0.9)],
            self.budget(),
        )
        self.assertEqual(plan["held"][0]["held_reason"], "privacy-budget")

    def test_speculation_never_authorizes_action_or_lkg_mutation(self):
        plan = build_speculative_plan(
            [CandidateIntent("dinner-suggestion", 0.8, 3.0, 3000, 0.1, 64)],
            self.budget(),
        )
        self.assertFalse(plan["external_action_allowed"])
        self.assertFalse(plan["active_state_mutation_allowed"])
        self.assertFalse(plan["lkg_mutation_allowed"])
        self.assertTrue(plan["prepared"][0]["prepare_only"])
        self.assertFalse(plan["prepared"][0]["action_allowed"])

    def test_storage_churn_is_bounded(self):
        plan = build_speculative_plan(
            [CandidateIntent("huge-prefetch", 1.0, 10.0, 10000, 0.1, 64, storage_write_mb=512)],
            self.budget(),
        )
        self.assertEqual(plan["held"][0]["held_reason"], "storage-write-budget")

    def test_usefully_full_policy_keeps_foreground_headroom(self):
        policy = SpeculationPolicy(idle_cpu_target=0.9, reclaimable_ram_target=0.8, minimum_score=0.01)
        plan = build_speculative_plan(
            [
                CandidateIntent("a", 0.9, 5.0, 5000, 0.2, 256),
                CandidateIntent("b", 0.8, 4.0, 4000, 0.2, 256),
            ],
            self.budget(),
            policy,
        )
        self.assertLessEqual(plan["utilization"]["speculative_cpu_used"], 0.63)
        self.assertLessEqual(plan["utilization"]["reclaimable_ram_used_mb"], 819)
        self.assertEqual(plan["policy"]["idle_cpu_target"], 0.9)
        self.assertEqual(plan["policy"]["reclaimable_ram_target"], 0.8)

    def test_low_value_junk_is_not_used_just_to_fill_resources(self):
        policy = SpeculationPolicy(minimum_score=0.5)
        plan = build_speculative_plan(
            [CandidateIntent("junk-future", 0.01, 0.1, 1, 0.01, 1)],
            self.budget(),
            policy,
        )
        self.assertEqual(plan["prepared"], [])
        self.assertEqual(plan["held"][0]["held_reason"], "insufficient-future-value")


if __name__ == "__main__":
    unittest.main()
