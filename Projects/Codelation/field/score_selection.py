from __future__ import annotations

from typing import Mapping


def _label(name: str) -> str:
    return name.replace("_", "-")


def select_thresholded_unique_max(
    scores: Mapping[str, object],
    *,
    threshold: float,
    fallback: str = "general",
) -> str:
    """Choose one unique highest score above threshold, else a stable fallback.

    This is recommendation-only arithmetic. It does not apply the selected mode or
    grant any resource/interface authority.
    """
    if not scores:
        return fallback
    numeric: dict[str, float] = {}
    for name, value in scores.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"score must be numeric: {name}")
        numeric[str(name)] = float(value)
    best = max(numeric.values())
    if best < float(threshold):
        return fallback
    winners = [name for name, value in numeric.items() if value == best]
    if len(winners) != 1:
        return fallback
    return _label(winners[0])


__all__ = ["select_thresholded_unique_max"]
