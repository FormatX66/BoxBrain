from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

from aurum_field import Field, Ref, encode
from field_native_vm import NativeInstruction, NativeProgram, VM_REVISION


CARRIER_REVISION = "aurum-field-native-carrier-v0"


class NativeCarrierError(ValueError):
    pass


@dataclass(frozen=True)
class NativeProgramCarrier:
    carrier: bytes
    carrier_sha256: str
    field_id: str
    program_identity: str
    tape_identity: str


def _tape_value(program: NativeProgram) -> list[list[Any]]:
    return [[instruction.opcode, instruction.argument] for instruction in program.tape]


def _tape_identity(tape: list[list[Any]]) -> str:
    return hashlib.blake2s(
        b"AURUM-NATIVE-TAPE-0\x00" + encode(tape)
    ).hexdigest()


def make_native_program_carrier(program: NativeProgram) -> NativeProgramCarrier:
    """Persist one native program as a canonical Field carrier.

    The carrier contains the local VM tape and identities only. It is a local
    capability carrier, not a cluster-wide implementation template.
    """
    tape = _tape_value(program)
    if _tape_identity(tape) != program.tape_identity:
        raise NativeCarrierError("native program tape identity mismatch")

    field = Field()
    program_ref = field.add(
        "capability",
        {
            "kind": "field-native-program-carrier",
            "carrier_revision": CARRIER_REVISION,
            "vm_revision": VM_REVISION,
            "program_identity": program.identity,
            "tape_identity": program.tape_identity,
            "parameters": list(program.parameters),
            "tape": tape,
            "local_variant": True,
            "copy_to_other_nodes": False,
        },
    )
    field.add(
        "view",
        {
            "name": "aurum-field-native-program-carrier",
            "program": program_ref,
            "program_identity": program.identity,
            "tape_identity": program.tape_identity,
        },
    )
    carrier = field.project()
    return NativeProgramCarrier(
        carrier=carrier,
        carrier_sha256=hashlib.sha256(carrier).hexdigest(),
        field_id=field.hex_id,
        program_identity=program.identity,
        tape_identity=program.tape_identity,
    )


def _program_record(field: Field) -> Mapping[str, Any]:
    matches: list[Mapping[str, Any]] = []
    for identity in field.identities():
        grain = field.get(identity)
        value = grain.value
        if (
            grain.kind == 3
            and isinstance(value, Mapping)
            and value.get("kind") == "field-native-program-carrier"
        ):
            matches.append(value)
    if len(matches) != 1:
        raise NativeCarrierError("carrier must contain exactly one native program")
    return matches[0]


def restore_native_program(carrier: bytes) -> NativeProgram:
    """Restore and verify a native VM program from canonical Field bytes."""
    field = Field.absorb(carrier)
    if field.project() != carrier:
        raise NativeCarrierError("carrier is not canonical Field projection")
    value = _program_record(field)
    if value.get("carrier_revision") != CARRIER_REVISION:
        raise NativeCarrierError("unsupported native carrier revision")
    if value.get("vm_revision") != VM_REVISION:
        raise NativeCarrierError("native carrier VM revision mismatch")

    parameters_raw = value.get("parameters")
    tape_raw = value.get("tape")
    if not isinstance(parameters_raw, list) or not all(isinstance(item, str) for item in parameters_raw):
        raise NativeCarrierError("invalid native carrier parameters")
    if not isinstance(tape_raw, list):
        raise NativeCarrierError("invalid native carrier tape")

    tape_value: list[list[Any]] = []
    instructions: list[NativeInstruction] = []
    for row in tape_raw:
        if not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], int):
            raise NativeCarrierError("invalid native carrier instruction")
        tape_value.append([row[0], row[1]])
        instructions.append(NativeInstruction(row[0], row[1]))

    expected_tape_identity = str(value.get("tape_identity", ""))
    if not expected_tape_identity or _tape_identity(tape_value) != expected_tape_identity:
        raise NativeCarrierError("native carrier tape digest mismatch")
    program_identity = str(value.get("program_identity", ""))
    if not program_identity:
        raise NativeCarrierError("native carrier program identity missing")

    return NativeProgram(
        identity=program_identity,
        tape_identity=expected_tape_identity,
        parameters=tuple(parameters_raw),
        tape=tuple(instructions),
    )


def verify_native_program_carrier(
    carrier: bytes,
    *,
    expected_sha256: str | None = None,
    expected_program_identity: str | None = None,
    expected_tape_identity: str | None = None,
) -> NativeProgram:
    observed_sha256 = hashlib.sha256(carrier).hexdigest()
    if expected_sha256 is not None and observed_sha256 != expected_sha256:
        raise NativeCarrierError("native carrier SHA-256 mismatch")
    program = restore_native_program(carrier)
    if expected_program_identity is not None and program.identity != expected_program_identity:
        raise NativeCarrierError("native carrier program identity mismatch")
    if expected_tape_identity is not None and program.tape_identity != expected_tape_identity:
        raise NativeCarrierError("native carrier tape identity mismatch")
    return program


__all__ = [
    "CARRIER_REVISION",
    "NativeCarrierError",
    "NativeProgramCarrier",
    "make_native_program_carrier",
    "restore_native_program",
    "verify_native_program_carrier",
]
