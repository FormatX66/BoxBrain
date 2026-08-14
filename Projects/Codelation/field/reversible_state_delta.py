from __future__ import annotations

from typing import Iterable


def project_reversible_set_delta(
    current: Iterable[str],
    target: Iterable[str],
    *,
    evidence: str = "",
    empty_value: str = "none",
) -> str:
    """Project a reversible set delta without applying it.

    The result is deterministic proposal text only. It has no authority to mutate
    current state and preserves the supplied evidence verbatim as part of the view.
    """
    current_set = {str(item) for item in current if str(item)}
    target_set = {str(item) for item in target if str(item)}
    added = " ".join(sorted(target_set - current_set)) or empty_value
    removed = " ".join(sorted(current_set - target_set)) or empty_value
    evidence_text = str(evidence) or empty_value
    return f"add={added};remove={removed};evidence={evidence_text}"


__all__ = ["project_reversible_set_delta"]
