"""Shadow-first Generation-2/3 adaptive runtime governor.

The governor consumes already-collected observations and produces deterministic
policy recommendations.  It does not read live hardware, call system tools, or
change kernel, driver, boot, network, or recovery state.

An optional executor boundary exists only as a fail-closed integration contract.
It is disabled by default and requires receipt-bound reversible authority plus
rollback metadata before an injected executor can be called.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
from typing import Any, Callable, Mapping, Sequence


SHADOW_RECEIPT_SCHEMA = "aurum-adaptive-runtime-shadow-v1"
EXECUTION_RECEIPT_SCHEMA = "aurum-adaptive-runtime-execution-v1"
ACTIVE_EXECUTION_DEFAULT = False
MAX_WINDOW_SAMPLES = 64
MAX_POLICY_CANDIDATES = 8
MAX_SPECULATIVE_CPU_PERCENT = 50
MAX_SPECULATIVE_MEMORY_PERCENT = 35
EXPECTED_AUTHORITY_SCOPE = "adaptive-runtime-policy"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STRATEGIES = {"baseline", "conserve", "balanced", "opportunistic"}


@dataclass(frozen=True)
class RuntimePolicy:
    policy_id: str
    generation: int
    strategy: str
    speculative_cpu_percent: int | None
    speculative_memory_percent: int | None
    network_prefetch: bool

    def receipt_mapping(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReversibleAuthority:
    authority_ref: str
    authorized: bool
    scope: str
    reversible: bool
    shadow_receipt_sha256: str
    rollback_target: str
    rollback_receipt_sha256: str


DEFAULT_POLICIES = (
    RuntimePolicy("runtime-baseline-v1", 0, "baseline", None, None, False),
    RuntimePolicy("runtime-gen2-conserve-v1", 2, "conserve", 10, 10, False),
    RuntimePolicy("runtime-gen2-balanced-v1", 2, "balanced", 25, 20, True),
    RuntimePolicy("runtime-gen3-opportunistic-v1", 3, "opportunistic", 40, 30, True),
)


def _audit_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return {"non_finite_float": repr(value)}
    if isinstance(value, Mapping):
        return {
            str(key): _audit_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_audit_value(item) for item in value]
    return {
        "unsupported_type": f"{type(value).__module__}.{type(value).__qualname__}"
    }


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _audit_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _seal(receipt: Mapping[str, Any]) -> dict[str, Any]:
    sealed = dict(receipt)
    sealed.pop("receipt_sha256", None)
    sealed["receipt_sha256"] = _sha256(sealed)
    return sealed


def verify_receipt(receipt: Mapping[str, Any]) -> bool:
    claimed = receipt.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    unsealed = dict(receipt)
    unsealed.pop("receipt_sha256", None)
    return claimed == _sha256(unsealed)


def _number(
    raw: Mapping[str, Any], name: str, problems: list[str], *, minimum: float
) -> float | None:
    value = raw.get(name)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < minimum
    ):
        problems.append(f"invalid-{name.replace('_', '-')}")
        return None
    return float(value)


def _integer(
    raw: Mapping[str, Any], name: str, problems: list[str], *, minimum: int
) -> int | None:
    value = raw.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        problems.append(f"invalid-{name.replace('_', '-')}")
        return None
    return value


def _carrier(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str) and value.strip() in {"0", "1"}:
        return value.strip() == "1"
    return None


def validate_runtime_sample(
    raw: Any,
    *,
    index: int,
    expected_reference_driver: str,
) -> dict[str, Any]:
    """Normalize one sample and quarantine malformed or unsafe evidence."""

    raw_sha256 = _sha256(raw)
    if not isinstance(raw, Mapping):
        return {
            "sample_id": f"sample-{index}",
            "raw_sha256": raw_sha256,
            "state": "quarantined",
            "classification": "malformed",
            "reasons": ["sample-not-a-mapping"],
        }

    problems: list[str] = []
    sample_id = raw.get("sample_id")
    if not isinstance(sample_id, str) or not _SAFE_ID.fullmatch(sample_id):
        problems.append("invalid-sample-id")
        sample_id = f"sample-{index}"

    temperature_c = _number(raw, "temperature_c", problems, minimum=-40.0)
    memory_available = _integer(
        raw, "memory_available_bytes", problems, minimum=0
    )
    memory_total = _integer(raw, "memory_total_bytes", problems, minimum=1)
    load_1m = _number(raw, "load_1m", problems, minimum=0.0)
    cpu_count = _integer(raw, "cpu_count", problems, minimum=1)
    current_throttled = raw.get("current_throttled")
    if not isinstance(current_throttled, bool):
        problems.append("invalid-current-throttled")

    ethernet = raw.get("ethernet")
    if not isinstance(ethernet, Mapping):
        problems.append("invalid-ethernet-sample")
        ethernet = {}
    carrier = _carrier(ethernet.get("carrier"))
    if carrier is None:
        problems.append("invalid-ethernet-carrier")
    operstate = ethernet.get("operstate")
    if not isinstance(operstate, str) or not operstate.strip():
        problems.append("invalid-ethernet-operstate")
        operstate = ""
    else:
        operstate = operstate.strip().lower()
    reference_driver = ethernet.get("reference_driver")
    if (
        not isinstance(reference_driver, str)
        or not _SAFE_ID.fullmatch(reference_driver)
    ):
        problems.append("invalid-reference-driver")
        reference_driver = ""
    rx_errors = _integer(ethernet, "rx_errors", problems, minimum=0)
    tx_errors = _integer(ethernet, "tx_errors", problems, minimum=0)
    rx_dropped = _integer(ethernet, "rx_dropped", problems, minimum=0)
    tx_dropped = _integer(ethernet, "tx_dropped", problems, minimum=0)

    if (
        memory_available is not None
        and memory_total is not None
        and memory_available > memory_total
    ):
        problems.append("memory-available-exceeds-total")

    if problems:
        return {
            "sample_id": sample_id,
            "raw_sha256": raw_sha256,
            "state": "quarantined",
            "classification": "malformed",
            "reasons": sorted(set(problems)),
        }

    assert temperature_c is not None
    assert memory_available is not None
    assert memory_total is not None
    assert load_1m is not None
    assert cpu_count is not None
    assert isinstance(current_throttled, bool)
    assert carrier is not None
    assert isinstance(reference_driver, str)
    assert rx_errors is not None
    assert tx_errors is not None
    assert rx_dropped is not None
    assert tx_dropped is not None
    memory_ratio = memory_available / memory_total
    normalized_load = load_1m / cpu_count
    unsafe: list[str] = []
    if temperature_c >= 80.0:
        unsafe.append("thermal-limit-near-or-reached")
    if current_throttled:
        unsafe.append("current-throttle-active")
    if memory_ratio < 0.08:
        unsafe.append("memory-reserve-too-low")
    if normalized_load > 2.0:
        unsafe.append("load-outside-shadow-policy-envelope")
    if not carrier or operstate != "up":
        unsafe.append("ethernet-reference-path-unhealthy")
    if reference_driver != expected_reference_driver:
        unsafe.append("reference-driver-mismatch")
    if rx_errors or tx_errors:
        unsafe.append("ethernet-error-evidence-present")
    if rx_dropped or tx_dropped:
        unsafe.append("ethernet-drop-evidence-present")

    normalized = {
        "sample_id": sample_id,
        "temperature_c": round(temperature_c, 3),
        "current_throttled": current_throttled,
        "memory_available_bytes": memory_available,
        "memory_total_bytes": memory_total,
        "memory_available_ratio": round(memory_ratio, 6),
        "load_1m": round(load_1m, 6),
        "cpu_count": cpu_count,
        "normalized_load": round(normalized_load, 6),
        "ethernet": {
            "carrier": carrier,
            "operstate": operstate,
            "reference_driver": reference_driver,
            "rx_errors": rx_errors,
            "tx_errors": tx_errors,
            "rx_dropped": rx_dropped,
            "tx_dropped": tx_dropped,
        },
    }
    return {
        "sample_id": sample_id,
        "raw_sha256": raw_sha256,
        "normalized": normalized,
        "state": "quarantined" if unsafe else "accepted",
        "classification": "unsafe" if unsafe else "safe",
        "reasons": sorted(unsafe),
    }


def _validate_policies(
    policies: Sequence[RuntimePolicy], baseline_policy_id: str
) -> None:
    if not policies or len(policies) > MAX_POLICY_CANDIDATES:
        raise ValueError("policy catalog must be non-empty and bounded")
    if len({item.policy_id for item in policies}) != len(policies):
        raise ValueError("policy ids must be unique")
    for policy in policies:
        if not _SAFE_ID.fullmatch(policy.policy_id):
            raise ValueError(f"invalid policy id: {policy.policy_id!r}")
        if policy.generation not in {0, 2, 3}:
            raise ValueError(f"unsupported runtime generation: {policy.generation}")
        if policy.strategy not in _STRATEGIES:
            raise ValueError(f"unknown runtime strategy: {policy.strategy!r}")
        if policy.strategy == "baseline":
            if policy.generation != 0:
                raise ValueError("baseline policy must be generation 0")
            if (
                policy.speculative_cpu_percent is not None
                or policy.speculative_memory_percent is not None
            ):
                raise ValueError("baseline policy must preserve current budgets")
            continue
        if policy.generation not in {2, 3}:
            raise ValueError("adaptive runtime candidates must be generation 2 or 3")
        if (
            not isinstance(policy.speculative_cpu_percent, int)
            or not 0 <= policy.speculative_cpu_percent <= MAX_SPECULATIVE_CPU_PERCENT
            or not isinstance(policy.speculative_memory_percent, int)
            or not 0
            <= policy.speculative_memory_percent
            <= MAX_SPECULATIVE_MEMORY_PERCENT
        ):
            raise ValueError(f"policy exceeds bounded speculative budget: {policy.policy_id}")
    baseline = next(
        (item for item in policies if item.policy_id == baseline_policy_id), None
    )
    if baseline is None or baseline.strategy != "baseline":
        raise ValueError("baseline policy must identify a catalog baseline")


def _aggregate(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    if not samples:
        return None
    temperatures = [float(item["temperature_c"]) for item in samples]
    memory_ratios = [float(item["memory_available_ratio"]) for item in samples]
    loads = [float(item["normalized_load"]) for item in samples]
    drivers = sorted(
        {str(item["ethernet"]["reference_driver"]) for item in samples}
    )
    return {
        "max_temperature_c": round(max(temperatures), 3),
        "average_temperature_c": round(sum(temperatures) / len(temperatures), 3),
        "current_throttle_seen": any(
            bool(item["current_throttled"]) for item in samples
        ),
        "minimum_memory_available_ratio": round(min(memory_ratios), 6),
        "maximum_normalized_load": round(max(loads), 6),
        "ethernet_healthy": all(
            bool(item["ethernet"]["carrier"])
            and item["ethernet"]["operstate"] == "up"
            and item["ethernet"]["rx_errors"] == 0
            and item["ethernet"]["tx_errors"] == 0
            and item["ethernet"]["rx_dropped"] == 0
            and item["ethernet"]["tx_dropped"] == 0
            for item in samples
        ),
        "reference_drivers": drivers,
    }


def _score_policy(
    policy: RuntimePolicy,
    aggregate: Mapping[str, Any] | None,
    *,
    evidence_sufficient: bool,
) -> tuple[float, list[str]]:
    if policy.strategy == "baseline":
        return 0.8, ["protected-current-policy"]
    if not evidence_sufficient or aggregate is None:
        return 0.0, ["insufficient-safe-evidence"]

    temperature = float(aggregate["max_temperature_c"])
    memory = float(aggregate["minimum_memory_available_ratio"])
    load = float(aggregate["maximum_normalized_load"])
    ethernet = bool(aggregate["ethernet_healthy"])
    if policy.strategy == "conserve":
        eligible = temperature >= 70.0 or memory <= 0.20 or load >= 0.85
        return (
            (0.88, ["bounded-resource-pressure-observed"])
            if eligible
            else (0.45, ["conservation-pressure-not-observed"])
        )
    if policy.strategy == "balanced":
        eligible = temperature <= 65.0 and memory >= 0.30 and load <= 0.65 and ethernet
        return (
            (0.84, ["balanced-headroom-observed"])
            if eligible
            else (0.55, ["balanced-headroom-not-proven"])
        )
    eligible = temperature <= 60.0 and memory >= 0.45 and load <= 0.40 and ethernet
    return (
        (0.90, ["strong-opportunistic-headroom-observed"])
        if eligible
        else (0.40, ["generation-3-headroom-not-proven"])
    )


def evaluate_shadow_window(
    samples: Sequence[Any],
    *,
    expected_reference_driver: str = "smsc95xx",
    baseline_policy_id: str = "runtime-baseline-v1",
    minimum_samples: int = 3,
    policies: Sequence[RuntimePolicy] = DEFAULT_POLICIES,
) -> dict[str, Any]:
    """Rank bounded policies and emit a deterministic, non-executing receipt."""

    if not isinstance(expected_reference_driver, str) or not _SAFE_ID.fullmatch(
        expected_reference_driver
    ):
        raise ValueError("expected reference driver must be an auditable id")
    if not 1 <= minimum_samples <= MAX_WINDOW_SAMPLES:
        raise ValueError("minimum sample count is outside the bounded window")
    _validate_policies(policies, baseline_policy_id)

    validated = [
        validate_runtime_sample(
            raw,
            index=index,
            expected_reference_driver=expected_reference_driver,
        )
        for index, raw in enumerate(samples)
    ]
    window_issues: list[str] = []
    if len(samples) > MAX_WINDOW_SAMPLES:
        window_issues.append("sample-window-exceeds-bound")
    sample_ids = [item["sample_id"] for item in validated]
    if len(set(sample_ids)) != len(sample_ids):
        window_issues.append("duplicate-sample-id")
    accepted = [
        item["normalized"] for item in validated if item["state"] == "accepted"
    ]
    quarantined = [item for item in validated if item["state"] == "quarantined"]
    aggregate = _aggregate(accepted)
    evidence_sufficient = (
        not quarantined
        and not window_issues
        and len(accepted) >= minimum_samples
    )

    ranked: list[dict[str, Any]] = []
    for policy in policies:
        score, evidence = _score_policy(
            policy, aggregate, evidence_sufficient=evidence_sufficient
        )
        ranked.append(
            {
                **policy.receipt_mapping(),
                "score": round(score, 3),
                "score_evidence": evidence,
                "eligible": policy.strategy == "baseline" or evidence_sufficient,
                "status": "ranked",
            }
        )
    ranked.sort(
        key=lambda item: (
            -float(item["score"]),
            item["strategy"] != "baseline",
            item["policy_id"],
        )
    )
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank

    baseline = next(item for item in ranked if item["policy_id"] == baseline_policy_id)
    if quarantined or window_issues:
        selected = baseline
        decision_state = "quarantined"
        reason = "sample-window-quarantined"
        recommendation = "no-change"
    elif not evidence_sufficient:
        selected = baseline
        decision_state = "insufficient-evidence"
        reason = "minimum-safe-sample-count-not-met"
        recommendation = "no-change"
    elif ranked[0]["policy_id"] == baseline_policy_id:
        selected = baseline
        decision_state = "completed"
        reason = "baseline-ranked-first"
        recommendation = "no-change"
    else:
        selected = ranked[0]
        decision_state = "completed"
        reason = "bounded-candidate-ranked-above-baseline"
        recommendation = "shadow-change"

    for item in ranked:
        if item["policy_id"] == selected["policy_id"]:
            item["status"] = (
                "recommended-shadow-only"
                if recommendation == "shadow-change"
                else "selected-no-change"
            )
        elif item["strategy"] == "baseline":
            item["status"] = "protected-lkg"

    receipt = {
        "schema": SHADOW_RECEIPT_SCHEMA,
        "mode": "shadow",
        "generation_ceiling": 3,
        "input": {
            "expected_reference_driver": expected_reference_driver,
            "baseline_policy_id": baseline_policy_id,
            "minimum_samples": minimum_samples,
            "maximum_samples": MAX_WINDOW_SAMPLES,
            "sample_count": len(samples),
        },
        "evidence": {
            "accepted_count": len(accepted),
            "quarantined_count": len(quarantined),
            "sample_receipts": validated,
            "window_issues": sorted(window_issues),
            "aggregate": aggregate,
        },
        "ranking": ranked,
        "decision": {
            "state": decision_state,
            "recommendation": recommendation,
            "selected_policy_id": selected["policy_id"],
            "selected_generation": selected["generation"],
            "reason": reason,
            "change_applied": False,
        },
        "execution": {
            "active_executor_default": ACTIVE_EXECUTION_DEFAULT,
            "enabled": False,
            "performed": False,
            "requires_explicit_reversible_authority": True,
            "requires_rollback_metadata": True,
        },
        "invariants": {
            "live_hardware_contacted": False,
            "kernel_changed": False,
            "driver_binding_changed": False,
            "boot_changed": False,
            "network_changed": False,
            "reference_driver_is_protected": True,
            "baseline_remains_competing_branch": True,
        },
    }
    return _seal(receipt)


def _authority_problems(
    authority: ReversibleAuthority | None, receipt_sha256: str
) -> list[str]:
    if authority is None:
        return ["missing-authority"]
    problems: list[str] = []
    if authority.authorized is not True:
        problems.append("authority-not-granted")
    if authority.scope != EXPECTED_AUTHORITY_SCOPE:
        problems.append("authority-scope-mismatch")
    if authority.reversible is not True:
        problems.append("authority-not-reversible")
    if not isinstance(authority.authority_ref, str) or not _SAFE_ID.fullmatch(
        authority.authority_ref
    ):
        problems.append("invalid-authority-ref")
    if authority.shadow_receipt_sha256 != receipt_sha256:
        problems.append("authority-not-bound-to-shadow-receipt")
    if (
        not isinstance(authority.rollback_target, str)
        or not authority.rollback_target.strip()
    ):
        problems.append("missing-rollback-target")
    if not isinstance(
        authority.rollback_receipt_sha256, str
    ) or not _SHA256.fullmatch(authority.rollback_receipt_sha256):
        problems.append("invalid-rollback-receipt-sha256")
    return sorted(problems)


def execute_runtime_recommendation(
    shadow_receipt: Mapping[str, Any],
    *,
    active: bool = ACTIVE_EXECUTION_DEFAULT,
    authority: ReversibleAuthority | None = None,
    executor: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]
    | None = None,
) -> dict[str, Any]:
    """Fail-closed boundary for a future injected reversible executor.

    This module supplies no operating-system executor.  A caller must opt in,
    present receipt-bound reversible authority and rollback metadata, and inject
    an executor that arms rollback before applying a selected policy.
    """

    shadow_sha256 = str(shadow_receipt.get("receipt_sha256", ""))
    base = {
        "schema": EXECUTION_RECEIPT_SCHEMA,
        "shadow_receipt_sha256": shadow_sha256,
        "active_requested": bool(active),
        "active_executor_default": ACTIVE_EXECUTION_DEFAULT,
        "performed": False,
    }
    if (
        shadow_receipt.get("schema") != SHADOW_RECEIPT_SCHEMA
        or not verify_receipt(shadow_receipt)
    ):
        return _seal({**base, "state": "quarantined", "reason": "invalid-shadow-receipt"})
    decision = shadow_receipt.get("decision", {})
    if decision.get("recommendation") != "shadow-change":
        return _seal({**base, "state": "no_change", "reason": "shadow-receipt-recommends-no-change"})
    if not active:
        return _seal({**base, "state": "held", "reason": "active-executor-disabled"})
    problems = _authority_problems(authority, shadow_sha256)
    if problems:
        return _seal(
            {
                **base,
                "state": "held",
                "reason": "reversible-authority-or-rollback-metadata-invalid",
                "authority_problems": problems,
            }
        )
    if executor is None:
        return _seal({**base, "state": "held", "reason": "active-executor-not-configured"})

    assert authority is not None
    selected_id = decision.get("selected_policy_id")
    ranking = shadow_receipt.get("ranking")
    if not isinstance(ranking, list):
        return _seal(
            {**base, "state": "quarantined", "reason": "invalid-policy-ranking"}
        )
    selected = next(
        (
            item
            for item in ranking
            if isinstance(item, Mapping) and item.get("policy_id") == selected_id
        ),
        None,
    )
    if selected is None:
        return _seal(
            {**base, "state": "quarantined", "reason": "selected-policy-missing"}
        )
    rollback = {
        "target": authority.rollback_target,
        "receipt_sha256": authority.rollback_receipt_sha256,
    }
    try:
        outcome = executor(selected, rollback)
    except Exception as exc:
        return _seal(
            {
                **base,
                "state": "quarantined",
                "reason": "executor-failed-without-reversible-proof",
                "authority_ref": authority.authority_ref,
                "error_class": type(exc).__name__,
            }
        )
    if (
        not isinstance(outcome, Mapping)
        or outcome.get("applied") is not True
        or outcome.get("rollback_armed") is not True
        or outcome.get("rollback_target") != authority.rollback_target
    ):
        return _seal(
            {
                **base,
                "state": "quarantined",
                "reason": "executor-did-not-prove-reversible-application",
                "authority_ref": authority.authority_ref,
            }
        )
    return _seal(
        {
            **base,
            "state": "executed",
            "reason": "explicit-reversible-authority-and-rollback-proven",
            "performed": True,
            "authority_ref": authority.authority_ref,
            "selected_policy_id": selected_id,
            "rollback": rollback,
            "executor_outcome": dict(outcome),
        }
    )
