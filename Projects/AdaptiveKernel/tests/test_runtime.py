import json
import unittest

from Projects.AdaptiveKernel.adaptive_kernel import (
    CapabilityRule,
    KernelPlan,
    evaluate,
    plan,
)
from Projects.AdaptiveKernel.runtime import (
    AdaptiveKernelRuntime,
    RealizationCandidate,
)


def candidate(
    candidate_id,
    rule_name,
    value=True,
    *,
    confidence=0.5,
    cost=1.0,
    reversible=True,
    compatible_when=(),
):
    return RealizationCandidate(
        candidate_id=candidate_id,
        rule_name=rule_name,
        confidence=confidence,
        cost=cost,
        reversible=reversible,
        compatible_when=compatible_when,
        propose=lambda state: {
            **state,
            f"kernel.capability.{rule_name}": value,
        },
    )


class AdaptiveKernelRuntimeTests(unittest.TestCase):
    def test_verified_candidate_is_promoted_with_audit_hashes(self):
        kernel_plan = plan(
            {"input.pointer": True},
            [CapabilityRule("pointer", ("input.pointer",), ("pointer",))],
        )
        runtime = AdaptiveKernelRuntime({"kernel.generation": 0})

        run = runtime.adapt(kernel_plan, [candidate("pointer-native", "pointer")])

        self.assertEqual(run.status, "success")
        self.assertEqual(run.promoted, ("pointer",))
        self.assertTrue(run.final_state["kernel.capability.pointer"])
        self.assertEqual(run.attempts[0].status, "success")
        self.assertNotEqual(run.attempts[0].before_hash, run.attempts[0].after_hash)
        self.assertEqual(
            run.attempts[0].proposed_hash,
            run.attempts[0].after_hash,
        )
        self.assertEqual(
            run.attempts[0].observed_hash,
            run.attempts[0].after_hash,
        )

    def test_failed_proposal_is_discarded_before_verified_fallback(self):
        kernel_plan = plan(
            {"net.link": True},
            [CapabilityRule("network", ("net.link",), ("network",))],
        )
        runtime = AdaptiveKernelRuntime({"network.link": "down"})
        candidates = [
            candidate("network-fast", "network", False, confidence=0.9),
            candidate("network-safe", "network", True, confidence=0.7),
        ]

        run = runtime.adapt(kernel_plan, candidates)

        self.assertEqual(run.status, "success")
        self.assertEqual(
            [(attempt.candidate_id, attempt.status) for attempt in run.attempts],
            [("network-fast", "failed"), ("network-safe", "success")],
        )
        failed = run.attempts[0]
        self.assertTrue(failed.rolled_back)
        self.assertEqual(failed.before_hash, failed.after_hash)
        self.assertNotEqual(failed.proposed_hash, failed.after_hash)

    def test_observation_mismatch_cannot_be_promoted_as_claimed_success(self):
        kernel_plan = plan(
            {"net.link": True},
            [CapabilityRule("network", ("net.link",), ("network",))],
        )
        claimed = candidate("network-claimed", "network", True, confidence=0.9)

        run = AdaptiveKernelRuntime().adapt(
            kernel_plan,
            [claimed],
            observer=lambda rule, proposed: {
                **proposed,
                "kernel.capability.network": False,
            },
        )

        self.assertEqual(run.status, "failed")
        self.assertEqual(run.attempts[0].reason, "verification_mismatch")
        self.assertNotEqual(
            run.attempts[0].proposed_hash,
            run.attempts[0].observed_hash,
        )
        self.assertNotIn("kernel.capability.network", run.final_state)

    def test_learning_checkpoint_reorders_a_later_equivalent_run(self):
        kernel_plan = plan(
            {"net.link": True},
            [CapabilityRule("network", ("net.link",), ("network",))],
        )
        candidates = [
            candidate("network-fast", "network", False, confidence=0.9),
            candidate("network-safe", "network", True, confidence=0.7),
        ]
        first = AdaptiveKernelRuntime()
        first.adapt(kernel_plan, candidates)
        checkpoint = first.learning_snapshot()
        json.dumps(checkpoint)

        restored = AdaptiveKernelRuntime(learning_snapshot=checkpoint)
        second_run = restored.adapt(kernel_plan, candidates)

        executed = [
            attempt.candidate_id
            for attempt in second_run.attempts
            if attempt.status in {"success", "failed", "no_change"}
        ]
        self.assertEqual(executed, ["network-safe"])
        self.assertEqual(restored.learning_for("network-safe").successes, 2)

    def test_repeated_failure_quarantines_and_prevents_replay(self):
        kernel_plan = plan(
            {"device.present": True},
            [CapabilityRule("device", ("device.present",), ("device",))],
        )
        runtime = AdaptiveKernelRuntime(quarantine_after_failures=2)
        broken = candidate("device-broken", "device", False, confidence=0.9)

        self.assertEqual(runtime.adapt(kernel_plan, [broken]).status, "failed")
        self.assertEqual(runtime.adapt(kernel_plan, [broken]).status, "failed")
        third = runtime.adapt(kernel_plan, [broken])

        self.assertEqual(third.status, "refused")
        self.assertEqual(third.attempts[0].reason, "candidate_quarantined")
        self.assertTrue(runtime.learning_for("device-broken").quarantined)

    def test_changed_evidence_can_explicitly_release_quarantine(self):
        kernel_plan = plan(
            {"device.present": True},
            [CapabilityRule("device", ("device.present",), ("device",))],
        )
        runtime = AdaptiveKernelRuntime(quarantine_after_failures=1)
        runtime.adapt(kernel_plan, [candidate("device-candidate", "device", False)])

        runtime.release_quarantine("device-candidate", confidence=0.8)
        run = runtime.adapt(
            kernel_plan,
            [candidate("device-candidate", "device", True)],
        )

        self.assertEqual(run.status, "success")
        self.assertFalse(runtime.learning_for("device-candidate").quarantined)

    def test_non_reversible_candidate_is_refused_without_calling_it(self):
        calls = []
        kernel_plan = plan(
            {"device.present": True},
            [CapabilityRule("device", ("device.present",), ("device",))],
        )
        unsafe = RealizationCandidate(
            "device-unsafe",
            "device",
            lambda state: calls.append(state) or state,
            reversible=False,
        )

        run = AdaptiveKernelRuntime().adapt(kernel_plan, [unsafe])

        self.assertEqual(run.status, "refused")
        self.assertEqual(calls, [])
        self.assertEqual(
            run.attempts[0].reason,
            "automatic_runtime_requires_reversible_candidate",
        )

    def test_runtime_rechecks_risk_even_for_a_manually_constructed_plan(self):
        rule = CapabilityRule("firmware", (), ("firmware",), risk="high")
        forced_plan = KernelPlan((evaluate(rule, {}),), ())

        run = AdaptiveKernelRuntime().adapt(
            forced_plan,
            [candidate("firmware-writer", "firmware")],
        )

        self.assertEqual(run.status, "refused")
        self.assertEqual(run.attempts[0].reason, "risk_gate")
        self.assertNotIn("kernel.capability.firmware", run.final_state)

    def test_invariant_failure_discards_candidate_and_uses_fallback(self):
        kernel_plan = plan(
            {"thermal.sensor": True},
            [CapabilityRule("cooling", ("thermal.sensor",), ("cooling",))],
        )
        hot = RealizationCandidate(
            "cooling-hot",
            "cooling",
            lambda state: {
                **state,
                "kernel.capability.cooling": True,
                "thermal.celsius": 100,
            },
            confidence=0.9,
        )
        safe = RealizationCandidate(
            "cooling-safe",
            "cooling",
            lambda state: {
                **state,
                "kernel.capability.cooling": True,
                "thermal.celsius": 55,
            },
            confidence=0.7,
        )

        run = AdaptiveKernelRuntime({"thermal.celsius": 40}).adapt(
            kernel_plan,
            [hot, safe],
            invariant=lambda state: state["thermal.celsius"] <= 80,
        )

        self.assertEqual(run.status, "success")
        self.assertEqual(run.attempts[0].reason, "invariant_violation")
        self.assertEqual(run.final_state["thermal.celsius"], 55)

    def test_compatibility_and_missing_candidates_are_explicitly_blocked(self):
        rules = [
            CapabilityRule("pointer", (), ("pointer",)),
            CapabilityRule("network", (), ("network",)),
        ]
        kernel_plan = plan({}, rules)
        runtime = AdaptiveKernelRuntime({"machine.bus": "usb"})
        incompatible = candidate(
            "pointer-pcie",
            "pointer",
            compatible_when=(("machine.bus", "pcie"),),
        )

        run = runtime.adapt(kernel_plan, [incompatible])

        self.assertEqual(run.status, "blocked")
        self.assertEqual(run.unresolved, ("pointer", "network"))
        self.assertEqual(
            [(attempt.rule_name, attempt.reason) for attempt in run.attempts],
            [("pointer", "incompatible_state"), ("network", "no_candidate")],
        )

    def test_blocked_front_does_not_erase_independent_verified_progress(self):
        rules = [
            CapabilityRule("pointer", (), ("pointer",)),
            CapabilityRule("network", (), ("network",)),
        ]
        kernel_plan = plan({}, rules)

        run = AdaptiveKernelRuntime().adapt(
            kernel_plan,
            [candidate("pointer-native", "pointer")],
        )

        self.assertEqual(run.status, "blocked")
        self.assertEqual(run.promoted, ("pointer",))
        self.assertEqual(run.unresolved, ("network",))
        self.assertTrue(run.final_state["kernel.capability.pointer"])

    def test_attempt_limit_is_visible_in_receipt(self):
        kernel_plan = plan({}, [CapabilityRule("device", (), ("device",))])
        candidates = [
            candidate("device-a", "device", False, confidence=0.9),
            candidate("device-b", "device", True, confidence=0.8),
        ]

        run = AdaptiveKernelRuntime().adapt(
            kernel_plan,
            candidates,
            max_candidates_per_rule=1,
        )

        self.assertEqual(run.status, "failed")
        self.assertEqual(
            [(attempt.candidate_id, attempt.reason) for attempt in run.attempts],
            [
                ("device-a", "verification_mismatch"),
                ("device-b", "bounded_attempt_limit"),
            ],
        )

    def test_verified_existing_state_is_no_change_not_false_progress(self):
        kernel_plan = plan(
            {"input.pointer": True},
            [CapabilityRule("pointer", ("input.pointer",), ("pointer",))],
        )
        runtime = AdaptiveKernelRuntime({"kernel.capability.pointer": True})

        run = runtime.adapt(kernel_plan, [candidate("pointer-native", "pointer")])

        self.assertEqual(run.status, "no_change")
        self.assertEqual(run.already_satisfied, ("pointer",))
        self.assertEqual(runtime.learning_for("pointer-native").successes, 0)

    def test_learning_identity_cannot_silently_move_to_another_rule(self):
        runtime = AdaptiveKernelRuntime()
        pointer_plan = plan({}, [CapabilityRule("pointer", (), ("pointer",))])
        runtime.adapt(pointer_plan, [candidate("stable-id", "pointer")])
        network_plan = plan({}, [CapabilityRule("network", (), ("network",))])

        with self.assertRaisesRegex(ValueError, "changed rule identity"):
            runtime.adapt(network_plan, [candidate("stable-id", "network")])

    def test_invalid_learning_schema_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            AdaptiveKernelRuntime(learning_snapshot={"schema": "unknown"})


if __name__ == "__main__":
    unittest.main()
