import unittest

from Projects.AdaptiveKernel.adaptive_runtime import (
    MAX_SPECULATIVE_CPU_PERCENT,
    MAX_SPECULATIVE_MEMORY_PERCENT,
    ReversibleAuthority,
    evaluate_shadow_window,
    execute_runtime_recommendation,
    verify_receipt,
)


def sample(
    number: int,
    *,
    temperature_c: float = 58.0,
    throttled: bool = False,
    memory_ratio: float = 0.50,
    normalized_load: float = 0.20,
    carrier: bool = True,
    driver: str = "smsc95xx",
    rx_errors: int = 0,
    tx_errors: int = 0,
    rx_dropped: int = 0,
    tx_dropped: int = 0,
) -> dict:
    total = 1_000_000
    cpu_count = 4
    return {
        "sample_id": f"sample-{number}",
        "temperature_c": temperature_c,
        "current_throttled": throttled,
        "memory_available_bytes": int(total * memory_ratio),
        "memory_total_bytes": total,
        "load_1m": normalized_load * cpu_count,
        "cpu_count": cpu_count,
        "ethernet": {
            "carrier": carrier,
            "operstate": "up" if carrier else "down",
            "reference_driver": driver,
            "rx_errors": rx_errors,
            "tx_errors": tx_errors,
            "rx_dropped": rx_dropped,
            "tx_dropped": tx_dropped,
        },
    }


