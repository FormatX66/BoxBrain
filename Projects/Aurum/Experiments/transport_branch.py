"""Future Branch transport selection for Aurum mesh and recovery paths.

This module ranks safe-to-prepare transport futures from fresh reachability,
identity, capability, reliability, and cost evidence.  It intentionally does not
connect to anything, broaden trust, reinterpret target identity, or grant network
or destructive authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class TransportKind(str, Enum):
    USB = "usb"
    ETHERNET = "ethernet"
    WIFI = "wifi"
    BLUETOOTH = "bluetooth"
    PEER_RELAY = "peer-relay"
    OFFLINE_QUEUE = "offline-queue"
    WAIT = "wait"


class TransportDisposition(str, Enum):
    WARM = "warm"
    PREPARE = "prepare"
    HOLD = "hold"
    QUARANTINE = "quarantine"
    WAIT = "wait"


@dataclass(frozen=True)
class TransportCandidate:
    name: str
    kind: TransportKind
    available: bool
    reachable: bool
    identity_verified: bool
    capability_fit: float
    reliability: float
    freshness: float
    human_time_saved: float
    latency_cost: float
    compute_cost: float = 0.0
    network_cost: float = 0.0
    privacy_cost: float = 0.0
    trust_broadening_required: bool = False
    target_identity_changed: bool = False
    stable_failed_attempts: int = 0

    def validate(self) -> None:
        if not self.name:
            raise ValueError("transport name required")
        for label, value in (
            ("capability_fit", self.capability_fit),
            ("reliability", self.reliability),
            ("freshness", self.freshness),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{label} must be between 0 and 1")
        for label, value in (
            ("human_time_saved", self.human_time_saved),
            ("latency_cost", self.latency_cost),
            ("compute_cost", self.compute_cost),
            ("network_cost", self.network_cost),
            ("privacy_cost", self.privacy_cost),
        ):
            if value < 0:
                raise ValueError(f"{label} must be non-negative")
        if self.stable_failed_attempts < 0:
            raise ValueError("stable_failed_attempts must be non-negative")


def transport_score(candidate: TransportCandidate) -> float:
    """Expected useful value per cost without allowing trust expansion."""
    candidate.validate()
    if not candidate.available:
        return float("-inf")
    if candidate.trust_broadening_required or candidate.target_identity_changed:
        return float("-inf")

    # Offline queue and wait remain legitimate low-cost futures when a live route
    # is unavailable. They do not pretend to be reachable network transports.
    if candidate.kind in (TransportKind.OFFLINE_QUEUE, TransportKind.WAIT):
        route_factor = 0.35
    else:
        route_factor = 1.0 if candidate.reachable and candidate.identity_verified else 0.05

    retry_discount = 1.0 / (1.0 + 0.9 * candidate.stable_failed_attempts)
    benefit = (
        route_factor
        * candidate.capability_fit
        * candidate.reliability
        * (0.4 + 0.6 * candidate.freshness)
        * (1.0 + candidate.human_time_saved)
        * retry_discount
    )
    cost = 0.05 + candidate.latency_cost + candidate.compute_cost + candidate.network_cost + candidate.privacy_cost
    return benefit / cost


def rank_transports(
    candidates: Iterable[TransportCandidate],
    *,
    limit: int = 7,
) -> list[dict]:
    """Rank live routes and safe fallbacks while failing closed on trust/identity."""
    if limit < 1:
        raise ValueError("limit must be positive")
    values = list(candidates)
    for candidate in values:
        candidate.validate()

    ordered = sorted(values, key=lambda item: (-transport_score(item), item.name))
    output: list[dict] = []
    for item in ordered[:limit]:
        score = transport_score(item)
        if item.trust_broadening_required:
            disposition = TransportDisposition.QUARANTINE
            reason = "trust-broadening-required"
        elif item.target_identity_changed:
            disposition = TransportDisposition.QUARANTINE
            reason = "target-identity-changed"
        elif not item.available:
            disposition = TransportDisposition.WAIT
            reason = "unavailable"
        elif item.kind == TransportKind.WAIT:
            disposition = TransportDisposition.WAIT
            reason = "wait-for-fresher-evidence"
        elif item.kind == TransportKind.OFFLINE_QUEUE:
            disposition = TransportDisposition.WARM
            reason = "safe-offline-fallback"
        elif not item.identity_verified:
            disposition = TransportDisposition.HOLD
            reason = "identity-unverified"
        elif not item.reachable:
            disposition = TransportDisposition.WARM
            reason = "known-route-not-currently-reachable"
        elif item.stable_failed_attempts >= 3:
            disposition = TransportDisposition.QUARANTINE
            reason = "stable-failed-route"
        else:
            disposition = TransportDisposition.PREPARE
            reason = "verified-reachable-route"

        output.append(
            {
                "name": item.name,
                "kind": item.kind.value,
                "score": None if score == float("-inf") else round(score, 6),
                "disposition": disposition.value,
                "reason": reason,
                "reachable": item.reachable,
                "identity_verified": item.identity_verified,
                "freshness": item.freshness,
            }
        )
    return output


def transport_plan(candidates: Iterable[TransportCandidate], *, limit: int = 7) -> dict:
    ranked = rank_transports(candidates, limit=limit)
    return {
        "schema": "aurum-future-branch-transport-plan-v1",
        "transports": ranked,
        "prepared_transport": next(
            (item["name"] for item in ranked if item["disposition"] == TransportDisposition.PREPARE.value),
            None,
        ),
        "warm_fallbacks": [
            item["name"]
            for item in ranked
            if item["disposition"] in (TransportDisposition.WARM.value, TransportDisposition.WAIT.value)
        ],
        "connection_authority": False,
        "identity_trust_broadening_allowed": False,
        "target_identity_reinterpretation_allowed": False,
        "external_action_allowed": False,
    }
