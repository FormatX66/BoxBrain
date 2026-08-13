from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable, Mapping

from aurum_field import Field, encode
from field_native_vm import NativeInstruction, NativeProgram, VM_REVISION


BUNDLE_REVISION = "aurum-field-native-bundle-v0"


class NativeBundleError(ValueError):
    pass


@dataclass(frozen=True)
class NativeBundleEntry:
    name: str
    program_identity: str
    tape_identity: str
    parameters: tuple[str, ...]
    tape: tuple[NativeInstruction, ...]

    def program(self) -> NativeProgram:
        return NativeProgram(
            identity=self.program_identity,
            tape_identity=self.tape_identity,
            parameters=self.parameters,
            tape=self.tape,
        )


@dataclass(frozen=True)
class NativeProgramBundle:
    carrier: bytes
    carrier_sha256: str
    field_id: str
    entries: tuple[NativeBundleEntry, ...]


def _tape_value(program: NativeProgram) -> list[list[Any]]:
    return [[instruction.opcode, instruction.argument] for instruction in program.tape]


def _tape_identity(tape: list[list[Any]]) -> str:
    return hashlib.blake2s(b"AURUM-NATIVE-TAPE-0\x00" + encode(tape)).hexdigest()


def make_native_bundle(programs: Mapping[str, NativeProgram]) -> NativeProgramBundle:
    if not programs:
        raise NativeBundleError("native bundle requires at least one program")
    field = Field()
    refs = []
    entries: list[NativeBundleEntry] = []
    for name, program in sorted(programs.items()):
        if not name:
            raise NativeBundleError("native bundle entry requires name")
        tape = _tape_value(program)
        if _tape_identity(tape) != program.tape_identity:
            raise NativeBundleError(f"tape identity mismatch for {name}")
        refs.append(
            field.add(
                "capability",
                {
                    "kind": "field-native-bundle-entry",
                    "bundle_revision": BUNDLE_REVISION,
                    "vm_revision": VM_REVISION,
                    "name": name,
                    "program_identity": program.identity,
                    "tape_identity": program.tape_identity,
                    "parameters": list(program.parameters),
                    "tape": tape,
                    "local_variant": True,
                    "copy_to_other_nodes": False,
                },
            )
        )
        entries.append(
            NativeBundleEntry(
                name=name,
                program_identity=program.identity,
                tape_identity=program.tape_identity,
                parameters=program.parameters,
                tape=program.tape,
            )
        )
    field.add(
        "view",
        {
            "name": "aurum-field-native-bundle",
            "bundle_revision": BUNDLE_REVISION,
            "entries": refs,
            "entry_names": [entry.name for entry in entries],
            "shared_implementation": False,
        },
    )
    carrier = field.project()
    return NativeProgramBundle(
        carrier=carrier,
        carrier_sha256=hashlib.sha256(carrier).hexdigest(),
        field_id=field.hex_id,
        entries=tuple(entries),
    )


def restore_native_bundle(carrier: bytes) -> NativeProgramBundle:
    field = Field.absorb(carrier)
    if field.project() != carrier:
        raise NativeBundleError("bundle is not canonical Field projection")
    entries: list[NativeBundleEntry] = []
    seen: set[str] = set()
    for identity in field.identities():
        grain = field.get(identity)
        value = grain.value
        if not (
            grain.kind == 3
            and isinstance(value, Mapping)
            and value.get("kind") == "field-native-bundle-entry"
        ):
            continue
        if value.get("bundle_revision") != BUNDLE_REVISION or value.get("vm_revision") != VM_REVISION:
            raise NativeBundleError("bundle entry revision mismatch")
        name = str(value.get("name", ""))
        if not name or name in seen:
            raise NativeBundleError("invalid or duplicate bundle entry name")
        seen.add(name)
        parameters = value.get("parameters")
        tape_raw = value.get("tape")
        if not isinstance(parameters, list) or not all(isinstance(item, str) for item in parameters):
            raise NativeBundleError("invalid bundle parameters")
        if not isinstance(tape_raw, list):
            raise NativeBundleError("invalid bundle tape")
        instructions: list[NativeInstruction] = []
        tape_value: list[list[Any]] = []
        for row in tape_raw:
            if not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], int):
                raise NativeBundleError("invalid bundle instruction")
            tape_value.append([row[0], row[1]])
            instructions.append(NativeInstruction(row[0], row[1]))
        tape_identity = str(value.get("tape_identity", ""))
        if not tape_identity or _tape_identity(tape_value) != tape_identity:
            raise NativeBundleError("bundle tape identity mismatch")
        program_identity = str(value.get("program_identity", ""))
        if not program_identity:
            raise NativeBundleError("bundle program identity missing")
        entries.append(
            NativeBundleEntry(
                name=name,
                program_identity=program_identity,
                tape_identity=tape_identity,
                parameters=tuple(parameters),
                tape=tuple(instructions),
            )
        )
    if not entries:
        raise NativeBundleError("bundle contains no native entries")
    ordered = tuple(sorted(entries, key=lambda entry: entry.name))
    return NativeProgramBundle(
        carrier=carrier,
        carrier_sha256=hashlib.sha256(carrier).hexdigest(),
        field_id=field.hex_id,
        entries=ordered,
    )


def bundle_programs(bundle: NativeProgramBundle) -> Mapping[str, NativeProgram]:
    return {entry.name: entry.program() for entry in bundle.entries}


__all__ = [
    "BUNDLE_REVISION",
    "NativeBundleEntry",
    "NativeBundleError",
    "NativeProgramBundle",
    "bundle_programs",
    "make_native_bundle",
    "restore_native_bundle",
]
