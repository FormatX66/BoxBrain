from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_native_autonomous_chain as chain


def compatible_seed_state() -> dict:
    """Return an immutable checkpoint fixture for isolated-lane tests."""
    return {
        "schema": chain.STATE_SCHEMA,
        "catalog_revision": chain.CATALOG_REVISION,
        "synthesis_revision": chain.SYNTHESIS_REVISION,
        "self_debug_revision": chain.SELF_DEBUG_REVISION,
        "local_verification_revision": chain.LOCAL_VERIFICATION_REVISION,
        "_checkpoint": {
            "schema": "aurum-native-chain-resume-v1",
            "learned_expressions": {
                "learning_retention_ratio": {
                    "op": "safe_divide",
                    "left": {
                        "op": "length",
                        "value": {
                            "op": "intersection",
                            "left": {"op": "split", "value": {"op": "input", "name": "after"}},
                            "right": {"op": "split", "value": {"op": "input", "name": "before"}},
                        },
                    },
                    "right": {
                        "op": "length",
                        "value": {
                            "op": "union",
                            "left": {"op": "split", "value": {"op": "input", "name": "after"}},
                            "right": {"op": "split", "value": {"op": "input", "name": "before"}},
                        },
                    },
                }
            },
            "verified_local_capabilities": ["io-plan"],
        },
    }


class NativeAutonomousChainResumeTests(unittest.TestCase):
    def test_isolated_frontier_reuses_verified_capabilities_without_inheriting_generations(self) -> None:
        seed_state = compatible_seed_state()
        events: list[dict] = []

        result = chain.run_chain(
            start_gap="learning_retention_ratio",
            max_generations=1,
            seed_state=seed_state,
            on_progress=lambda event: events.append(dict(event)),
        )

        self.assertTrue(result["seeded_from_checkpoint"])
        self.assertEqual(result["resumed_from_generations"], 0)
        self.assertEqual(result["completed_generations"], 1)
        self.assertEqual(result["generations"][0]["gap"], "learning_retention_ratio")
        self.assertEqual(
            result["initial_seed_capabilities"],
            sorted(seed_state["_checkpoint"]["learned_expressions"]),
        )
        self.assertIn("io-plan", result["reusable_local_capabilities"])
        self.assertEqual(events[0]["status"], "seeded")

    def test_incompatible_persisted_checkpoint_is_not_seeded(self) -> None:
        seed_state = compatible_seed_state()
        seed_state["local_verification_revision"] = "stale-persisted-revision"
        events: list[dict] = []

        result = chain.run_chain(
            start_gap="learning_retention_ratio",
            max_generations=1,
            seed_state=seed_state,
            on_progress=lambda event: events.append(dict(event)),
        )

        self.assertFalse(result["seeded_from_checkpoint"])
        self.assertNotIn("io-plan", result["reusable_local_capabilities"])
        self.assertNotEqual(events[0]["status"], "seeded")

    def test_unchanged_external_block_uses_the_generation_checkpoint(self) -> None:
        gap = "adaptive_shell_live_trial_readiness"
        spec = chain.get_native_semantic_gap(gap)
        self.assertIsNotNone(spec)
        evidence = chain.apply_external_prerequisite_evidence_from_file(spec)
        external_status = {
            "applied": evidence.applied,
            "reason": evidence.reason,
            "evidence": dict(evidence.evidence) if evidence.evidence is not None else None,
        }
        resume_state = {
            "schema": chain.STATE_SCHEMA,
            "catalog_revision": chain.CATALOG_REVISION,
            "synthesis_revision": chain.SYNTHESIS_REVISION,
            "self_debug_revision": chain.SELF_DEBUG_REVISION,
            "local_verification_revision": chain.LOCAL_VERIFICATION_REVISION,
            "start_gap": "learning_delta_score",
            "completed_generations": 20,
            "latest_completed_gap": gap,
            "next_gap": gap,
            "blocked_reason": "external-prerequisite-blocked",
            "external_evidence": external_status,
            "generations": [{"generation": number, "gap": gap} for number in range(1, 21)],
            "_checkpoint": {
                "schema": "aurum-native-chain-resume-v1",
                "learned_expressions": {},
                "verified_local_capabilities": [],
            },
        }
        events: list[dict] = []

        result = chain.run_chain(resume_state=resume_state, on_progress=lambda event: events.append(dict(event)))

        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["completed_generations"], 20)
        self.assertEqual([event["status"] for event in events], ["resumed", "cached"])


if __name__ == "__main__":
    unittest.main()
