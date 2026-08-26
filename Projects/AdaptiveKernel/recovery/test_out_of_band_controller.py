from __future__ import annotations

import unittest

from Projects.AdaptiveKernel.pi3_watchdog_contract import WatchdogEvidence, WatchdogState, evaluate_watchdog
from Projects.AdaptiveKernel.recovery.out_of_band_controller import (
    ActuationResult,
    ComponentIdentity,
    ControllerIdentity,
    LKGIdentity,
    Observation,
    ObservationState,
    OutOfBandRecoveryController,
    RecoveredState,
    RecoveryRunState,
    SimulationActuator,
    SimulationObserver,
    SimulationVerifier,
    TargetIdentity,
)


class OutOfBandRecoveryControllerTests(unittest.TestCase):
    def component(self, role: str, **changes) -> ComponentIdentity:
        values = {
            "component_id": f"simulation-{role}",
            "role": role,
            "identity_fingerprint": f"SHA256:simulation-{role}",
            "independently_identified": True,
            "independent_of_target_kernel": True,
            "simulation_only": True,
        }
        values.update(changes)
        return ComponentIdentity(**values)

    def make_controller(
        self,
        *,
        observation_state: ObservationState = ObservationState.FAILED,
        automatic_detection: bool = True,
        observer_identity: ComponentIdentity | None = None,
        actuator_identity: ComponentIdentity | None = None,
        verifier_identity: ComponentIdentity | None = None,
        controller_identity: ControllerIdentity | None = None,
        actuation: ActuationResult | None = None,
        recovered_target: TargetIdentity | None = None,
        recovered_lkg: LKGIdentity | None = None,
        recovered_healthy: bool = True,
    ):
        target = TargetIdentity("Raspberry Pi 3 Model B Rev 1.2", "00000000a6a7df7f")
        lkg = LKGIdentity("pi3-current-card-lkg", "a" * 64)
        observer = SimulationObserver(
            observer_identity or self.component("observer"),
            Observation(
                state=observation_state,
                automatic_detection=automatic_detection,
                target_kernel_responsive=False,
                evidence_refs=("simulation:independent-observation",),
                reason="simulated heartbeat and video loss",
            ),
        )
        actuator = SimulationActuator(
            actuator_identity or self.component("actuator"),
            actuation
            or ActuationResult(
                requested=True,
                completed=True,
                power_control_exercised=True,
                lkg_recovery_exercised=True,
                evidence_refs=("simulation:power-lkg-cycle",),
                reason="simulated independent power cycle and LKG selection",
            ),
        )
        verifier = SimulationVerifier(
            verifier_identity or self.component("verifier"),
            RecoveredState(
                target=recovered_target or target,
                lkg=recovered_lkg or lkg,
                healthy=recovered_healthy,
                evidence_refs=("simulation:post-recovery-verification",),
            ),
        )
        controller = OutOfBandRecoveryController(
            controller=controller_identity
            or ControllerIdentity(
                controller_id="simulation-controller",
                identity_fingerprint="SHA256:simulation-controller",
                independently_identified=True,
                independent_of_target_kernel=True,
                simulation_only=True,
            ),
            observer=observer,
            actuator=actuator,
            verifier=verifier,
            expected_target=target,
            expected_lkg=lkg,
        )
        return controller, observer, actuator, verifier

    def test_failed_target_exercises_complete_simulation_but_grants_no_authority(self):
        controller, observer, actuator, verifier = self.make_controller()
        receipt = controller.run()
        self.assertEqual(receipt["state"], RecoveryRunState.SIMULATED_VERIFIED.value)
        self.assertEqual((observer.calls, actuator.calls, verifier.calls), (1, 1, 1))
        self.assertTrue(receipt["post_recovery_verification"]["exact_target_match"])
        self.assertTrue(receipt["post_recovery_verification"]["exact_lkg_match"])
        self.assertFalse(receipt["safety"]["hardware_actuation_performed"])
        self.assertFalse(receipt["safety"]["mutation_authority_granted"])
        self.assertFalse(receipt["watchdog_decision"]["watchdog_proven"])

    def test_receipt_watchdog_evidence_preserves_existing_evaluator_semantics(self):
        controller, _, _, _ = self.make_controller()
        receipt = controller.run()
        evidence = WatchdogEvidence(**receipt["watchdog_evidence"])
        decision = evaluate_watchdog(evidence)
        self.assertEqual(decision.state, WatchdogState.HELD_IDENTITY)
        self.assertFalse(decision.watchdog_proven)
        self.assertFalse(decision.mutation_authority_granted)
        self.assertEqual(
            decision.next_gate,
            "prove-pinned-target-and-independent-controller-identity",
        )

    def test_healthy_observation_never_calls_actuator_or_verifier(self):
        controller, observer, actuator, verifier = self.make_controller(
            observation_state=ObservationState.HEALTHY
        )
        receipt = controller.run()
        self.assertEqual(receipt["state"], RecoveryRunState.NO_CHANGE.value)
        self.assertEqual((observer.calls, actuator.calls, verifier.calls), (1, 0, 0))

    def test_ambiguous_failure_waits_without_actuation(self):
        controller, _, actuator, verifier = self.make_controller(
            observation_state=ObservationState.AMBIGUOUS
        )
        receipt = controller.run()
        self.assertEqual(receipt["state"], RecoveryRunState.WAITING.value)
        self.assertEqual((actuator.calls, verifier.calls), (0, 0))

    def test_manual_or_unreferenced_failure_detection_is_refused(self):
        controller, _, actuator, verifier = self.make_controller(automatic_detection=False)
        receipt = controller.run()
        self.assertEqual(receipt["state"], RecoveryRunState.REFUSED.value)
        self.assertEqual((actuator.calls, verifier.calls), (0, 0))

    def test_non_independent_observer_is_refused_before_observation(self):
        controller, observer, actuator, _ = self.make_controller(
            observer_identity=self.component("observer", independent_of_target_kernel=False)
        )
        receipt = controller.run()
        self.assertEqual(receipt["state"], RecoveryRunState.REFUSED.value)
        self.assertEqual((observer.calls, actuator.calls), (0, 0))

    def test_controller_without_independent_identity_is_refused(self):
        controller, observer, actuator, _ = self.make_controller(
            controller_identity=ControllerIdentity(
                controller_id="simulation-controller",
                identity_fingerprint="SHA256:simulation-controller",
                independently_identified=False,
                independent_of_target_kernel=True,
                simulation_only=True,
            )
        )
        receipt = controller.run()
        self.assertEqual(receipt["state"], RecoveryRunState.REFUSED.value)
        self.assertEqual((observer.calls, actuator.calls), (0, 0))

    def test_non_simulation_adapter_is_refused(self):
        controller, observer, actuator, _ = self.make_controller(
            actuator_identity=self.component("actuator", simulation_only=False)
        )
        receipt = controller.run()
        self.assertEqual(receipt["state"], RecoveryRunState.REFUSED.value)
        self.assertEqual((observer.calls, actuator.calls), (0, 0))

    def test_actuator_without_power_or_lkg_capability_is_refused(self):
        controller, observer, actuator, _ = self.make_controller()
        actuator.can_control_power = False
        receipt = controller.run()
        self.assertEqual(receipt["state"], RecoveryRunState.REFUSED.value)
        self.assertEqual((observer.calls, actuator.calls), (0, 0))

    def test_component_identity_collision_is_refused(self):
        controller, observer, actuator, _ = self.make_controller(
            actuator_identity=self.component(
                "actuator",
                component_id="simulation-observer",
                identity_fingerprint="SHA256:simulation-actuator",
            )
        )
        receipt = controller.run()
        self.assertEqual(receipt["state"], RecoveryRunState.REFUSED.value)
        self.assertEqual((observer.calls, actuator.calls), (0, 0))

    def test_incomplete_power_or_lkg_actuation_never_verifies(self):
        incomplete = ActuationResult(
            requested=True,
            completed=True,
            power_control_exercised=True,
            lkg_recovery_exercised=False,
            evidence_refs=("simulation:partial-cycle",),
            reason="LKG selection was not exercised",
        )
        controller, _, actuator, verifier = self.make_controller(actuation=incomplete)
        receipt = controller.run()
        self.assertEqual(receipt["state"], RecoveryRunState.SIMULATED_UNVERIFIED.value)
        self.assertEqual((actuator.calls, verifier.calls), (1, 0))

    def test_wrong_recovered_target_identity_fails_closed(self):
        wrong = TargetIdentity("Raspberry Pi 3 Model B Rev 1.3", "00000000a6a7df7f")
        controller, _, _, _ = self.make_controller(recovered_target=wrong)
        receipt = controller.run()
        self.assertEqual(receipt["state"], RecoveryRunState.SIMULATED_UNVERIFIED.value)
        self.assertFalse(receipt["post_recovery_verification"]["exact_target_match"])
        self.assertFalse(receipt["watchdog_decision"]["watchdog_proven"])

    def test_wrong_recovered_lkg_fails_closed(self):
        wrong = LKGIdentity("different-lkg", "b" * 64)
        controller, _, _, _ = self.make_controller(recovered_lkg=wrong)
        receipt = controller.run()
        self.assertEqual(receipt["state"], RecoveryRunState.SIMULATED_UNVERIFIED.value)
        self.assertFalse(receipt["post_recovery_verification"]["exact_lkg_match"])
        self.assertFalse(receipt["safety"]["mutation_authority_granted"])

    def test_unhealthy_recovered_target_fails_closed(self):
        controller, _, _, _ = self.make_controller(recovered_healthy=False)
        receipt = controller.run()
        self.assertEqual(receipt["state"], RecoveryRunState.SIMULATED_UNVERIFIED.value)
        self.assertFalse(receipt["post_recovery_verification"]["healthy"])
        self.assertFalse(receipt["watchdog_decision"]["watchdog_proven"])


if __name__ == "__main__":
    unittest.main()
