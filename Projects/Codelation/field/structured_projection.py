from __future__ import annotations

from typing import Iterable, Mapping


def project_labeled_state(
    values: Mapping[str, object],
    *,
    order: Iterable[str] | None = None,
    empty_value: str = "none",
    separator: str = ";",
) -> str:
    """Project bounded named values into deterministic human-readable text.

    This is a view helper only. It neither mutates authoritative state nor grants
    execution authority. Empty string/None values are normalized explicitly.
    """
    names = tuple(order) if order is not None else tuple(sorted(str(key) for key in values))
    parts: list[str] = []
    for name in names:
        if name not in values:
            raise ValueError(f"projection value missing: {name}")
        raw = values[name]
        text = "" if raw is None else str(raw)
        parts.append(f"{name}={text if text else empty_value}")
    return separator.join(parts)


__all__ = ["project_labeled_state"]
