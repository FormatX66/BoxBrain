"""Zero-authority cancellation/backpressure model for the Pi3 smsc95xx USB lane.

Consumes the sealed virtual USB timing receipt and stress-tests bounded endpoint
queues, cancellation, disconnect invalidation, and recovery from pressure. This is
virtual scheduling evidence only: no Pi, USB handle, URB, register, module, driver
binding, firmware, or network state is touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

UPSTREAM_SCHEMA = "aurum.pi3.smsc95xx.virtual-usb-timing-concurrency.v1"
UPSTREAM_STATE = "controlled-virtual-usb-timing-concurrency-passed"
SCHEMA = "aurum.pi3.smsc95xx.virtual-usb-queue-pressure.v1"
STATE = "controlled-virtual-usb-queue-pressure-passed"
DEFAULT_SEQUENCE_SEED = 0x9514BACC
DEFAULT_SEQUENCE_STEPS = 32_768
DEFAULT_QUEUE_DEPTH = 8
DIRECTIONS = ("tx", "rx")

_REQUIRED_FALSE = (
    "mutation_allowed", "device_io_allowed", "usb_transfer_allowed",
    "register_write_allowed", "interrupt_ack_write_allowed",
    "driver_binding_change_allowed", "kernel_module_load_allowed",
    "firmware_mutation_allowed", "network_configuration_change_allowed",
    "promotion_allowed", "write_authority",
)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_sealed(value: Mapping[str, Any]) -> bool:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    body = dict(value)
    body.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(body)


def _validate_upstream(receipt: Mapping[str, Any]) -> None:
    if receipt.get("schema") != UPSTREAM_SCHEMA or receipt.get("state") != UPSTREAM_STATE:
        raise ValueError("timing receipt is not the expected passed schema/state")
    if not _verify_sealed(receipt) or receipt.get("mismatch_count") != 0:
        raise ValueError("timing receipt is unsealed or contains mismatches")
    authority = receipt.get("authority")
    if not isinstance(authority, Mapping):
        raise ValueError("timing authority is malformed")
    for key in _REQUIRED_FALSE:
        if authority.get(key) is not False:
            raise ValueError(f"timing receipt must keep {key}=false")
    invariants = receipt.get("invariants")
    if not isinstance(invariants, Mapping):
        raise ValueError("timing invariants are malformed")
    for key in ("live_pi_contacted", "usb_device_opened", "usb_transfer_submitted", "clear_halt_submitted", "register_access_performed", "wall_clock_or_sleep_used"):
        if invariants.get(key) is not False:
            raise ValueError(f"timing receipt crossed the zero-authority boundary: {key}")


@dataclass
class QueueItem:
    transfer_id: int
    generation: int
    cancel_requested: bool = False


class EndpointQueue:
    """Bounded virtual endpoint queue with one active item and FIFO waiting work."""

    def __init__(self, direction: str, *, max_depth: int = DEFAULT_QUEUE_DEPTH) -> None:
        if direction not in DIRECTIONS:
            raise ValueError("direction must be tx or rx")
        if not isinstance(max_depth, int) or max_depth < 1 or max_depth > 1024:
            raise ValueError("max_depth must be between 1 and 1024")
        self.direction = direction
        self.max_depth = max_depth
        self.generation = 0
        self.connected = True
        self._next_id = 1
        self.active: QueueItem | None = None
        self.waiting: list[QueueItem] = []
        self.cancel_intents = 0
        self.quarantined = 0

    @property
    def depth(self) -> int:
        return len(self.waiting) + int(self.active is not None)

    def submit(self) -> tuple[str, int | None]:
        if not self.connected:
            return "rejected-disconnected", None
        if self.depth >= self.max_depth:
            return "backpressure", None
        item = QueueItem(self._next_id, self.generation)
        self._next_id += 1
        if self.active is None:
            self.active = item
            return "active", item.transfer_id
        self.waiting.append(item)
        return "queued", item.transfer_id

    def cancel(self, transfer_id: int) -> str:
        if not isinstance(transfer_id, int) or transfer_id < 1:
            raise ValueError("transfer_id must be positive")
        if self.active is not None and self.active.transfer_id == transfer_id:
            if not self.active.cancel_requested:
                self.active.cancel_requested = True
                self.cancel_intents += 1
            return "active-cancel-intent"
        for index, item in enumerate(self.waiting):
            if item.transfer_id == transfer_id:
                del self.waiting[index]
                return "queued-cancelled"
        return "not-found"

    def complete_active(self) -> str:
        if self.active is None:
            return "idle"
        item = self.active
        if item.generation != self.generation or not self.connected:
            status = "stale-completion-quarantined"
            self.quarantined += 1
        elif item.cancel_requested:
            status = "cancelled-completion-quarantined"
            self.quarantined += 1
        else:
            status = "completed"
        self.active = self.waiting.pop(0) if self.waiting else None
        return status

    def disconnect(self) -> int:
        if not self.connected:
            return 0
        self.connected = False
        self.generation += 1
        invalidated = self.depth
        self.quarantined += invalidated
        self.active = None
        self.waiting.clear()
        return invalidated

    def reconnect(self) -> None:
        self.connected = True

    def assert_invariants(self) -> int:
        violations = int(self.depth > self.max_depth)
        ids = ([self.active.transfer_id] if self.active else []) + [item.transfer_id for item in self.waiting]
        violations += int(len(ids) != len(set(ids)))
        if self.active is not None:
            violations += int(self.active.generation != self.generation)
        violations += sum(int(item.generation != self.generation) for item in self.waiting)
        return violations


def run_queue_pressure_model(
    *,
    timing_receipt: Mapping[str, Any],
    max_depth: int = DEFAULT_QUEUE_DEPTH,
    sequence_seed: int = DEFAULT_SEQUENCE_SEED,
    sequence_steps: int = DEFAULT_SEQUENCE_STEPS,
) -> dict[str, Any]:
    _validate_upstream(timing_receipt)
    if not isinstance(max_depth, int) or max_depth < 1 or max_depth > 1024:
        raise ValueError("max_depth must be between 1 and 1024")
    if not isinstance(sequence_seed, int) or sequence_seed < 0:
        raise ValueError("sequence_seed must be non-negative")
    if not isinstance(sequence_steps, int) or sequence_steps < 1:
        raise ValueError("sequence_steps must be positive")

    violations = 0
    matrix_scenarios = 0
    digest = hashlib.sha256()

    # Fixed matrix: fill, backpressure, queued cancellation, active cancellation,
    # completion recovery, disconnect invalidation, reconnect, and independent queues.
    tx = EndpointQueue("tx", max_depth=max_depth)
    ids: list[int] = []
    for _ in range(max_depth):
        status, transfer_id = tx.submit()
        violations += int(status not in {"active", "queued"} or transfer_id is None)
        if transfer_id is not None:
            ids.append(transfer_id)
        matrix_scenarios += 1
    status, _ = tx.submit()
    violations += int(status != "backpressure")
    matrix_scenarios += 1
    if len(ids) > 1:
        violations += int(tx.cancel(ids[-1]) != "queued-cancelled")
        matrix_scenarios += 1
    violations += int(tx.cancel(ids[0]) != "active-cancel-intent")
    matrix_scenarios += 1
    violations += int(tx.complete_active() != "cancelled-completion-quarantined")
    matrix_scenarios += 1
    status, _ = tx.submit()
    violations += int(status not in {"queued", "active"})
    matrix_scenarios += 1
    invalidated = tx.disconnect()
    violations += int(invalidated != tx.quarantined - 1)
    matrix_scenarios += 1
    status, _ = tx.submit()
    violations += int(status != "rejected-disconnected")
    matrix_scenarios += 1
    tx.reconnect()
    status, _ = tx.submit()
    violations += int(status != "active")
    matrix_scenarios += 1
    rx = EndpointQueue("rx", max_depth=max_depth)
    status, _ = rx.submit()
    violations += int(status != "active" or tx.depth != 1 or rx.depth != 1)
    matrix_scenarios += 1

    rng = random.Random(sequence_seed)
    queues = {direction: EndpointQueue(direction, max_depth=max_depth) for direction in DIRECTIONS}
    known_ids: dict[str, list[int]] = {direction: [] for direction in DIRECTIONS}
    operation_counts = {"submit": 0, "cancel": 0, "complete": 0, "disconnect": 0, "reconnect": 0, "backpressure": 0}
    max_observed_depth = {direction: 0 for direction in DIRECTIONS}

    for step in range(sequence_steps):
        direction = DIRECTIONS[rng.randrange(2)]
        queue = queues[direction]
        op = rng.randrange(100)
        if op < 52:
            status, transfer_id = queue.submit()
            operation_counts["submit"] += 1
            operation_counts["backpressure"] += int(status == "backpressure")
            if transfer_id is not None:
                known_ids[direction].append(transfer_id)
            digest.update(json.dumps([step, direction, "submit", status, transfer_id, queue.depth], separators=(",", ":")).encode("utf-8"))
        elif op < 68:
            candidates = known_ids[direction]
            transfer_id = candidates[rng.randrange(len(candidates))] if candidates else 1_000_000 + step
            status = queue.cancel(transfer_id)
            operation_counts["cancel"] += 1
            digest.update(json.dumps([step, direction, "cancel", transfer_id, status, queue.depth], separators=(",", ":")).encode("utf-8"))
        elif op < 85:
            status = queue.complete_active()
            operation_counts["complete"] += 1
            digest.update(json.dumps([step, direction, "complete", status, queue.depth], separators=(",", ":")).encode("utf-8"))
        elif op < 92:
            invalidated = queue.disconnect()
            operation_counts["disconnect"] += 1
            digest.update(json.dumps([step, direction, "disconnect", invalidated, queue.generation], separators=(",", ":")).encode("utf-8"))
        else:
            queue.reconnect()
            operation_counts["reconnect"] += 1
            digest.update(json.dumps([step, direction, "reconnect", queue.generation], separators=(",", ":")).encode("utf-8"))
        violations += queue.assert_invariants()
        max_observed_depth[direction] = max(max_observed_depth[direction], queue.depth)

    violations += sum(int(depth > max_depth) for depth in max_observed_depth.values())

    body: dict[str, Any] = {
        "schema": SCHEMA,
        "state": STATE if violations == 0 else "controlled-virtual-usb-queue-pressure-failed",
        "upstream_timing_receipt_sha256": timing_receipt["receipt_sha256"],
        "max_queue_depth": max_depth,
        "matrix_scenarios": matrix_scenarios,
        "deterministic_sequence_seed": sequence_seed,
        "deterministic_sequence_steps": sequence_steps,
        "scenario_count": matrix_scenarios + sequence_steps,
        "violation_count": violations,
        "operation_counts": operation_counts,
        "max_observed_depth": max_observed_depth,
        "trace_sha256": digest.hexdigest(),
        "queue_contract": {
            "queue_depth_bounded": True,
            "backpressure_fail_closed": True,
            "queued_cancel_removes_work": True,
            "active_cancel_is_intent_only": True,
            "cancelled_completion_quarantined": True,
            "disconnect_invalidates_outstanding_work": True,
            "reconnect_requires_fresh_submission": True,
            "tx_rx_queues_independent": True,
        },
        "invariants": {
            "live_pi_contacted": False,
            "usb_device_opened": False,
            "usb_transfer_submitted": False,
            "usb_cancel_submitted": False,
            "clear_halt_submitted": False,
            "register_access_performed": False,
            "wall_clock_or_sleep_used": False,
            "driver_binding_changed": False,
        },
        "authority": {key: False for key in _REQUIRED_FALSE},
        "strongest_claim": (
            "The sealed virtual USB timing model now has deterministic bounded queue-pressure and cancellation behavior: "
            "queue depth never exceeds its configured limit, saturation returns backpressure, queued cancellations remove "
            "work, active cancellation remains intent-only, cancelled/stale completions quarantine, and disconnect clears outstanding work."
        ),
        "next_safe_gate": "linux-usbnet-urb-lifecycle-reference-differential",
    }
    body["receipt_sha256"] = _canonical_sha256(body)
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timing-receipt", type=Path, required=True)
    parser.add_argument("--max-depth", type=int, default=DEFAULT_QUEUE_DEPTH)
    parser.add_argument("--sequence-seed", type=lambda value: int(value, 0), default=DEFAULT_SEQUENCE_SEED)
    parser.add_argument("--sequence-steps", type=int, default=DEFAULT_SEQUENCE_STEPS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    timing_receipt = json.loads(args.timing_receipt.read_text(encoding="utf-8"))
    receipt = run_queue_pressure_model(
        timing_receipt=timing_receipt,
        max_depth=args.max_depth,
        sequence_seed=args.sequence_seed,
        sequence_steps=args.sequence_steps,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["state"] == STATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
