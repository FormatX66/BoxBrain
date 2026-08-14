from __future__ import annotations

from typing import Iterable


def project_preference_evidence(
    accepted: Iterable[str],
    reverted: Iterable[str],
    pinned: Iterable[str],
    ignored: Iterable[str],
    disabled: Iterable[str],
    *,
    empty_value: str = "none",
) -> str:
    """Project explicit interaction outcomes into bounded local preference evidence.

    This function is deterministic and local-only. It does not infer sensitive traits,
    modify the interface, or grant any authority.
    """
    accepted_set={str(x) for x in accepted if str(x)}
    reverted_set={str(x) for x in reverted if str(x)}
    pinned_set={str(x) for x in pinned if str(x)}
    ignored_set={str(x) for x in ignored if str(x)}
    disabled_set={str(x) for x in disabled if str(x)}
    avoid=reverted_set|disabled_set
    lock=pinned_set-disabled_set
    prefer=(accepted_set|pinned_set)-avoid
    neutral=ignored_set-avoid-prefer
    def render(values:set[str])->str:
        return " ".join(sorted(values)) or empty_value
    return f"prefer={render(prefer)};avoid={render(avoid)};lock={render(lock)};neutral={render(neutral)}"


__all__=["project_preference_evidence"]
