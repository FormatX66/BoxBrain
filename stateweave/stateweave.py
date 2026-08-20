from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import heapq
import struct
from typing import Iterable, Mapping, Sequence

MAGIC = b"SWV1"

OP_EQ = 0
OP_NE = 1
OP_LT = 2
OP_LE = 3
OP_GT = 4
OP_GE = 5

MODE_SET = 0
MODE_ADD = 1


@dataclass(frozen=True, slots=True)
class Predicate:
    node: int
    op: int
    value: int

    def holds(self, state: Mapping[int, int]) -> bool:
        actual = state.get(self.node, 0)
        if self.op == OP_EQ:
            return actual == self.value
        if self.op == OP_NE:
            return actual != self.value
        if self.op == OP_LT:
            return actual < self.value
        if self.op == OP_LE:
            return actual <= self.value
        if self.op == OP_GT:
            return actual > self.value
        if self.op == OP_GE:
            return actual >= self.value
        raise ValueError(f"unknown predicate op {self.op}")


@dataclass(frozen=True, slots=True)
class Effect:
    node: int
    mode: int
    value: int

    def apply(self, state: dict[int, int]) -> None:
        if self.mode == MODE_SET:
            state[self.node] = self.value
            return
        if self.mode == MODE_ADD:
            state[self.node] = state.get(self.node, 0) + self.value
            return
        raise ValueError(f"unknown effect mode {self.mode}")


@dataclass(frozen=True, slots=True)
class Transition:
    transition_id: int
    cost: int
    preconditions: tuple[Predicate, ...]
    effects: tuple[Effect, ...]
    reversible: bool = False

    def enabled(self, state: Mapping[int, int]) -> bool:
        return all(p.holds(state) for p in self.preconditions)

    def apply(self, state: Mapping[int, int]) -> dict[int, int]:
        out = dict(state)
        for effect in self.effects:
            effect.apply(out)
        return out


@dataclass(frozen=True, slots=True)
class Receipt:
    transition_id: int
    before_hash: str
    after_hash: str


@dataclass(frozen=True, slots=True)
class Weave:
    state: Mapping[int, int]
    goals: tuple[Predicate, ...]
    invariants: tuple[Predicate, ...]
    transitions: tuple[Transition, ...]

    def goals_hold(self, state: Mapping[int, int]) -> bool:
        return all(p.holds(state) for p in self.goals)

    def invariants_hold(self, state: Mapping[int, int]) -> bool:
        return all(p.holds(state) for p in self.invariants)

    def plan(self, max_expansions: int = 10000) -> tuple[Transition, ...]:
        """Find the lowest-cost valid transition path using Dijkstra search."""
        start = _state_key(self.state)
        if self.goals_hold(dict(start)):
            return ()
        if not self.invariants_hold(dict(start)):
            raise ValueError("initial state violates invariant")

        frontier: list[tuple[int, int, tuple[tuple[int, int], ...], tuple[int, ...]]] = []
        serial = 0
        heapq.heappush(frontier, (0, serial, start, ()))
        best_cost = {start: 0}
        by_id = {t.transition_id: t for t in self.transitions}
        expansions = 0

        while frontier:
            cost, _, state_key, path_ids = heapq.heappop(frontier)
            if cost != best_cost.get(state_key):
                continue
            state = dict(state_key)
            if self.goals_hold(state):
                return tuple(by_id[i] for i in path_ids)

            expansions += 1
            if expansions > max_expansions:
                raise RuntimeError("planning expansion limit reached")

            for transition in self.transitions:
                if not transition.enabled(state):
                    continue
                next_state = transition.apply(state)
                if not self.invariants_hold(next_state):
                    continue
                next_key = _state_key(next_state)
                next_cost = cost + transition.cost
                if next_cost < best_cost.get(next_key, 2**63 - 1):
                    best_cost[next_key] = next_cost
                    serial += 1
                    heapq.heappush(
                        frontier,
                        (next_cost, serial, next_key, path_ids + (transition.transition_id,)),
                    )
        raise RuntimeError("no valid plan")

    def execute(self, plan: Sequence[Transition]) -> tuple[dict[int, int], tuple[Receipt, ...]]:
        state = dict(self.state)
        receipts: list[Receipt] = []
        for transition in plan:
            if not transition.enabled(state):
                raise RuntimeError(f"transition {transition.transition_id} not enabled")
            before = _state_digest(state)
            next_state = transition.apply(state)
            if not self.invariants_hold(next_state):
                raise RuntimeError(f"transition {transition.transition_id} violates invariant")
            after = _state_digest(next_state)
            receipts.append(Receipt(transition.transition_id, before, after))
            state = next_state
        if not self.goals_hold(state):
            raise RuntimeError("plan completed without satisfying goals")
        return state, tuple(receipts)

    def to_bytes(self) -> bytes:
        out = bytearray(MAGIC)
        _write_state(out, self.state)
        _write_predicates(out, self.goals)
        _write_predicates(out, self.invariants)
        out += struct.pack("<I", len(self.transitions))
        for transition in sorted(self.transitions, key=lambda x: x.transition_id):
            flags = 1 if transition.reversible else 0
            out += struct.pack("<IIB", transition.transition_id, transition.cost, flags)
            _write_predicates(out, transition.preconditions)
            out += struct.pack("<I", len(transition.effects))
            for effect in transition.effects:
                out += struct.pack("<IBq", effect.node, effect.mode, effect.value)
        return bytes(out)

    @classmethod
    def from_bytes(cls, data: bytes) -> "Weave":
        view = memoryview(data)
        if len(view) < 4 or bytes(view[:4]) != MAGIC:
            raise ValueError("invalid StateWeave magic")
        pos = 4
        state, pos = _read_state(view, pos)
        goals, pos = _read_predicates(view, pos)
        invariants, pos = _read_predicates(view, pos)
        count, pos = _read_u32(view, pos)
        transitions: list[Transition] = []
        for _ in range(count):
            transition_id, pos = _read_u32(view, pos)
            cost, pos = _read_u32(view, pos)
            flags, pos = _read_u8(view, pos)
            preconditions, pos = _read_predicates(view, pos)
            effect_count, pos = _read_u32(view, pos)
            effects: list[Effect] = []
            for _ in range(effect_count):
                node, pos = _read_u32(view, pos)
                mode, pos = _read_u8(view, pos)
                value, pos = _read_i64(view, pos)
                effects.append(Effect(node, mode, value))
            transitions.append(
                Transition(
                    transition_id=transition_id,
                    cost=cost,
                    preconditions=preconditions,
                    effects=tuple(effects),
                    reversible=bool(flags & 1),
                )
            )
        if pos != len(view):
            raise ValueError("trailing bytes in StateWeave payload")
        return cls(state, goals, invariants, tuple(transitions))


