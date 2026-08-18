from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from Projects.Codelation.state_space import (
    Constraint,
    ConvergenceStage,
    FiniteStateSolver,
    State,
    Variable,
)


@dataclass(frozen=True)
class FailureRecovery:
    failure: str
    stage: str
    detection: tuple[str, ...]
    actions: tuple[str, ...]
    converges_to: str
    requires_operator_in_test_world: bool = False
    physical_only: bool = False


# These are deliberately bounded machine variables.  They are not intended to be a
# taxonomy of every PC ever made; they are the dimensions that can change the current
# Aurum PC seed's boot outcome.  New physical evidence extends a domain or adds a new
# variable instead of turning into an ad-hoc human troubleshooting procedure.
BOOT_VARIABLES = (
    Variable("firmware", ("uefi", "bios")),
    Variable("media_layout", ("gpt", "mbr", "superfloppy")),
    Variable("boot_filesystem", ("fat", "iso9660", "ext")),
    Variable("loader", ("direct_efi", "grub_efi", "syslinux_bios")),
    Variable("payload_strategy", ("same_device_signature", "embedded_rescue", "partition_scan")),
    Variable("storage_transport", ("usb_msd", "usb_uasp", "nvme", "sata")),
    Variable("root_strategy", ("label_signature", "uuid", "probe_all")),
    Variable("display", ("efi_gop", "vesa", "serial")),
    Variable("network", ("wired_link", "wired_no_carrier", "wifi", "none")),
)


BOOT_CONSTRAINTS = (
    Constraint(
        "uefi-cannot-use-bios-loader",
        lambda state: not (state["firmware"] == "uefi" and state["loader"] == "syslinux_bios"),
        "UEFI entry must use an EFI-capable path in the current seed model.",
    ),
    Constraint(
        "bios-cannot-use-efi-loader",
        lambda state: not (state["firmware"] == "bios" and state["loader"] != "syslinux_bios"),
        "Legacy BIOS cannot directly execute the modeled EFI loaders.",
    ),
    Constraint(
        "direct-efi-needs-fat",
        lambda state: not (state["loader"] == "direct_efi" and state["boot_filesystem"] != "fat"),
        "The direct removable-media EFI path is modeled on a FAT EFI system filesystem.",
    ),
    Constraint(
        "syslinux-seed-fs",
        lambda state: not (
            state["loader"] == "syslinux_bios" and state["boot_filesystem"] not in {"fat", "iso9660"}
        ),
        "The current BIOS seed uses Syslinux on FAT/ISO media rather than an extlinux path.",
    ),
)


# Each stage intentionally forgets distinctions that no longer affect later behavior.
# That is the convergence principle: many early paths, progressively fewer meaningful
# states, one local Aurum runtime invariant.
BOOT_CONVERGENCE = (
    ConvergenceStage(
        "bootloader-owned",
        lambda state: (
            state["firmware"],
            state["loader"],
            state["payload_strategy"],
            state["storage_transport"],
            state["root_strategy"],
            state["display"],
            state["network"],
        ),
    ),
    ConvergenceStage(
        "payload-verified",
        lambda state: (
            state["payload_strategy"],
            state["storage_transport"],
            state["root_strategy"],
            state["display"],
            state["network"],
        ),
    ),
    ConvergenceStage(
        "kernel-running",
        lambda state: (
            state["root_strategy"],
            state["display"],
            state["network"],
        ),
    ),
    ConvergenceStage(
        "aurum-local",
        lambda state: (state["display"], state["network"]),
    ),
    ConvergenceStage(
        "network-classified",
        lambda state: (state["network"],),
    ),
    ConvergenceStage("aurum-runtime-ready", lambda state: ("aurum-runtime-ready",)),
)


