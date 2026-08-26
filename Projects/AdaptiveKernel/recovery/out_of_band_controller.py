"""Fail-closed, simulation-only out-of-band recovery controller scaffold.

The controller models the independent observer, independently identified
controller, independent power/LKG actuator, automatic failure detection,
recovery action, and exact post-recovery target/LKG verification required by
``pi3_watchdog_contract``.  This module contains no live transport or hardware
adapter and cannot grant mutation authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Protocol

from Projects.AdaptiveKernel.pi3_watchdog_contract import (
    WatchdogEvidence,
    evaluate_watchdog,
)


RECEIPT_SCHEMA = "aurum.pi3.oob-recovery.simulation.v1"
EXPECTED_MODEL_MARKER = "Raspberry Pi 3 Model B Rev 1.2"
EXPECTED_SERIAL = "00000000a6a7df7f"


class RecoveryContractError(RuntimeError):
    """The recovery topology or simulation evidence failed closed."""


class ObservationState(str, Enum):
    HEALTHY = "healthy"
    FAILED = "failed"
    AMBIGUOUS = "ambiguous"


class RecoveryRunState(str, Enum):
    NO_CHANGE = "no-change-target-healthy"
    WAITING = "waiting-failure-state-ambiguous"
    REFUSED = "refused-recovery-contract"
    SIMULATED_VERIFIED = "simulated-recovery-verified"
    SIMULATED_UNVERIFIED = "simulated-recovery-unverified"


@dataclass(frozen=True)
class TargetIdentity:
    model_marker: str
    serial: str

    def exact_match(self, other: "TargetIdentity") -> bool:
        return self.model_marker == other.model_marker and self.serial == other.serial


@dataclass(frozen=True)
class LKGIdentity:
    artifact_id: str
    sha256: str

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            raise RecoveryContractError("LKG artifact identity is required")
        digest = self.sha256.casefold()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise RecoveryContractError("LKG SHA-256 is invalid")

    def exact_match(self, other: "LKGIdentity") -> bool:
        return self.artifact_id == other.artifact_id and self.sha256.casefold() == other.sha256.casefold()


@dataclass(frozen=True)
class ComponentIdentity:
    component_id: str
    role: str
    identity_fingerprint: str
    independently_identified: bool
    independent_of_target_kernel: bool
    simulation_only: bool = True


@dataclass(frozen=True)
class ControllerIdentity:
    controller_id: str
    identity_fingerprint: str
    independently_identified: bool
    independent_of_target_kernel: bool
    simulation_only: bool = True


@dataclass(frozen=True)
class Observation:
    state: ObservationState
    automatic_detection: bool
    target_kernel_responsive: bool
    evidence_refs: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ActuationResult:
    requested: bool
    completed: bool
    power_control_exercised: bool
    lkg_recovery_exercised: bool
    evidence_refs: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class RecoveredState:
    target: TargetIdentity
    lkg: LKGIdentity
    healthy: bool
    evidence_refs: tuple[str, ...]


class ObserverAdapter(Protocol):
    identity: ComponentIdentity

    def observe(self) -> Observation: ...


class RecoveryActuatorAdapter(Protocol):
    identity: ComponentIdentity
    can_control_power: bool
    can_select_or_restore_lkg: bool

    def recover(self, *, expected_target: TargetIdentity, expected_lkg: LKGIdentity) -> ActuationResult: ...


class PostRecoveryVerifierAdapter(Protocol):
    identity: ComponentIdentity

    def verify(self) -> RecoveredState: ...


@dataclass
class SimulationObserver:
    identity: ComponentIdentity
    observation: Observation
    calls: int = 0

    def observe(self) -> Observation:
        self.calls += 1
        return self.observation


@dataclass
class SimulationActuator:
    identity: ComponentIdentity
    result: ActuationResult
    can_control_power: bool = True
    can_select_or_restore_lkg: bool = True
    calls: int = 0

    def recover(self, *, expected_target: TargetIdentity, expected_lkg: LKGIdentity) -> ActuationResult:
        del expected_target, expected_lkg
        self.calls += 1
        return self.result


@dataclass
class SimulationVerifier:
    identity: ComponentIdentity
    recovered_state: RecoveredState
    calls: int = 0

    def verify(self) -> RecoveredState:
        self.calls += 1
        return self.recovered_state


class OutOfBandRecoveryController:
    """Exercise the recovery state machine without a live actuation route."""

    def __init__(
        self,
        *,
        controller: ControllerIdentity,
        observer: ObserverAdapter,
        actuator: RecoveryActuatorAdapter,
        verifier: PostRecoveryVerifierAdapter,
        expected_target: TargetIdentity,
        expected_lkg: LKGIdentity,
    ) -> None:
        self.controller = controller
        self.observer = observer
        self.actuator = actuator
        self.verifier = verifier
        self.expected_target = expected_target
        self.expected_lkg = expected_lkg

    @staticmethod
    def _component_record(component: ComponentIdentity) -> dict[str, Any]:
        return {
            "component_id": component.component_id,
            "role": component.role,
            "identity_fingerprint": component.identity_fingerprint,
            "independently_identified": component.independently_identified,
            "independent_of_target_kernel": component.independent_of_target_kernel,
            "simulation_only": component.simulation_only,
        }

    def _validate_topology(self) -> None:
        if self.expected_target.model_marker != EXPECTED_MODEL_MARKER or self.expected_target.serial != EXPECTED_SERIAL:
            raise RecoveryContractError("target is not the pinned experimental Pi 3")

        components = (self.observer.identity, self.actuator.identity, self.verifier.identity)
        expected_roles = ("observer", "actuator", "verifier")
        for component, expected_role in zip(components, expected_roles, strict=True):
            if component.role != expected_role:
                raise RecoveryContractError(f"{expected_role} adapter identity has the wrong role")
            if not component.component_id.strip() or not component.identity_fingerprint.strip():
                raise RecoveryContractError(f"{expected_role} identity is incomplete")
            if not component.independently_identified:
                raise RecoveryContractError(f"{expected_role} identity is not independently identified")
            if not component.independent_of_target_kernel:
                raise RecoveryContractError(f"{expected_role} is not independent of the target kernel")
            if not component.simulation_only:
                raise RecoveryContractError("live adapters are outside the simulation-only controller boundary")

        if not self.controller.controller_id.strip() or not self.controller.identity_fingerprint.strip():
            raise RecoveryContractError("controller identity is incomplete")
        if not self.controller.independently_identified or not self.controller.independent_of_target_kernel:
            raise RecoveryContractError("controller independence is unproven")
        if not self.controller.simulation_only:
            raise RecoveryContractError("live controller identity is outside the simulation-only boundary")

        identities = [
            (self.controller.controller_id, self.controller.identity_fingerprint),
            *((component.component_id, component.identity_fingerprint) for component in components),
        ]
        if len({item[0] for item in identities}) != len(identities):
            raise RecoveryContractError("controller, observer, actuator, and verifier IDs must be distinct")
        if len({item[1] for item in identities}) != len(identities):
            raise RecoveryContractError("controller, observer, actuator, and verifier fingerprints must be distinct")
        if not self.actuator.can_control_power or not self.actuator.can_select_or_restore_lkg:
            raise RecoveryContractError("actuator must model independent power and LKG recovery")

    @staticmethod
    def _physical_watchdog_evidence() -> WatchdogEvidence:
        # A successful simulation is implementation evidence, not physical proof.
        # Keep every physical proof bit false so the existing evaluator stays held.
        return WatchdogEvidence(
            pinned_target_identity=False,
            independent_controller_identity=False,
            observer_independent_of_target_kernel=False,
            recovery_actuator_independent_of_target_kernel=False,
            automatic_failure_detection_proven=False,
            automatic_recovery_actuation_proven=False,
            post_recovery_target_identity_proven=False,
            lkg_restored_and_healthy_proven=False,
            local_target_timer_only=False,
            network_only_actuation=False,
            mutation_authority_granted=False,
        )

    def _base_receipt(self) -> dict[str, Any]:
        evidence = self._physical_watchdog_evidence()
        decision = evaluate_watchdog(evidence)
        return {
            "schema": RECEIPT_SCHEMA,
            "mode": "simulation-only",
            "target_expected": asdict(self.expected_target),
            "lkg_expected": asdict(self.expected_lkg),
            "topology": {
                "controller": {
                    "controller_id": self.controller.controller_id,
                    "identity_fingerprint": self.controller.identity_fingerprint,
                    "independently_identified": self.controller.independently_identified,
                    "independent_of_target_kernel": self.controller.independent_of_target_kernel,
                    "simulation_only": self.controller.simulation_only,
                },
                "observer": self._component_record(self.observer.identity),
                "actuator": self._component_record(self.actuator.identity),
                "verifier": self._component_record(self.verifier.identity),
            },
            "watchdog_evidence": asdict(evidence),
            "watchdog_decision": {
                "state": decision.state.value,
                "watchdog_proven": decision.watchdog_proven,
                "mutation_authority_granted": decision.mutation_authority_granted,
                "next_gate": decision.next_gate,
            },
            "safety": {
                "hardware_actuation_performed": False,
                "network_activity_performed": False,
                "ssh_activity_performed": False,
                "boot_or_firmware_changed": False,
                "kernel_module_or_driver_changed": False,
                "mutation_authority_granted": False,
            },
            "remaining_physical_gates": [
                "independently identify the external observer/controller",
                "prove target-kernel-independent video or health observation",
                "independently identify and exercise the power/LKG actuator",
                "automatically detect a real target failure and actuate recovery",
                "re-prove exact Raspberry Pi 3 Model B Rev 1.2 marker and serial after recovery",
                "re-prove the exact protected LKG artifact and target health",
                "obtain separate fresh kernel-mutation authority only after watchdog proof",
            ],
        }

    def run(self) -> dict[str, Any]:
        try:
            self._validate_topology()
        except RecoveryContractError as exc:
            receipt = self._base_receipt()
            receipt.update({"state": RecoveryRunState.REFUSED.value, "reason": str(exc)})
            return receipt

        observation = self.observer.observe()
        receipt = self._base_receipt()
        receipt["observation"] = {
            **asdict(observation),
            "state": observation.state.value,
        }

        if observation.state is ObservationState.HEALTHY:
            receipt.update(
                {
                    "state": RecoveryRunState.NO_CHANGE.value,
                    "reason": "independent observer reports target healthy; no recovery requested",
                    "simulated_actuation": None,
                    "post_recovery_verification": None,
                }
            )
            return receipt

        if observation.state is ObservationState.AMBIGUOUS:
            receipt.update(
                {
                    "state": RecoveryRunState.WAITING.value,
                    "reason": "failure evidence is ambiguous; fail closed without actuation",
                    "simulated_actuation": None,
                    "post_recovery_verification": None,
                }
            )
            return receipt

        if not observation.automatic_detection or not observation.evidence_refs:
            receipt.update(
                {
                    "state": RecoveryRunState.REFUSED.value,
                    "reason": "failed state lacks automatic evidence-backed detection",
                    "simulated_actuation": None,
                    "post_recovery_verification": None,
                }
            )
            return receipt

        actuation = self.actuator.recover(expected_target=self.expected_target, expected_lkg=self.expected_lkg)
        receipt["simulated_actuation"] = asdict(actuation)
        if not (
            actuation.requested
            and actuation.completed
            and actuation.power_control_exercised
            and actuation.lkg_recovery_exercised
            and actuation.evidence_refs
        ):
            receipt.update(
                {
                    "state": RecoveryRunState.SIMULATED_UNVERIFIED.value,
                    "reason": "simulated independent power/LKG recovery did not complete with evidence",
                    "post_recovery_verification": None,
                }
            )
            return receipt

        recovered = self.verifier.verify()
        exact_target = self.expected_target.exact_match(recovered.target)
        exact_lkg = self.expected_lkg.exact_match(recovered.lkg)
        healthy = bool(recovered.healthy and recovered.evidence_refs)
        receipt["post_recovery_verification"] = {
            "observed_target": asdict(recovered.target),
            "observed_lkg": asdict(recovered.lkg),
            "exact_target_match": exact_target,
            "exact_lkg_match": exact_lkg,
            "healthy": healthy,
            "evidence_refs": list(recovered.evidence_refs),
        }
        if not (exact_target and exact_lkg and healthy):
            receipt.update(
                {
                    "state": RecoveryRunState.SIMULATED_UNVERIFIED.value,
                    "reason": "post-recovery target identity, LKG identity, or health did not verify exactly",
                }
            )
            return receipt

        receipt.update(
            {
                "state": RecoveryRunState.SIMULATED_VERIFIED.value,
                "reason": "simulation exercised detection, recovery, and exact verification; physical gates remain closed",
            }
        )
        return receipt