class AdaptiveRuntimeTests(unittest.TestCase):
    def test_generation_3_wins_only_as_a_shadow_recommendation(self):
        receipt = evaluate_shadow_window([sample(1), sample(2), sample(3)])
        self.assertTrue(verify_receipt(receipt))
        self.assertEqual(receipt["decision"]["state"], "completed")
        self.assertEqual(receipt["decision"]["recommendation"], "shadow-change")
        self.assertEqual(
            receipt["decision"]["selected_policy_id"],
            "runtime-gen3-opportunistic-v1",
        )
        self.assertEqual(receipt["decision"]["selected_generation"], 3)
        self.assertFalse(receipt["decision"]["change_applied"])
        self.assertFalse(receipt["execution"]["enabled"])
        self.assertFalse(receipt["execution"]["performed"])
        self.assertFalse(receipt["invariants"]["live_hardware_contacted"])

    def test_generation_2_conservation_wins_under_safe_resource_pressure(self):
        samples = [
            sample(1, temperature_c=72.0, memory_ratio=0.15, normalized_load=0.9),
            sample(2, temperature_c=71.0, memory_ratio=0.16, normalized_load=0.8),
            sample(3, temperature_c=70.0, memory_ratio=0.17, normalized_load=0.75),
        ]
        receipt = evaluate_shadow_window(samples)
        self.assertEqual(
            receipt["decision"]["selected_policy_id"],
            "runtime-gen2-conserve-v1",
        )
        self.assertEqual(receipt["decision"]["selected_generation"], 2)

    def test_insufficient_evidence_recommends_no_change(self):
        receipt = evaluate_shadow_window([sample(1), sample(2)])
        self.assertEqual(receipt["decision"]["state"], "insufficient-evidence")
        self.assertEqual(receipt["decision"]["recommendation"], "no-change")
        self.assertEqual(
            receipt["decision"]["selected_policy_id"], "runtime-baseline-v1"
        )

    def test_baseline_wins_between_policy_envelopes(self):
        samples = [
            sample(1, temperature_c=68.0, memory_ratio=0.28, normalized_load=0.70),
            sample(2, temperature_c=67.0, memory_ratio=0.29, normalized_load=0.68),
            sample(3, temperature_c=66.0, memory_ratio=0.30, normalized_load=0.67),
        ]
        receipt = evaluate_shadow_window(samples)
        self.assertEqual(receipt["decision"]["reason"], "baseline-ranked-first")
        self.assertEqual(receipt["decision"]["recommendation"], "no-change")

    def test_current_throttle_quarantines_window_and_preserves_baseline(self):
        receipt = evaluate_shadow_window(
            [sample(1), sample(2, throttled=True), sample(3)]
        )
        self.assertEqual(receipt["decision"]["state"], "quarantined")
        self.assertEqual(receipt["decision"]["recommendation"], "no-change")
        self.assertEqual(receipt["evidence"]["quarantined_count"], 1)
        quarantined = receipt["evidence"]["sample_receipts"][1]
        self.assertEqual(quarantined["classification"], "unsafe")
        self.assertIn("current-throttle-active", quarantined["reasons"])

    def test_malformed_sample_and_reference_driver_mismatch_are_quarantined(self):
        malformed = sample(1)
        del malformed["memory_total_bytes"]
        mismatch = sample(2, driver="unexpected-driver")
        receipt = evaluate_shadow_window([malformed, mismatch, sample(3)])
        self.assertEqual(receipt["decision"]["state"], "quarantined")
        classifications = {
            item["classification"] for item in receipt["evidence"]["sample_receipts"]
        }
        self.assertEqual(classifications, {"malformed", "unsafe", "safe"})
        reasons = {
            reason
            for item in receipt["evidence"]["sample_receipts"]
            for reason in item["reasons"]
        }
        self.assertIn("invalid-memory-total-bytes", reasons)
        self.assertIn("reference-driver-mismatch", reasons)

    def test_packet_drop_evidence_quarantines_window(self):
        receipt = evaluate_shadow_window(
            [sample(1), sample(2, rx_dropped=1), sample(3)]
        )
        self.assertEqual(receipt["decision"]["state"], "quarantined")
        self.assertEqual(receipt["decision"]["recommendation"], "no-change")
        dropped = receipt["evidence"]["sample_receipts"][1]
        self.assertEqual(dropped["classification"], "unsafe")
        self.assertIn("ethernet-drop-evidence-present", dropped["reasons"])
        self.assertEqual(dropped["normalized"]["ethernet"]["rx_dropped"], 1)
        self.assertEqual(dropped["normalized"]["ethernet"]["tx_dropped"], 0)

    def test_drop_counters_are_required_nonnegative_fields(self):
        missing = sample(1)
        del missing["ethernet"]["tx_dropped"]
        negative = sample(2, rx_dropped=-1)
        receipt = evaluate_shadow_window([missing, negative, sample(3)])
        reasons = {
            reason
            for item in receipt["evidence"]["sample_receipts"]
            for reason in item["reasons"]
        }
        self.assertEqual(receipt["decision"]["state"], "quarantined")
        self.assertIn("invalid-tx-dropped", reasons)
        self.assertIn("invalid-rx-dropped", reasons)

    def test_policy_budgets_are_bounded_and_receipt_tampering_is_detected(self):
        receipt = evaluate_shadow_window([sample(1), sample(2), sample(3)])
        for policy in receipt["ranking"]:
            cpu = policy["speculative_cpu_percent"]
            memory = policy["speculative_memory_percent"]
            if cpu is not None:
                self.assertLessEqual(cpu, MAX_SPECULATIVE_CPU_PERCENT)
            if memory is not None:
                self.assertLessEqual(memory, MAX_SPECULATIVE_MEMORY_PERCENT)
        tampered = dict(receipt)
        tampered["mode"] = "active"
        self.assertFalse(verify_receipt(tampered))

    def test_executor_is_disabled_by_default_even_when_injected(self):
        receipt = evaluate_shadow_window([sample(1), sample(2), sample(3)])
        calls = []

        def executor(policy, rollback):
            calls.append((policy, rollback))
            return {
                "applied": True,
                "rollback_armed": True,
                "rollback_target": rollback["target"],
            }

        result = execute_runtime_recommendation(receipt, executor=executor)
        self.assertEqual(result["state"], "held")
        self.assertEqual(result["reason"], "active-executor-disabled")
        self.assertEqual(calls, [])

    def test_active_request_requires_receipt_bound_authority_and_rollback(self):
        receipt = evaluate_shadow_window([sample(1), sample(2), sample(3)])
        calls = []

        def executor(policy, rollback):
            calls.append((policy["policy_id"], rollback["target"]))
            return {
                "applied": True,
                "rollback_armed": True,
                "rollback_target": rollback["target"],
            }

        incomplete = ReversibleAuthority(
            authority_ref="test-authority",
            authorized=True,
            scope="adaptive-runtime-policy",
            reversible=True,
            shadow_receipt_sha256=receipt["receipt_sha256"],
            rollback_target="runtime-baseline-v1",
            rollback_receipt_sha256="",
        )
        held = execute_runtime_recommendation(
            receipt, active=True, authority=incomplete, executor=executor
        )
        self.assertEqual(held["state"], "held")
        self.assertIn(
            "invalid-rollback-receipt-sha256", held["authority_problems"]
        )
        self.assertEqual(calls, [])

        complete = ReversibleAuthority(
            authority_ref="test-authority",
            authorized=True,
            scope="adaptive-runtime-policy",
            reversible=True,
            shadow_receipt_sha256=receipt["receipt_sha256"],
            rollback_target="runtime-baseline-v1",
            rollback_receipt_sha256="a" * 64,
        )
        executed = execute_runtime_recommendation(
            receipt, active=True, authority=complete, executor=executor
        )
        self.assertEqual(executed["state"], "executed")
        self.assertTrue(executed["performed"])
        self.assertEqual(calls, [("runtime-gen3-opportunistic-v1", "runtime-baseline-v1")])
        self.assertTrue(verify_receipt(executed))


if __name__ == "__main__":
    unittest.main()