def _state_key(state: Mapping[int, int]) -> tuple[tuple[int, int], ...]:
    return tuple(sorted((int(key), int(value)) for key, value in state.items()))


def _state_digest(state: Mapping[int, int]) -> str:
    payload = bytearray()
    _write_state(payload, state)
    return sha256(payload).hexdigest()


def _write_state(out: bytearray, state: Mapping[int, int]) -> None:
    items = _state_key(state)
    out += struct.pack("<I", len(items))
    for node, value in items:
        out += struct.pack("<Iq", node, value)


def _write_predicates(out: bytearray, predicates: Iterable[Predicate]) -> None:
    items = tuple(predicates)
    out += struct.pack("<I", len(items))
    for predicate in items:
        out += struct.pack("<IBq", predicate.node, predicate.op, predicate.value)


def _read_exact(view: memoryview, pos: int, size: int) -> tuple[memoryview, int]:
    end = pos + size
    if end > len(view):
        raise ValueError("truncated StateWeave payload")
    return view[pos:end], end


def _read_u32(view: memoryview, pos: int) -> tuple[int, int]:
    chunk, pos = _read_exact(view, pos, 4)
    return struct.unpack("<I", chunk)[0], pos


def _read_u8(view: memoryview, pos: int) -> tuple[int, int]:
    chunk, pos = _read_exact(view, pos, 1)
    return struct.unpack("<B", chunk)[0], pos


def _read_i64(view: memoryview, pos: int) -> tuple[int, int]:
    chunk, pos = _read_exact(view, pos, 8)
    return struct.unpack("<q", chunk)[0], pos


def _read_state(view: memoryview, pos: int) -> tuple[dict[int, int], int]:
    count, pos = _read_u32(view, pos)
    state: dict[int, int] = {}
    for _ in range(count):
        node, pos = _read_u32(view, pos)
        value, pos = _read_i64(view, pos)
        if node in state:
            raise ValueError("duplicate state node")
        state[node] = value
    return state, pos


def _read_predicates(view: memoryview, pos: int) -> tuple[tuple[Predicate, ...], int]:
    count, pos = _read_u32(view, pos)
    items: list[Predicate] = []
    for _ in range(count):
        node, pos = _read_u32(view, pos)
        op, pos = _read_u8(view, pos)
        value, pos = _read_i64(view, pos)
        items.append(Predicate(node, op, value))
    return tuple(items), pos
