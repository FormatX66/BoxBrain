from __future__ import annotations

from typing import Iterable


def subtract_protected_tokens(
    candidate: Iterable[str],
    *protected_groups: Iterable[str],
) -> tuple[str, ...]:
    """Return canonical candidate tokens not present in any protected group.

    This is a pure constraint projection. It cannot add protected tokens, mutate a
    shell, or grant authority.
    """
    allowed = {str(item) for item in candidate if str(item)}
    protected: set[str] = set()
    for group in protected_groups:
        protected.update(str(item) for item in group if str(item))
    return tuple(sorted(allowed - protected))


__all__ = ["subtract_protected_tokens"]
