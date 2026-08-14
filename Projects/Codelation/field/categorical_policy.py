from __future__ import annotations

from typing import Iterable, Mapping


def select_categorical_policy_tokens(
    category: str,
    available: Iterable[str],
    profiles: Mapping[str, Iterable[str]],
) -> tuple[str, ...]:
    """Select canonical available tokens allowed by one declarative category profile.

    The profile data is supplied by the caller; this helper contains no hard-coded
    activity/resource policy and performs no actuation.
    """
    available_set={str(x) for x in available if str(x)}
    selected=profiles.get(str(category))
    if selected is None:
        return ()
    desired={str(x) for x in selected if str(x)}
    return tuple(sorted(available_set & desired))


__all__=["select_categorical_policy_tokens"]
