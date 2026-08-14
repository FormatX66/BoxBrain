from __future__ import annotations

from typing import Iterable, Mapping


def _reason_label(name: str) -> str:
    normalized = name
    if normalized.endswith("_present"):
        normalized = normalized[: -len("_present")]
    return normalized.replace("_", "-")


def classify_required_conditions(
    values: Mapping[str, object],
    *,
    order: Iterable[str] | None = None,
    positive: str = "yes",
    success: str = "ready",
    blocked_prefix: str = "blocked-",
) -> str:
    """Classify ordered required conditions and preserve the first failure reason.

    This is deterministic classification only. It does not grant authority or perform
    the operation whose readiness is being classified.
    """
    names = tuple(order) if order is not None else tuple(sorted(str(key) for key in values))
    for name in names:
        if name not in values:
            raise ValueError(f"condition missing: {name}")
        if str(values[name]).casefold() != positive.casefold():
            return f"{blocked_prefix}{_reason_label(name)}"
    return success


__all__ = ["classify_required_conditions"]
