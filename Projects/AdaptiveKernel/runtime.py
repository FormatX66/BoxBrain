"""Bounded generation-1 runtime for Adaptive Kernel proposals.

The runtime advances the generation-0 planner into a deterministic feedback
loop: rank a set of simulated realizations, propose a state on an isolated
copy, verify it, retain or discard it, and learn from the result.

It deliberately has no live kernel, driver, firmware, device, filesystem, or
privileged execution carrier. Callbacks must be pure functions; only the
realization proposer receives a mutable state copy. A later hardware carrier
must sit behind its own authority and recovery gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re
from types import MappingProxyType
from typing import Callable, Iterable, Mapping, TypeAlias

from Projects.AdaptiveKernel.adaptive_kernel import CapabilityRule, KernelPlan


KernelValue: TypeAlias = bool | int | float | str | None
KernelState: TypeAlias = Mapping[str, KernelValue]
Proposer: TypeAlias = Callable[[dict[str, KernelValue]], KernelState]
Observer: TypeAlias = Callable[[CapabilityRule, KernelState], KernelState]
Verifier: TypeAlias = Callable[[CapabilityRule, KernelState, KernelState], bool]
Invariant: TypeAlias = Callable[[KernelState], bool]


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_LEARNING_SCHEMA = "adaptive-kernel-learning-v1"
_SUCCESS_REWARD = 0.10
_FAILURE_PENALTY = 0.25


@dataclass(frozen=True)
class RealizationCandidate:
    """One bounded way to realize a selected capability rule.

    ``propose`` receives a copy of the runtime state.  Its return value is not
    installed until the verifier and invariant both accept it.
    """

    candidate_id: str
    rule_name: str
    propose: Proposer
    confidence: float = 0.50
    cost: float = 1.0
    reversible: bool = True
    compatible_when: tuple[tuple[str, KernelValue], ...] = ()

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.candidate_id):
            raise ValueError("candidate_id must be a stable auditable identifier")
        if not self.rule_name:
            raise ValueError("rule_name cannot be empty")
        if not callable(self.propose):
            raise TypeError("propose must be callable")
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if not math.isfinite(self.cost) or self.cost < 0.0:
            raise ValueError("cost must be a finite non-negative number")
        _normalize_state(dict(self.compatible_when))


@dataclass(frozen=True)
class CandidateLearning:
    rule_name: str
    confidence: float
    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    quarantined: bool = False


@dataclass(frozen=True)
class AdaptationAttempt:
    rule_name: str
    candidate_id: str | None
    status: str
    reason: str
    before_hash: str
    proposed_hash: str | None
    observed_hash: str | None
    after_hash: str
    confidence_before: float | None
    confidence_after: float | None
    rolled_back: bool = False


@dataclass(frozen=True)
class AdaptationRun:
    status: str
    final_state: KernelState
    promoted: tuple[str, ...]
    already_satisfied: tuple[str, ...]
    unresolved: tuple[str, ...]
    attempts: tuple[AdaptationAttempt, ...]


class AdaptiveKernelRuntime:
    """Deterministic simulated realization, verification, and learning loop."""

    def __init__(
        self,
        initial_state: KernelState | None = None,
        *,
        learning_snapshot: Mapping[str, object] | None = None,
        quarantine_after_failures: int = 2,
    ) -> None:
        if quarantine_after_failures < 1:
            raise ValueError("quarantine_after_failures must be at least one")
        self._state = _normalize_state(initial_state or {})
        self._quarantine_after_failures = quarantine_after_failures
        self._learning: dict[str, CandidateLearning] = {}
        if learning_snapshot is not None:
            self._restore_learning(learning_snapshot)

    @property
    def state(self) -> KernelState:
        return MappingProxyType(dict(self._state))

    def learning_for(self, candidate_id: str) -> CandidateLearning | None:
        return self._learning.get(candidate_id)

    def learning_snapshot(self) -> dict[str, object]:
        """Return a deterministic, JSON-serializable learning checkpoint."""

        candidates: dict[str, object] = {}
        for candidate_id, learned in sorted(self._learning.items()):
            candidates[candidate_id] = {
                "rule_name": learned.rule_name,
                "confidence": learned.confidence,
                "successes": learned.successes,
                "failures": learned.failures,
                "consecutive_failures": learned.consecutive_failures,
                "quarantined": learned.quarantined,
            }
        return {
            "schema": _LEARNING_SCHEMA,
            "state_hash": _digest(self._state),
            "candidates": candidates,
        }

    def release_quarantine(
        self,
        candidate_id: str,
        *,
        confidence: float | None = None,
    ) -> None:
        """Explicitly release a candidate after its evidence or implementation changes."""

        learned = self._learning.get(candidate_id)
        if learned is None:
            raise KeyError(candidate_id)
        next_confidence = learned.confidence if confidence is None else confidence
        if not math.isfinite(next_confidence) or not 0.0 <= next_confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        self._learning[candidate_id] = CandidateLearning(
            rule_name=learned.rule_name,
            confidence=next_confidence,
            successes=learned.successes,
            failures=learned.failures,
            consecutive_failures=0,
            quarantined=False,
        )

    def adapt(
        self,
        kernel_plan: KernelPlan,
        candidates: Iterable[RealizationCandidate],
        *,
        observer: Observer | None = None,
        verifier: Verifier | None = None,
        invariant: Invariant | None = None,
        max_candidates_per_rule: int = 8,
    ) -> AdaptationRun:
        """Attempt selected low-risk rules and return complete audit evidence.

        Independent rules may make progress even when another rule is blocked or
        fails.  Failed proposed states are discarded before they can become the
        runtime state.  Non-reversible and non-low-risk work is refused.
        """

        if max_candidates_per_rule < 1:
            raise ValueError("max_candidates_per_rule must be at least one")
        candidate_list = tuple(candidates)
        self._validate_candidate_identities(candidate_list)
        by_rule: dict[str, list[RealizationCandidate]] = {}
        for candidate in candidate_list:
            by_rule.setdefault(candidate.rule_name, []).append(candidate)

        observe = observer or _identity_observer
        check = verifier or _default_verifier
        attempts: list[AdaptationAttempt] = []
        promoted: list[str] = []
        already_satisfied: list[str] = []
        unresolved: list[str] = []

        for selected in kernel_plan.selected:
            rule = selected.rule
            if rule.risk != "low":
                attempts.append(self._skipped_attempt(rule.name, "refused", "risk_gate"))
                unresolved.append(rule.name)
                continue

            eligible: list[RealizationCandidate] = []
            for candidate in by_rule.get(rule.name, ()):
                learned = self._learning_for(candidate)
                if learned.quarantined:
                    attempts.append(
                        self._skipped_attempt(
                            rule.name,
                            "refused",
                            "candidate_quarantined",
                            candidate,
                            learned,
                        )
                    )
                elif not candidate.reversible:
                    attempts.append(
                        self._skipped_attempt(
                            rule.name,
                            "refused",
                            "automatic_runtime_requires_reversible_candidate",
                            candidate,
                            learned,
                        )
                    )
                elif not _is_compatible(candidate, self._state):
                    attempts.append(
                        self._skipped_attempt(
                            rule.name,
                            "blocked",
                            "incompatible_state",
                            candidate,
                            learned,
                        )
                    )
                else:
                    eligible.append(candidate)

            if not by_rule.get(rule.name):
                attempts.append(self._skipped_attempt(rule.name, "blocked", "no_candidate"))

            eligible.sort(key=self._rank_key)
            resolved = False
            for candidate in eligible[:max_candidates_per_rule]:
                attempt = self._attempt(rule, candidate, observe, check, invariant)
                attempts.append(attempt)
                if attempt.status == "success":
                    promoted.append(rule.name)
                    resolved = True
                    break
                if attempt.status == "no_change":
                    already_satisfied.append(rule.name)
                    resolved = True
                    break

            if not resolved:
                for candidate in eligible[max_candidates_per_rule:]:
                    attempts.append(
                        self._skipped_attempt(
                            rule.name,
                            "blocked",
                            "bounded_attempt_limit",
                            candidate,
                            self._learning_for(candidate),
                        )
                    )

            if not resolved:
                unresolved.append(rule.name)

        status = _run_status(promoted, already_satisfied, unresolved, attempts)
        return AdaptationRun(
            status=status,
            final_state=MappingProxyType(dict(self._state)),
            promoted=tuple(promoted),
            already_satisfied=tuple(already_satisfied),
            unresolved=tuple(unresolved),
            attempts=tuple(attempts),
        )

    def _attempt(
        self,
        rule: CapabilityRule,
        candidate: RealizationCandidate,
        observer: Observer,
        verifier: Verifier,
        invariant: Invariant | None,
    ) -> AdaptationAttempt:
        before = dict(self._state)
        before_hash = _digest(before)
        learned_before = self._learning_for(candidate)
        proposed: dict[str, KernelValue] | None = None
        proposed_hash: str | None = None
        observed: dict[str, KernelValue] | None = None
        observed_hash: str | None = None

        try:
            proposed = _normalize_state(candidate.propose(dict(before)))
            proposed_hash = _digest(proposed)
        except Exception as exc:
            reason = f"proposal_exception:{type(exc).__name__}"
        else:
            proposed_view = MappingProxyType(dict(proposed))
            try:
                proposed_invariants_hold = invariant is None or bool(
                    invariant(proposed_view)
                )
            except Exception as exc:
                reason = f"invariant_exception:{type(exc).__name__}"
            else:
                if not proposed_invariants_hold:
                    reason = "invariant_violation"
                else:
                    try:
                        observed = _normalize_state(observer(rule, proposed_view))
                        observed_hash = _digest(observed)
                    except Exception as exc:
                        reason = f"observation_exception:{type(exc).__name__}"
                    else:
                        observed_view = MappingProxyType(dict(observed))
                        try:
                            observed_invariants_hold = invariant is None or bool(
                                invariant(observed_view)
                            )
                        except Exception as exc:
                            reason = f"invariant_exception:{type(exc).__name__}"
                        else:
                            if not observed_invariants_hold:
                                reason = "observed_invariant_violation"
                            else:
                                try:
                                    verified = bool(
                                        verifier(rule, proposed_view, observed_view)
                                    )
                                except Exception as exc:
                                    reason = (
                                        f"verification_exception:{type(exc).__name__}"
                                    )
                                else:
                                    if verified:
                                        if observed == before:
                                            return AdaptationAttempt(
                                                rule_name=rule.name,
                                                candidate_id=candidate.candidate_id,
                                                status="no_change",
                                                reason="already_satisfied",
                                                before_hash=before_hash,
                                                proposed_hash=proposed_hash,
                                                observed_hash=observed_hash,
                                                after_hash=before_hash,
                                                confidence_before=(
                                                    learned_before.confidence
                                                ),
                                                confidence_after=(
                                                    learned_before.confidence
                                                ),
                                            )
                                        self._state = observed
                                        learned_after = self._record_success(candidate)
                                        return AdaptationAttempt(
                                            rule_name=rule.name,
                                            candidate_id=candidate.candidate_id,
                                            status="success",
                                            reason="verified",
                                            before_hash=before_hash,
                                            proposed_hash=proposed_hash,
                                            observed_hash=observed_hash,
                                            after_hash=_digest(self._state),
                                            confidence_before=learned_before.confidence,
                                            confidence_after=learned_after.confidence,
                                        )
                                    reason = "verification_mismatch"

        learned_after = self._record_failure(candidate)
        return AdaptationAttempt(
            rule_name=rule.name,
            candidate_id=candidate.candidate_id,
            status="failed",
            reason=reason,
            before_hash=before_hash,
            proposed_hash=proposed_hash,
            observed_hash=observed_hash,
            after_hash=_digest(self._state),
            confidence_before=learned_before.confidence,
            confidence_after=learned_after.confidence,
            rolled_back=(
                (proposed is not None and proposed != before)
                or (observed is not None and observed != before)
            ),
        )

    def _rank_key(self, candidate: RealizationCandidate) -> tuple[float, float, str]:
        learned = self._learning_for(candidate)
        return (-learned.confidence, candidate.cost, candidate.candidate_id)

    def _learning_for(self, candidate: RealizationCandidate) -> CandidateLearning:
        learned = self._learning.get(candidate.candidate_id)
        if learned is None:
            learned = CandidateLearning(candidate.rule_name, candidate.confidence)
            self._learning[candidate.candidate_id] = learned
        return learned

    def _record_success(self, candidate: RealizationCandidate) -> CandidateLearning:
        current = self._learning_for(candidate)
        updated = CandidateLearning(
            rule_name=current.rule_name,
            confidence=min(1.0, current.confidence + _SUCCESS_REWARD),
            successes=current.successes + 1,
            failures=current.failures,
            consecutive_failures=0,
            quarantined=False,
        )
        self._learning[candidate.candidate_id] = updated
        return updated

    def _record_failure(self, candidate: RealizationCandidate) -> CandidateLearning:
        current = self._learning_for(candidate)
        consecutive_failures = current.consecutive_failures + 1
        updated = CandidateLearning(
            rule_name=current.rule_name,
            confidence=max(0.0, current.confidence - _FAILURE_PENALTY),
            successes=current.successes,
            failures=current.failures + 1,
            consecutive_failures=consecutive_failures,
            quarantined=consecutive_failures >= self._quarantine_after_failures,
        )
        self._learning[candidate.candidate_id] = updated
        return updated

    def _skipped_attempt(
        self,
        rule_name: str,
        status: str,
        reason: str,
        candidate: RealizationCandidate | None = None,
        learned: CandidateLearning | None = None,
    ) -> AdaptationAttempt:
        state_hash = _digest(self._state)
        confidence = learned.confidence if learned is not None else None
        return AdaptationAttempt(
            rule_name=rule_name,
            candidate_id=candidate.candidate_id if candidate is not None else None,
            status=status,
            reason=reason,
            before_hash=state_hash,
            proposed_hash=None,
            observed_hash=None,
            after_hash=state_hash,
            confidence_before=confidence,
            confidence_after=confidence,
        )

    def _validate_candidate_identities(
        self,
        candidates: tuple[RealizationCandidate, ...],
    ) -> None:
        seen: dict[str, str] = {}
        for candidate in candidates:
            prior_rule = seen.get(candidate.candidate_id)
            if prior_rule is not None:
                raise ValueError(f"duplicate candidate_id: {candidate.candidate_id}")
            seen[candidate.candidate_id] = candidate.rule_name
            learned = self._learning.get(candidate.candidate_id)
            if learned is not None and learned.rule_name != candidate.rule_name:
                raise ValueError(
                    f"candidate_id {candidate.candidate_id!r} changed rule identity"
                )

    def _restore_learning(self, snapshot: Mapping[str, object]) -> None:
        if snapshot.get("schema") != _LEARNING_SCHEMA:
            raise ValueError("unsupported adaptive-kernel learning schema")
        candidates = snapshot.get("candidates")
        if not isinstance(candidates, Mapping):
            raise ValueError("learning snapshot candidates must be a mapping")
        for candidate_id, payload in candidates.items():
            if not isinstance(candidate_id, str) or not _IDENTIFIER.fullmatch(candidate_id):
                raise ValueError("learning snapshot contains an invalid candidate_id")
            if not isinstance(payload, Mapping):
                raise ValueError("candidate learning entry must be a mapping")
            rule_name = payload.get("rule_name")
            confidence = payload.get("confidence")
            successes = payload.get("successes", 0)
            failures = payload.get("failures", 0)
            consecutive_failures = payload.get("consecutive_failures", 0)
            quarantined = payload.get("quarantined", False)
            if not isinstance(rule_name, str) or not rule_name:
                raise ValueError("candidate learning rule_name is invalid")
            if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
                raise ValueError("candidate learning confidence is invalid")
            if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                raise ValueError("candidate learning confidence is invalid")
            counters = (successes, failures, consecutive_failures)
            if any(
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
                for value in counters
            ):
                raise ValueError("candidate learning counter is invalid")
            if not isinstance(quarantined, bool):
                raise ValueError("candidate learning quarantine flag is invalid")
            self._learning[candidate_id] = CandidateLearning(
                rule_name=rule_name,
                confidence=float(confidence),
                successes=successes,
                failures=failures,
                consecutive_failures=consecutive_failures,
                quarantined=quarantined,
            )


def _identity_observer(rule: CapabilityRule, proposed: KernelState) -> KernelState:
    del rule
    return dict(proposed)


def _default_verifier(
    rule: CapabilityRule,
    proposed: KernelState,
    observed: KernelState,
) -> bool:
    return proposed == observed and bool(rule.provides) and all(
        observed.get(f"kernel.capability.{capability}") is True
        for capability in rule.provides
    )


def _is_compatible(candidate: RealizationCandidate, state: KernelState) -> bool:
    return all(state.get(key) == expected for key, expected in candidate.compatible_when)


def _normalize_state(state: KernelState) -> dict[str, KernelValue]:
    if not isinstance(state, Mapping):
        raise TypeError("kernel state must be a mapping")
    normalized: dict[str, KernelValue] = {}
    for key, value in state.items():
        if not isinstance(key, str) or not key:
            raise ValueError("kernel state keys must be non-empty strings")
        if not isinstance(value, (bool, int, float, str, type(None))):
            raise TypeError(f"unsupported kernel state value for {key!r}")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"kernel state value for {key!r} must be finite")
        normalized[key] = value
    return normalized


def _digest(state: KernelState) -> str:
    payload = json.dumps(
        _normalize_state(state),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _run_status(
    promoted: list[str],
    already_satisfied: list[str],
    unresolved: list[str],
    attempts: list[AdaptationAttempt],
) -> str:
    if not unresolved:
        return "success" if promoted else "no_change"
    unresolved_rules = set(unresolved)
    relevant = [attempt for attempt in attempts if attempt.rule_name in unresolved_rules]
    if any(attempt.status == "failed" for attempt in relevant):
        return "failed"
    if any(attempt.status == "refused" for attempt in relevant):
        return "refused"
    return "blocked"
