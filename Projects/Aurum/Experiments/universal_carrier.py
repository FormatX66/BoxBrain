"""Non-production universal Aurum carrier planning experiment.

This module prepares a deterministic logical disk layout for a future physical
carrier that can expose independent x86 and Raspberry Pi boot frontends while
sharing one architecture-neutral Aurum lineage. It never writes a disk and never
promotes or mutates Last Known Good state.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Payload:
    platform: str
    artifact: str
    sha256: str
    boot_family: str

    def validate(self) -> None:
        if self.platform not in {"x86_64", "rpi_arm64"}:
            raise ValueError("unsupported experimental platform")
        if not self.artifact:
            raise ValueError("artifact required")
        if not _SHA256.fullmatch(self.sha256):
            raise ValueError("sha256 must be lowercase 64-hex")
        if not self.boot_family:
            raise ValueError("boot family required")


@dataclass(frozen=True)
class CarrierPolicy:
    boot_mb: int = 512
    seed_mb: int = 512
    state_mb: int = 1024
    payload_headroom_fraction: float = 0.20

    def validate(self) -> None:
        if min(self.boot_mb, self.seed_mb, self.state_mb) <= 0:
            raise ValueError("partition reserves must be positive")
        if not 0 <= self.payload_headroom_fraction <= 1:
            raise ValueError("payload headroom must be between 0 and 1")


def build_carrier_plan(
    *,
    lineage_id: str,
    source_commit: str,
    x86: Payload,
    pi: Payload,
    policy: CarrierPolicy | None = None,
) -> dict:
    """Return a safe, deterministic logical carrier plan.

    The payload partition is intentionally architecture-separated even though the
    physical implementation may later choose one filesystem. State is namespaced
    by node identity so one machine cannot overwrite another machine's evidence.
    """
    policy = policy or CarrierPolicy()
    policy.validate()
    if not lineage_id:
        raise ValueError("lineage_id required")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("source_commit must be immutable 40-hex git commit")
    x86.validate()
    pi.validate()
    if x86.platform != "x86_64" or pi.platform != "rpi_arm64":
        raise ValueError("x86 and pi payload roles must not be swapped")

    partitions = [
        {
            "name": "AURUM_BOOT",
            "purpose": "multi-firmware front door",
            "minimum_mb": policy.boot_mb,
            "writable_runtime_state": False,
            "entries": {
                "x86_64_uefi": "EFI/BOOT/BOOTX64.EFI",
                "rpi_arm64": "rpi/config.txt",
            },
        },
        {
            "name": "AURUM_PAYLOADS",
            "purpose": "architecture-separated phenotype payloads",
            "headroom_fraction": policy.payload_headroom_fraction,
            "payloads": {
                "x86_64": {"artifact": x86.artifact, "sha256": x86.sha256, "boot_family": x86.boot_family},
                "rpi_arm64": {"artifact": pi.artifact, "sha256": pi.sha256, "boot_family": pi.boot_family},
            },
        },
        {
            "name": "AURUM_SEED",
            "purpose": "shared immutable lineage and recovery metadata",
            "minimum_mb": policy.seed_mb,
            "lineage_id": lineage_id,
            "source_commit": source_commit,
        },
        {
            "name": "AURUM_STATE",
            "purpose": "versioned writable node state",
            "minimum_mb": policy.state_mb,
            "namespace_rule": "node-id/platform",
            "cross_node_overwrite_allowed": False,
        },
    ]

    return {
        "schema": "aurum-universal-carrier-plan-v0",
        "status": "PREPARED_NOT_PHYSICALLY_PROVEN",
        "lineage_id": lineage_id,
        "source_commit": source_commit,
        "partitions": partitions,
        "platforms": ["x86_64", "rpi_arm64"],
        "physical_write_allowed": False,
        "active_state_mutation_allowed": False,
        "lkg_mutation_allowed": False,
        "promotion_allowed": False,
        "next_required_proof": "independent physical x86 and Pi boot proof before constructing shared physical carrier",
    }
