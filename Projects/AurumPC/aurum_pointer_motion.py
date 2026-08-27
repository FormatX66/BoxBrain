#!/usr/bin/env python3
"""Shared, read-only pointer-motion evidence for Hopper and Gen1 Aurum surfaces.

Opening an input path proves only that the software stack can see a pointer
source.  It is deliberately insufficient as proof that a real pointer event was
observed.  This module keeps those two facts separate so Echo Rally, the Gen1
GUI, and later surfaces can share the same fail-closed motion contract.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

SCHEMA = "aurum.pointer-motion.v1"


def _pair(value: Sequence[object] | None) -> list[int] | None:
    if value is None or len(value) != 2:
        return None
    first, second = value
    if not isinstance(first, int) or isinstance(first, bool):
        return None
    if not isinstance(second, int) or isinstance(second, bool):
        return None
    return [first, second]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class PointerMotionSnapshot:
    event_count: int = 0
    last_at: str | None = None
    last_monotonic: float | None = None
    position: list[int] | None = None
    delta: list[int] | None = None

    @property
    def observed(self) -> bool:
        return self.event_count > 0 and self.last_at is not None

    def as_dict(self, *, path_available: bool) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "path_available": bool(path_available),
            "motion_observed": self.observed,
            "event_count": self.event_count,
            "last_at": self.last_at,
            "last_monotonic": self.last_monotonic,
            "position": list(self.position) if self.position is not None else None,
            "delta": list(self.delta) if self.delta is not None else None,
            "ready": bool(path_available and self.observed),
        }


class PointerMotionTracker:
    """Thread-safe in-memory evidence collector for local pointer events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._count = 0
        self._last_at: str | None = None
        self._last_monotonic: float | None = None
        self._position: list[int] | None = None
        self._delta: list[int] | None = None

    def record(
        self,
        *,
        position: Sequence[object] | None = None,
        delta: Sequence[object] | None = None,
        observed_at: str | None = None,
        monotonic_at: float | None = None,
    ) -> PointerMotionSnapshot:
        position_pair = _pair(position)
        delta_pair = _pair(delta)
        with self._lock:
            self._count += 1
            self._last_at = observed_at or _utc_now()
            self._last_monotonic = time.monotonic() if monotonic_at is None else float(monotonic_at)
            self._position = position_pair
            self._delta = delta_pair
            return self._snapshot_unlocked()

    def snapshot(self) -> PointerMotionSnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def _snapshot_unlocked(self) -> PointerMotionSnapshot:
        return PointerMotionSnapshot(
            event_count=self._count,
            last_at=self._last_at,
            last_monotonic=self._last_monotonic,
            position=list(self._position) if self._position is not None else None,
            delta=list(self._delta) if self._delta is not None else None,
        )


def motion_evidence(
    value: PointerMotionSnapshot | Mapping[str, Any] | None,
    *,
    path_available: bool,
) -> dict[str, Any]:
    """Normalize pointer evidence while preserving path-vs-motion separation."""
    if isinstance(value, PointerMotionSnapshot):
        return value.as_dict(path_available=path_available)
    if isinstance(value, Mapping):
        count = value.get("event_count", 0)
        last_at = value.get("last_at")
        observed = bool(
            isinstance(count, int)
            and not isinstance(count, bool)
            and count > 0
            and isinstance(last_at, str)
            and bool(last_at.strip())
        )
        return {
            "schema": SCHEMA,
            "path_available": bool(path_available),
            "motion_observed": observed,
            "event_count": count if isinstance(count, int) and not isinstance(count, bool) and count >= 0 else 0,
            "last_at": last_at if isinstance(last_at, str) and last_at.strip() else None,
            "last_monotonic": value.get("last_monotonic"),
            "position": _pair(value.get("position")) if isinstance(value.get("position"), Sequence) else None,
            "delta": _pair(value.get("delta")) if isinstance(value.get("delta"), Sequence) else None,
            "ready": bool(path_available and observed),
        }
    return PointerMotionSnapshot().as_dict(path_available=path_available)
