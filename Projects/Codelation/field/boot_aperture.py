from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

from aurum_field import Field

BOOT_APERTURE_SCHEMA = "aurum.boot.aperture.v0"


@dataclass(frozen=True)
class BootMechanism:
    name: str
    carrier: str
    requires: frozenset[str]
    provides: frozenset[str]
    persistent_media_required: bool


@dataclass(frozen=True)
class BootAperturePlan:
    target_identity: str
    mechanism: str
    carrier: str
    requirements: tuple[str, ...]
    projection_only: bool
    persistent_media_required: bool
    identity: str


def default_boot_mechanisms() -> tuple[BootMechanism, ...]:
    return (
        BootMechanism(
            "pi3-network",
            "ethernet-boot",
            frozenset({"pi3-rom-network-boot", "authorized-lan"}),
            frozenset({"bootstrap-bytes"}),
            False,
        ),
        BootMechanism(
            "pxe",
            "pxe-network",
            frozenset({"pxe-client", "authorized-lan"}),
            frozenset({"bootstrap-bytes"}),
            False,
        ),
        BootMechanism(
            "uefi-http",
            "uefi-http",
            frozenset({"uefi-http-client", "authorized-network"}),
            frozenset({"bootstrap-bytes"}),
            False,
        ),
        BootMechanism(
            "uefi-removable",
            "uefi-removable-media",
            frozenset({"uefi", "authorized-removable-media"}),
            frozenset({"bootstrap-bytes"}),
            True,
        ),
        BootMechanism(
            "pi3-fat-shim",
            "fat-compatible-pi-boot",
            frozenset({"pi3-fat-boot", "authorized-removable-media"}),
            frozenset({"bootstrap-bytes"}),
            True,
        ),
    )


def choose_boot_aperture(
    target_identity: str,
    observed: Iterable[str],
    *,
    mechanisms: tuple[BootMechanism, ...] | None = None,
) -> BootAperturePlan:
    if not target_identity:
        raise ValueError("target identity is required")
    available = frozenset(observed)
    candidates = [
        mechanism
        for mechanism in (mechanisms or default_boot_mechanisms())
        if mechanism.requires <= available
    ]
    if not candidates:
        raise ValueError("no verified boot aperture is currently available")
    selected = sorted(
        candidates,
        key=lambda item: (
            item.persistent_media_required,
            len(item.requires),
            item.name,
        ),
    )[0]
    payload = {
        "schema": BOOT_APERTURE_SCHEMA,
        "target_identity": target_identity,
        "mechanism": selected.name,
        "carrier": selected.carrier,
        "requirements": sorted(selected.requires),
        "projection_only": True,
        "persistent_media_required": selected.persistent_media_required,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    identity = hashlib.blake2s(b"AURUM-BOOT-APERTURE-0\x00" + raw, digest_size=32).hexdigest()
    return BootAperturePlan(
        target_identity=target_identity,
        mechanism=selected.name,
        carrier=selected.carrier,
        requirements=tuple(sorted(selected.requires)),
        projection_only=True,
        persistent_media_required=selected.persistent_media_required,
        identity=identity,
    )


def boot_aperture_field(plan: BootAperturePlan) -> Field:
    field = Field()
    aperture = field.add(
        "capability",
        {
            "schema": BOOT_APERTURE_SCHEMA,
            "identity": plan.identity,
            "target_identity": plan.target_identity,
            "mechanism": plan.mechanism,
            "carrier": plan.carrier,
            "requirements": list(plan.requirements),
            "projection_only": plan.projection_only,
            "persistent_media_required": plan.persistent_media_required,
            "semantic_owner": "aurum",
            "compatibility_carrier_is_not_os_owner": True,
        },
    )
    field.add(
        "view",
        {
            "name": "aurum-boot-aperture",
            "aperture": aperture,
        },
    )
    return field


__all__ = [
    "BOOT_APERTURE_SCHEMA",
    "BootAperturePlan",
    "BootMechanism",
    "boot_aperture_field",
    "choose_boot_aperture",
    "default_boot_mechanisms",
]
