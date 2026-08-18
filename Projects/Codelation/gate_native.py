from __future__ import annotations

import hashlib
import struct
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


VERSION = 1
ATOM_BYTES = 32
_HEADER = struct.Struct(">BII")
_U16 = struct.Struct(">H")


def atom(*parts: bytes) -> bytes:
    """Derive an opaque machine identity from binary material only."""
    h = hashlib.sha256()
    for part in parts:
        h.update(len(part).to_bytes(8, "big"))
        h.update(part)
    return h.digest()


def require_atom(value: bytes) -> bytes:
    value = bytes(value)
    if len(value) != ATOM_BYTES:
        raise ValueError("atom identity must be 32 bytes")
    return value


@dataclass(frozen=True, order=True)
class Gate:
    """Monotonic capability gate.

    Inputs and output are opaque 256-bit state identities. Evidence, authority,
    hardware observations, capabilities, and work readiness are all the same kind
    of machine state. A gate fires when every required input state exists.
    """

    inputs: tuple[bytes, ...]
    output: bytes

    def __post_init__(self) -> None:
        normalized = tuple(sorted({require_atom(item) for item in self.inputs}))
        if not normalized:
            raise ValueError("gate requires at least one input")
        object.__setattr__(self, "inputs", normalized)
        object.__setattr__(self, "output", require_atom(self.output))


class GateField:
    """Event-driven state/gate machine with canonical binary serialization."""

    def __init__(self, *, active: Iterable[bytes] = (), gates: Iterable[Gate] = ()) -> None:
        self.active = {require_atom(item) for item in active}
        self.gates = tuple(sorted(set(gates)))
        self._by_input: dict[bytes, list[Gate]] = defaultdict(list)
        for gate in self.gates:
            for item in gate.inputs:
                self._by_input[item].append(gate)

    def activate(self, *states: bytes) -> tuple[bytes, ...]:
        """Activate changed state and propagate only gates touched by that change."""
        queue: deque[bytes] = deque()
        newly_active: list[bytes] = []
        for state in states:
            state = require_atom(state)
            if state not in self.active:
                self.active.add(state)
                newly_active.append(state)
                queue.append(state)

        seen_gates: set[Gate] = set()
        while queue:
            changed = queue.popleft()
            for gate in self._by_input.get(changed, ()):
                if gate in seen_gates and gate.output in self.active:
                    continue
                seen_gates.add(gate)
                if gate.output not in self.active and all(item in self.active for item in gate.inputs):
                    self.active.add(gate.output)
                    newly_active.append(gate.output)
                    queue.append(gate.output)
        return tuple(newly_active)

    def is_active(self, state: bytes) -> bool:
        return require_atom(state) in self.active

    def with_gate(self, gate: Gate) -> "GateField":
        field = GateField(active=self.active, gates=(*self.gates, gate))
        # A newly introduced gate may already have satisfied inputs.
        if all(item in field.active for item in gate.inputs):
            field.activate(gate.output)
        return field

    def to_bytes(self) -> bytes:
        """Canonical state. No labels, JSON, paths, source language, or ASCII required."""
        active = sorted(self.active)
        gates = sorted(self.gates)
        out = bytearray(_HEADER.pack(VERSION, len(active), len(gates)))
        for state in active:
            out.extend(state)
        for gate in gates:
            if len(gate.inputs) > 65535:
                raise ValueError("gate fan-in exceeds binary format")
            out.extend(_U16.pack(len(gate.inputs)))
            for item in gate.inputs:
                out.extend(item)
            out.extend(gate.output)
        return bytes(out)

    @classmethod
    def from_bytes(cls, payload: bytes) -> "GateField":
        view = memoryview(payload)
        if len(view) < _HEADER.size:
            raise ValueError("truncated gate field")
        version, active_count, gate_count = _HEADER.unpack(view[: _HEADER.size])
        if version != VERSION:
            raise ValueError("unsupported gate field version")
        offset = _HEADER.size
        active: list[bytes] = []
        for _ in range(active_count):
            end = offset + ATOM_BYTES
            if end > len(view):
                raise ValueError("truncated active state")
            active.append(bytes(view[offset:end]))
            offset = end
        gates: list[Gate] = []
        for _ in range(gate_count):
            end = offset + _U16.size
            if end > len(view):
                raise ValueError("truncated gate input count")
            (input_count,) = _U16.unpack(view[offset:end])
            offset = end
            inputs: list[bytes] = []
            for _ in range(input_count):
                end = offset + ATOM_BYTES
                if end > len(view):
                    raise ValueError("truncated gate input")
                inputs.append(bytes(view[offset:end]))
                offset = end
            end = offset + ATOM_BYTES
            if end > len(view):
                raise ValueError("truncated gate output")
            output = bytes(view[offset:end])
            offset = end
            gates.append(Gate(tuple(inputs), output))
        if offset != len(view):
            raise ValueError("trailing bytes in gate field")
        return cls(active=active, gates=gates)

    def identity(self) -> bytes:
        return hashlib.sha256(self.to_bytes()).digest()

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_bytes(self.to_bytes())
        temporary.replace(path)

    @classmethod
    def read(cls, path: Path) -> "GateField":
        return cls.from_bytes(path.read_bytes())


def convergent_gate(inputs: Sequence[bytes], output: bytes) -> Gate:
    return Gate(tuple(inputs), output)
