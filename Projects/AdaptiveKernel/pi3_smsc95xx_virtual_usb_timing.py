"""Zero-authority virtual USB timing/concurrency model for the Pi3 smsc95xx lane.

This stage consumes the sealed virtual USB fault receipt and models ordering,
endpoint serialization, independent TX/RX overlap, bounded retry backoff, and
stale completion handling around disconnect/reconnect. It never opens a USB
handle, contacts the Pi, or performs a real transfer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

UPSTREAM_SCHEMA = "aurum.pi3.smsc95xx.virtual-usb-fault-harness.v1"
UPSTREAM_STATE = "controlled-virtual-usb-fault-harness-passed"
SCHEMA = "aurum.pi3.smsc95xx.virtual-usb-timing-concurrency.v1"
STATE = "controlled-virtual-usb-timing-concurrency-passed"
DEFAULT_SEQUENCE_SEED = 0x9514C0DE
DEFAULT_SEQUENCE_STEPS = 32_768
DIRECTIONS = ("tx", "rx")

_REQUIRED_FALSE = (
    "mutation_allowed", "device_io_allowed", "usb_transfer_allowed",
    "register_write_allowed", "interrupt_ack_write_allowed",
    "driver_binding_change_allowed", "kernel_module_load_allowed",
    "firmware_mutation_allowed", "network_configuration_change_allowed",
    "promotion_allowed", "write_authority",
)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _verify_sealed(value: Mapping[str, Any]) -> bool:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    body = dict(value)
    body.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(body)


def _validate_upstream(receipt: Mapping[str, Any]) -> int:
    if receipt.get("schema") != UPSTREAM_SCHEMA or receipt.get("state") != UPSTREAM_STATE:
        raise ValueError("virtual fault receipt is not the expected passed schema/state")
    if not _verify_sealed(receipt) or receipt.get("mismatch_count") != 0:
        raise ValueError("virtual fault receipt is unsealed or contains mismatches")
    authority = receipt.get("authority")
    if not isinstance(authority, Mapping):
        raise ValueError("virtual fault authority is malformed")
    for key in _REQUIRED_FALSE:
        if authority.get(key) is not False:
            raise ValueError(f"virtual fault receipt must keep {key}=false")
    invariants = receipt.get("invariants")
    if not isinstance(invariants, Mapping):
        raise ValueError("virtual fault invariants are malformed")
    for key in ("live_pi_contacted", "usb_device_opened", "usb_transfer_submitted", "clear_halt_submitted"):
        if invariants.get(key) is not False:
            raise ValueError(f"upstream crossed no-hardware boundary: {key}")
    retry_budget = receipt.get("retry_budget")
    if not isinstance(retry_budget, int) or not 0 <= retry_budget <= 8:
        raise ValueError("upstream retry budget is invalid")
    return retry_budget


@dataclass(frozen=True)
class VirtualTransfer:
    transfer_id: int
    direction: str
    generation: int
    submit_ms: int
    start_ms: int
    finish_ms: int


class VirtualUsbScheduler:
    def __init__(self) -> None:
        self.connected = True
        self.generation = 0
        self._next_id = 1
        self._busy_until = {"tx": 0, "rx": 0}

    @staticmethod
    def _validate_time(value: int, name: str) -> None:
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")

    def submit(self, direction: str, *, now_ms: int, duration_ms: int) -> VirtualTransfer:
        if direction not in DIRECTIONS:
            raise ValueError("direction must be tx or rx")
        self._validate_time(now_ms, "now_ms")
        self._validate_time(duration_ms, "duration_ms")
        if duration_ms == 0:
            raise ValueError("duration_ms must be positive")
        if not self.connected:
            raise RuntimeError("virtual USB backend is disconnected")
        start = max(now_ms, self._busy_until[direction])
        finish = start + duration_ms
        transfer = VirtualTransfer(
            transfer_id=self._next_id,
            direction=direction,
            generation=self.generation,
            submit_ms=now_ms,
            start_ms=start,
            finish_ms=finish,
        )
        self._next_id += 1
        self._busy_until[direction] = finish
        return transfer

    def complete(self, transfer: VirtualTransfer, *, now_ms: int) -> str:
        self._validate_time(now_ms, "now_ms")
        if transfer.generation != self.generation:
            return "stale-completion-quarantined"
        if not self.connected:
            return "disconnected-completion-quarantined"
        if now_ms < transfer.finish_ms:
            return "early-completion-refused"
        return "completed"

    def disconnect(self, *, now_ms: int) -> int:
        self._validate_time(now_ms, "now_ms")
        if not self.connected:
            return self.generation
        self.connected = False
        self.generation += 1
        return self.generation

    def reconnect(self, *, now_ms: int) -> int:
        self._validate_time(now_ms, "now_ms")
        if self.connected:
            return self.generation
        self.connected = True
        self._busy_until = {"tx": now_ms, "rx": now_ms}
        return self.generation


def retry_due_ms(*, attempt: int, base_backoff_ms: int = 5, max_backoff_ms: int = 40) -> int:
    if not isinstance(attempt, int) or attempt < 1:
        raise ValueError("attempt must be >= 1")
    if not isinstance(base_backoff_ms, int) or base_backoff_ms < 1:
        raise ValueError("base_backoff_ms must be positive")
    if not isinstance(max_backoff_ms, int) or max_backoff_ms < base_backoff_ms:
        raise ValueError("max_backoff_ms must be >= base_backoff_ms")
    return min(max_backoff_ms, base_backoff_ms * (2 ** (attempt - 1)))


def _check_scheduler_invariants(scheduler: VirtualUsbScheduler, transfers: list[VirtualTransfer]) -> int:
    violations = 0
    for transfer in transfers:
        violations += int(transfer.start_ms < transfer.submit_ms)
        violations += int(transfer.finish_ms <= transfer.start_ms)
    for direction in DIRECTIONS:
        ordered = sorted((t for t in transfers if t.direction == direction and t.generation == scheduler.generation), key=lambda item: item.transfer_id)
        for previous, current in zip(ordered, ordered[1:]):
            violations += int(current.start_ms < previous.finish_ms)
    return violations


def run_timing_model(
    *,
    fault_receipt: Mapping[str, Any],
    sequence_seed: int = DEFAULT_SEQUENCE_SEED,
    sequence_steps: int = DEFAULT_SEQUENCE_STEPS,
) -> dict[str, Any]:
    retry_budget = _validate_upstream(fault_receipt)
    if not isinstance(sequence_seed, int) or sequence_seed < 0:
        raise ValueError("sequence_seed must be non-negative")
    if not isinstance(sequence_steps, int) or sequence_steps < 1:
        raise ValueError("sequence_steps must be positive")

    mismatch_count = 0
    digest = hashlib.sha256()
    scenarios = 0

    # Deterministic bounded matrix: same-endpoint serialization, TX/RX overlap,
    # completion timing, disconnect invalidation, reconnect, and retry backoff.
    scheduler = VirtualUsbScheduler()
    tx1 = scheduler.submit("tx", now_ms=0, duration_ms=10)
    tx2 = scheduler.submit("tx", now_ms=1, duration_ms=4)
    rx1 = scheduler.submit("rx", now_ms=1, duration_ms=3)
    mismatch_count += int(tx2.start_ms != tx1.finish_ms)
    mismatch_count += int(rx1.start_ms != 1)
    mismatch_count += int(scheduler.complete(tx1, now_ms=9) != "early-completion-refused")
    mismatch_count += int(scheduler.complete(rx1, now_ms=4) != "completed")
    scenarios += 4

    scheduler.disconnect(now_ms=5)
    mismatch_count += int(scheduler.complete(tx1, now_ms=10) != "stale-completion-quarantined")
    scheduler.reconnect(now_ms=6)
    tx3 = scheduler.submit("tx", now_ms=6, duration_ms=2)
    mismatch_count += int(tx3.start_ms != 6 or scheduler.complete(tx3, now_ms=8) != "completed")
    scenarios += 2

    expected_backoff = (5, 10, 20, 40, 40)
    for attempt, expected in enumerate(expected_backoff, start=1):
        mismatch_count += int(retry_due_ms(attempt=attempt) != expected)
        scenarios += 1

    rng = random.Random(sequence_seed)
    scheduler = VirtualUsbScheduler()
    transfers: list[VirtualTransfer] = []
    now_ms = 0
    operation_counts = {"submit": 0, "complete": 0, "disconnect": 0, "reconnect": 0, "retry-backoff": 0}

    for step in range(sequence_steps):
        now_ms += rng.randrange(0, 3)
        op = rng.randrange(100)
        if op < 58 and scheduler.connected:
            direction = DIRECTIONS[rng.randrange(2)]
            transfer = scheduler.submit(direction, now_ms=now_ms, duration_ms=1 + rng.randrange(8))
            transfers.append(transfer)
            operation_counts["submit"] += 1
            digest.update(json.dumps([step, "submit", transfer.__dict__], sort_keys=True, separators=(",", ":")).encode("utf-8"))
        elif op < 78 and transfers:
            transfer = transfers[rng.randrange(len(transfers))]
            status = scheduler.complete(transfer, now_ms=now_ms)
            if transfer.generation != scheduler.generation:
                mismatch_count += int(status != "stale-completion-quarantined")
            elif not scheduler.connected:
                mismatch_count += int(status != "disconnected-completion-quarantined")
            elif now_ms < transfer.finish_ms:
                mismatch_count += int(status != "early-completion-refused")
            else:
                mismatch_count += int(status != "completed")
            operation_counts["complete"] += 1
            digest.update(json.dumps([step, "complete", transfer.transfer_id, now_ms, status], separators=(",", ":")).encode("utf-8"))
        elif op < 86:
            scheduler.disconnect(now_ms=now_ms)
            operation_counts["disconnect"] += 1
            digest.update(json.dumps([step, "disconnect", now_ms, scheduler.generation], separators=(",", ":")).encode("utf-8"))
        elif op < 94:
            scheduler.reconnect(now_ms=now_ms)
            operation_counts["reconnect"] += 1
            digest.update(json.dumps([step, "reconnect", now_ms, scheduler.generation], separators=(",", ":")).encode("utf-8"))
        else:
            attempt = 1 + rng.randrange(max(1, retry_budget + 1))
            delay = retry_due_ms(attempt=attempt)
            mismatch_count += int(delay < 5 or delay > 40)
            operation_counts["retry-backoff"] += 1
            digest.update(json.dumps([step, "retry", attempt, delay], separators=(",", ":")).encode("utf-8"))

    mismatch_count += _check_scheduler_invariants(scheduler, transfers)

    body: dict[str, Any] = {
        "schema": SCHEMA,
        "state": STATE if mismatch_count == 0 else "controlled-virtual-usb-timing-concurrency-failed",
        "upstream_fault_receipt_sha256": fault_receipt["receipt_sha256"],
        "retry_budget": retry_budget,
        "matrix_scenarios": scenarios,
        "deterministic_sequence_seed": sequence_seed,
        "deterministic_sequence_steps": sequence_steps,
        "scenario_count": scenarios + sequence_steps,
        "mismatch_count": mismatch_count,
        "operation_counts": operation_counts,
        "trace_sha256": digest.hexdigest(),
        "timing_contract": {
            "same_endpoint_serialized": True,
            "tx_rx_overlap_allowed": True,
            "early_completion_refused": True,
            "disconnect_invalidates_prior_generation": True,
            "stale_completion_quarantined": True,
            "retry_backoff_bounded_ms": [5, 40],
        },
        "invariants": {
            "live_pi_contacted": False,
            "usb_device_opened": False,
            "usb_transfer_submitted": False,
            "clear_halt_submitted": False,
            "register_access_performed": False,
            "wall_clock_or_sleep_used": False,
            "driver_binding_changed": False,
        },
        "authority": {key: False for key in _REQUIRED_FALSE},
        "strongest_claim": (
            "The sealed virtual USB fault model now has deterministic zero-authority timing/concurrency semantics: "
            "same-endpoint transfers serialize, TX and RX may overlap, early/stale completions fail closed, "
            "disconnect invalidates the prior generation, and retry backoff is bounded."
        ),
        "next_safe_gate": "virtual-usb-cancellation-and-queue-pressure-model",
    }
    body["receipt_sha256"] = _canonical_sha256(body)
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fault-receipt", type=Path, required=True)
    parser.add_argument("--sequence-seed", type=lambda value: int(value, 0), default=DEFAULT_SEQUENCE_SEED)
    parser.add_argument("--sequence-steps", type=int, default=DEFAULT_SEQUENCE_STEPS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fault_receipt = json.loads(args.fault_receipt.read_text(encoding="utf-8"))
    receipt = run_timing_model(
        fault_receipt=fault_receipt,
        sequence_seed=args.sequence_seed,
        sequence_steps=args.sequence_steps,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["state"] == STATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
