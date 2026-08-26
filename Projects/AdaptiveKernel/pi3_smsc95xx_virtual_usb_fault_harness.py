"""Zero-authority virtual USB backend fault harness for the Pi3 smsc95xx candidate.

This stage consumes the sealed integrated packet/control-loop receipt and adds
transfer-fault timing/retry semantics without opening a USB device or contacting
the Pi.  It exists to make retry, stall, short-transfer, disconnect, and
quarantine behavior explicit before any real device actuation is considered.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any, Mapping, Sequence

UPSTREAM_SCHEMA = "aurum.pi3.smsc95xx.integrated-packet-control-loop-differential.v1"
UPSTREAM_STATE = "controlled-integrated-host-packet-control-loop-passed"
SCHEMA = "aurum.pi3.smsc95xx.virtual-usb-fault-harness.v1"
STATE = "controlled-virtual-usb-fault-harness-passed"
DEFAULT_SEQUENCE_SEED = 0x9514FA17
DEFAULT_SEQUENCE_STEPS = 16_384
DIRECTIONS = ("tx", "rx")
FAULTS = ("success", "timeout", "io-error", "stall", "short-transfer", "disconnect")

_REQUIRED_FALSE = (
    "mutation_allowed",
    "device_io_allowed",
    "usb_transfer_allowed",
    "register_write_allowed",
    "interrupt_ack_write_allowed",
    "driver_binding_change_allowed",
    "kernel_module_load_allowed",
    "firmware_mutation_allowed",
    "network_configuration_change_allowed",
    "promotion_allowed",
    "write_authority",
)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_sealed(value: Mapping[str, Any]) -> bool:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    body = dict(value)
    body.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(body)


def _validate_upstream(receipt: Mapping[str, Any]) -> None:
    if receipt.get("schema") != UPSTREAM_SCHEMA:
        raise ValueError("integrated receipt schema mismatch")
    if receipt.get("state") != UPSTREAM_STATE:
        raise ValueError("integrated receipt has not passed")
    if not _verify_sealed(receipt):
        raise ValueError("integrated receipt seal mismatch")
    if receipt.get("mismatch_count") != 0:
        raise ValueError("integrated receipt contains mismatches")
    authority = receipt.get("authority")
    if not isinstance(authority, Mapping):
        raise ValueError("integrated authority is malformed")
    for key in _REQUIRED_FALSE:
        if authority.get(key) is not False:
            raise ValueError(f"integrated receipt must keep {key}=false")
    invariants = receipt.get("invariants")
    if not isinstance(invariants, Mapping):
        raise ValueError("integrated invariants are malformed")
    for key in ("live_pi_contacted", "usb_device_opened", "usb_transfer_submitted"):
        if invariants.get(key) is not False:
            raise ValueError(f"integrated receipt crossed hardware boundary: {key}")


def _validate_request(direction: str, outcomes: Sequence[str], retry_budget: int) -> None:
    if direction not in DIRECTIONS:
        raise ValueError("direction must be tx or rx")
    if not isinstance(retry_budget, int) or not 0 <= retry_budget <= 8:
        raise ValueError("retry_budget must be an integer from 0 through 8")
    if not outcomes:
        raise ValueError("at least one virtual backend outcome is required")
    if any(outcome not in FAULTS for outcome in outcomes):
        raise ValueError("unknown virtual USB outcome")


def simulate_transfer(direction: str, outcomes: Sequence[str], *, retry_budget: int = 2) -> dict[str, Any]:
    """Run one bounded virtual USB transfer.

    Retries exist only for timeout, transient I/O error, and a modeled endpoint
    stall.  A stall may emit a *clear-halt intent* but never performs a USB
    clear-halt request.  Short transfers and disconnects fail closed immediately.
    The outcome list is virtual backend evidence, not a live transport.
    """
    _validate_request(direction, outcomes, retry_budget)
    attempts = 0
    retries_used = 0
    clear_halt_intents = 0
    trace: list[str] = []

    for outcome in outcomes:
        attempts += 1
        trace.append(outcome)
        if outcome == "success":
            return {
                "direction": direction,
                "terminal": "delivered",
                "delivered": True,
                "quarantined": False,
                "attempts": attempts,
                "retries_used": retries_used,
                "clear_halt_intents": clear_halt_intents,
                "trace": trace,
            }
        if outcome == "disconnect":
            return {
                "direction": direction,
                "terminal": "disconnected",
                "delivered": False,
                "quarantined": True,
                "attempts": attempts,
                "retries_used": retries_used,
                "clear_halt_intents": clear_halt_intents,
                "trace": trace,
            }
        if outcome == "short-transfer":
            return {
                "direction": direction,
                "terminal": "short-transfer-quarantined",
                "delivered": False,
                "quarantined": True,
                "attempts": attempts,
                "retries_used": retries_used,
                "clear_halt_intents": clear_halt_intents,
                "trace": trace,
            }
        if outcome == "stall":
            clear_halt_intents += 1
        if retries_used >= retry_budget:
            return {
                "direction": direction,
                "terminal": "retry-budget-exhausted",
                "delivered": False,
                "quarantined": True,
                "attempts": attempts,
                "retries_used": retries_used,
                "clear_halt_intents": clear_halt_intents,
                "trace": trace,
            }
        retries_used += 1

    return {
        "direction": direction,
        "terminal": "backend-evidence-exhausted",
        "delivered": False,
        "quarantined": True,
        "attempts": attempts,
        "retries_used": retries_used,
        "clear_halt_intents": clear_halt_intents,
        "trace": trace,
    }


def _oracle(direction: str, outcomes: Sequence[str], retry_budget: int) -> tuple[Any, ...]:
    """Independent compact oracle used for differential fault checking."""
    _validate_request(direction, outcomes, retry_budget)
    retries = 0
    stalls = 0
    for index, outcome in enumerate(outcomes, start=1):
        if outcome == "success":
            return ("delivered", True, False, index, retries, stalls)
        if outcome == "disconnect":
            return ("disconnected", False, True, index, retries, stalls)
        if outcome == "short-transfer":
            return ("short-transfer-quarantined", False, True, index, retries, stalls)
        stalls += int(outcome == "stall")
        if retries >= retry_budget:
            return ("retry-budget-exhausted", False, True, index, retries, stalls)
        retries += 1
    return ("backend-evidence-exhausted", False, True, len(outcomes), retries, stalls)


def _result_tuple(result: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        result["terminal"],
        result["delivered"],
        result["quarantined"],
        result["attempts"],
        result["retries_used"],
        result["clear_halt_intents"],
    )


def run_fault_harness(
    *,
    integrated_receipt: Mapping[str, Any],
    retry_budget: int = 2,
    sequence_seed: int = DEFAULT_SEQUENCE_SEED,
    sequence_steps: int = DEFAULT_SEQUENCE_STEPS,
) -> dict[str, Any]:
    _validate_upstream(integrated_receipt)
    if not isinstance(sequence_seed, int) or sequence_seed < 0:
        raise ValueError("sequence_seed must be a non-negative integer")
    if not isinstance(sequence_steps, int) or sequence_steps < 1:
        raise ValueError("sequence_steps must be positive")
    if not isinstance(retry_budget, int) or not 0 <= retry_budget <= 8:
        raise ValueError("retry_budget must be an integer from 0 through 8")

    templates: tuple[tuple[str, ...], ...] = (
        ("success",),
        ("timeout", "success"),
        ("io-error", "success"),
        ("stall", "success"),
        ("timeout", "timeout", "timeout"),
        ("io-error", "io-error", "io-error"),
        ("stall", "stall", "stall"),
        ("short-transfer",),
        ("disconnect",),
    )
    mismatch_count = 0
    matrix_scenarios = 0
    digest = hashlib.sha256()
    terminal_counts: dict[str, int] = {}

    for direction in DIRECTIONS:
        for outcomes in templates:
            result = simulate_transfer(direction, outcomes, retry_budget=retry_budget)
            expected = _oracle(direction, outcomes, retry_budget)
            mismatch_count += int(_result_tuple(result) != expected)
            matrix_scenarios += 1
            terminal_counts[result["terminal"]] = terminal_counts.get(result["terminal"], 0) + 1
            digest.update(json.dumps([direction, outcomes, _result_tuple(result)], separators=(",", ":")).encode("utf-8"))

    rng = random.Random(sequence_seed)
    for _ in range(sequence_steps):
        direction = DIRECTIONS[rng.randrange(len(DIRECTIONS))]
        length = 1 + rng.randrange(4)
        outcomes = tuple(FAULTS[rng.randrange(len(FAULTS))] for _ in range(length))
        result = simulate_transfer(direction, outcomes, retry_budget=retry_budget)
        expected = _oracle(direction, outcomes, retry_budget)
        mismatch_count += int(_result_tuple(result) != expected)
        terminal_counts[result["terminal"]] = terminal_counts.get(result["terminal"], 0) + 1
        digest.update(json.dumps([direction, outcomes, _result_tuple(result)], separators=(",", ":")).encode("utf-8"))

    body: dict[str, Any] = {
        "schema": SCHEMA,
        "state": STATE if mismatch_count == 0 else "controlled-virtual-usb-fault-harness-failed",
        "upstream_integrated_receipt_sha256": integrated_receipt["receipt_sha256"],
        "retry_budget": retry_budget,
        "matrix_scenarios": matrix_scenarios,
        "deterministic_sequence_seed": sequence_seed,
        "deterministic_sequence_steps": sequence_steps,
        "scenario_count": matrix_scenarios + sequence_steps,
        "mismatch_count": mismatch_count,
        "terminal_counts": dict(sorted(terminal_counts.items())),
        "trace_sha256": digest.hexdigest(),
        "fault_classes": list(FAULTS),
        "invariants": {
            "live_pi_contacted": False,
            "usb_device_opened": False,
            "usb_transfer_submitted": False,
            "clear_halt_submitted": False,
            "register_access_performed": False,
            "driver_binding_changed": False,
        },
        "authority": {key: False for key in _REQUIRED_FALSE},
        "strongest_claim": (
            "The sealed integrated Pi3 smsc95xx candidate has deterministic host-only fault/retry behavior "
            "for success, timeout, transient I/O error, endpoint stall, short transfer, and disconnect. "
            "Retries are bounded and terminal faults quarantine without any real USB or Pi actuation."
        ),
        "next_safe_gate": "virtual-usb-timing-and-concurrency-model",
    }
    body["receipt_sha256"] = _canonical_sha256(body)
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integrated-receipt", required=True, type=Path)
    parser.add_argument("--retry-budget", type=int, default=2)
    parser.add_argument("--sequence-seed", type=lambda value: int(value, 0), default=DEFAULT_SEQUENCE_SEED)
    parser.add_argument("--sequence-steps", type=int, default=DEFAULT_SEQUENCE_STEPS)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    integrated = json.loads(args.integrated_receipt.read_text(encoding="utf-8"))
    receipt = run_fault_harness(
        integrated_receipt=integrated,
        retry_budget=args.retry_budget,
        sequence_seed=args.sequence_seed,
        sequence_steps=args.sequence_steps,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["state"] == STATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