FAILURE_RECOVERIES = (
    FailureRecovery(
        failure="grub-shell-config-unreadable",
        stage="bootloader",
        detection=("grub-command-shell", "boot-config-not-auto-loaded", "boot-media-visible-or-unknown"),
        actions=(
            "validate-efi-image-self-location",
            "embed-rescue-config",
            "embed-partition-and-filesystem-modules",
            "scan-boot-device-by-signature",
            "verify-kernel-and-initrd-before-release",
            "emit-machine-readable-evidence",
        ),
        converges_to="payload-verified",
    ),
    FailureRecovery(
        failure="boot-filesystem-unreadable",
        stage="bootloader",
        detection=("loader-ran", "filesystem-probe-failed"),
        actions=(
            "load-or-embed-required-filesystem-driver",
            "scan-supported-media-layouts",
            "try-embedded-rescue-payload",
            "record-rejected-layout-signatures",
        ),
        converges_to="payload-verified",
    ),
    FailureRecovery(
        failure="kernel-image-invalid",
        stage="payload",
        detection=("payload-found", "checksum-or-format-invalid"),
        actions=(
            "reject-generation",
            "select-known-good-payload",
            "rebuild-and-reverify-candidate",
        ),
        converges_to="kernel-verified",
    ),
    FailureRecovery(
        failure="kernel-start-failure",
        stage="kernel",
        detection=("kernel-handoff-attempted", "early-kernel-progress-missing"),
        actions=(
            "capture-serial-early-boot-evidence",
            "retry-conservative-cpu-acpi-profile",
            "retry-known-good-kernel-generation",
        ),
        converges_to="kernel-running",
    ),
    FailureRecovery(
        failure="root-unresolved",
        stage="early-userspace",
        detection=("kernel-running", "root-not-mounted"),
        actions=(
            "resolve-by-aurum-signature",
            "resolve-by-uuid",
            "probe-supported-storage-transports",
            "start-embedded-rescue-userspace",
        ),
        converges_to="root-mounted",
    ),
    FailureRecovery(
        failure="display-unavailable",
        stage="local-runtime",
        detection=("runtime-alive", "primary-display-missing"),
        actions=(
            "fall-back-to-generic-framebuffer",
            "fall-back-to-serial-evidence-channel",
            "continue-headless-runtime",
        ),
        converges_to="aurum-local",
    ),
    FailureRecovery(
        failure="input-unavailable",
        stage="local-runtime",
        detection=("runtime-alive", "hid-path-missing"),
        actions=(
            "probe-generic-usb-hid",
            "probe-legacy-input-path",
            "continue-autonomous-headless-runtime",
        ),
        converges_to="aurum-local",
    ),
    FailureRecovery(
        failure="network-unavailable",
        stage="network",
        detection=("runtime-alive", "no-usable-link"),
        actions=(
            "classify-no-carrier-vs-missing-interface",
            "probe-bundled-network-drivers",
            "continue-local-first-offline",
            "queue-network-recovery-after-local-readiness",
        ),
        converges_to="aurum-runtime-ready-offline",
    ),
    FailureRecovery(
        failure="runtime-service-failure",
        stage="aurum-runtime",
        detection=("userspace-running", "aurum-service-not-ready"),
        actions=(
            "validate-local-dependency-graph",
            "restart-bounded-service",
            "select-known-good-runtime-generation",
            "preserve-failed-generation-for-analysis",
        ),
        converges_to="aurum-runtime-ready",
    ),
    FailureRecovery(
        failure="self-build-failure",
        stage="self-build",
        detection=("self-build-started", "candidate-gate-failed"),
        actions=(
            "preserve-failed-candidate",
            "fork-safe-and-adventurous-hypotheses",
            "keep-known-good-generation-running",
            "retest-convergent-invariants",
        ),
        converges_to="known-good-generation-running",
    ),
    FailureRecovery(
        failure="unmodeled-physical-observation",
        stage="physical-boundary",
        detection=("real-machine-result-not-predicted-by-current-model",),
        actions=(
            "record-observation",
            "derive-minimal-new-variable-or-domain-value",
            "fork-hypothesis-branch",
            "replay-virtual-state-space-with-new-evidence",
        ),
        converges_to="observation-ingested",
        physical_only=True,
    ),
)


PC01_BOOT_OBSERVATION = {
    "observation": "grub-shell-config-unreadable",
    "proven": (
        "firmware-executed-usb-boot-path",
        "grub-executed",
        "physical-disks-were-enumerated",
    ),
    "not_yet_proven": (
        "boot-config-self-location",
        "boot-filesystem-readability",
        "payload-handoff",
    ),
}


def boot_solver() -> FiniteStateSolver:
    return FiniteStateSolver(BOOT_VARIABLES, BOOT_CONSTRAINTS, BOOT_CONVERGENCE)


def recovery_for(failure: str) -> FailureRecovery:
    for recovery in FAILURE_RECOVERIES:
        if recovery.failure == failure:
            return recovery
    raise KeyError(failure)


def all_test_world_recoveries_are_autonomous() -> bool:
    return all(not recovery.requires_operator_in_test_world for recovery in FAILURE_RECOVERIES)


def report() -> dict[str, object]:
    solved = boot_solver().solve().as_dict()
    solved.update(
        {
            "model": "aurum-pc-boot-state-v1",
            "pc01_observation": PC01_BOOT_OBSERVATION,
            "failure_classes": len(FAILURE_RECOVERIES),
            "test_world_operator_steps": sum(
                1 for recovery in FAILURE_RECOVERIES if recovery.requires_operator_in_test_world
            ),
            "physical_boundary": "new evidence extends the model, then the bounded sweep replays",
        }
    )
    return solved


def main() -> int:
    print(json.dumps(report(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
