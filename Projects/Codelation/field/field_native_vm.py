from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Sequence

from aurum_field import encode


VM_REVISION = "aurum-field-native-vm-v0"


class NativeVMError(ValueError):
    pass


# Compact stable opcodes. They are Aurum's bounded internal operation vocabulary,
# not Python/source-language ownership.
OP_INPUT = 1
OP_STRIP = 2
OP_CASEFOLD = 3
OP_SPLIT = 4
OP_UNIQUE = 5
OP_SORT = 6
OP_JOIN = 7
OP_LENGTH = 8
OP_SYMMETRIC_DIFFERENCE = 9
OP_INTERSECTION = 10
OP_UNION = 11
OP_SAFE_DIVIDE = 12

_NAME_TO_OPCODE = {
    "input": OP_INPUT,
    "strip": OP_STRIP,
    "casefold": OP_CASEFOLD,
    "split": OP_SPLIT,
    "unique": OP_UNIQUE,
    "sort": OP_SORT,
    "join": OP_JOIN,
    "length": OP_LENGTH,
    "symmetric_difference": OP_SYMMETRIC_DIFFERENCE,
    "intersection": OP_INTERSECTION,
    "union": OP_UNION,
    "safe_divide": OP_SAFE_DIVIDE,
}


@dataclass(frozen=True)
class NativeInstruction:
    opcode: int
    argument: Any = None


@dataclass(frozen=True)
class NativeProgram:
    identity: str
    tape_identity: str
    parameters: tuple[str, ...]
    tape: tuple[NativeInstruction, ...]


@dataclass(frozen=True)
class NativeExample:
    arguments: Mapping[str, Any]
    expected: Any


@dataclass(frozen=True)
class NativeVerification:
    program_identity: str
    tape_identity: str
    examples: int
    passed: int
    verified: bool


def _program_identity(parameters: Sequence[str], expression: Mapping[str, Any]) -> str:
    body = encode({"revision": VM_REVISION, "parameters": list(parameters), "expression": dict(expression)})
    return hashlib.blake2s(b"AURUM-NATIVE-PROGRAM-0\x00" + body).hexdigest()


def _emit(expression: Mapping[str, Any], parameters: frozenset[str], out: list[NativeInstruction]) -> None:
    op_name = str(expression.get("op", ""))
    try:
        opcode = _NAME_TO_OPCODE[op_name]
    except KeyError as exc:
        raise NativeVMError(f"unsupported native operation: {op_name}") from exc

    if opcode == OP_INPUT:
        name = str(expression.get("name", ""))
        if name not in parameters:
            raise NativeVMError(f"unknown input: {name}")
        out.append(NativeInstruction(OP_INPUT, name))
        return

    if opcode in {OP_SYMMETRIC_DIFFERENCE, OP_INTERSECTION, OP_UNION, OP_SAFE_DIVIDE}:
        left = expression.get("left")
        right = expression.get("right")
        if not isinstance(left, Mapping) or not isinstance(right, Mapping):
            raise NativeVMError(f"{op_name} requires left and right expressions")
        _emit(left, parameters, out)
        _emit(right, parameters, out)
        out.append(NativeInstruction(opcode))
        return

    value = expression.get("value")
    if not isinstance(value, Mapping):
        raise NativeVMError(f"{op_name} requires value expression")
    _emit(value, parameters, out)
    if opcode == OP_JOIN:
        separator = expression.get("separator", "")
        if not isinstance(separator, str):
            raise NativeVMError("join separator must be text")
        out.append(NativeInstruction(opcode, separator))
    else:
        out.append(NativeInstruction(opcode))


def compile_native(parameters: Sequence[str], expression: Mapping[str, Any]) -> NativeProgram:
    if not parameters or len(set(parameters)) != len(parameters):
        raise NativeVMError("parameters must be non-empty and unique")
    tape: list[NativeInstruction] = []
    _emit(expression, frozenset(parameters), tape)
    tape_value = [[instruction.opcode, instruction.argument] for instruction in tape]
    tape_identity = hashlib.blake2s(
        b"AURUM-NATIVE-TAPE-0\x00" + encode(tape_value)
    ).hexdigest()
    return NativeProgram(
        identity=_program_identity(parameters, expression),
        tape_identity=tape_identity,
        parameters=tuple(parameters),
        tape=tuple(tape),
    )


def _as_set(value: Any) -> set[Any]:
    if isinstance(value, str):
        return set(value.split())
    if isinstance(value, (list, tuple, set, frozenset)):
        return set(value)
    raise NativeVMError("set operation requires text or collection")


def execute_native(program: NativeProgram, arguments: Mapping[str, Any]) -> Any:
    if set(arguments) != set(program.parameters):
        raise NativeVMError("arguments do not match program parameters")
    stack: list[Any] = []
    for instruction in program.tape:
        op = instruction.opcode
        if op == OP_INPUT:
            stack.append(arguments[str(instruction.argument)])
        elif op == OP_STRIP:
            stack.append(str(stack.pop()).strip())
        elif op == OP_CASEFOLD:
            stack.append(str(stack.pop()).casefold())
        elif op == OP_SPLIT:
            stack.append(str(stack.pop()).split())
        elif op == OP_UNIQUE:
            stack.append(list(dict.fromkeys(stack.pop())))
        elif op == OP_SORT:
            stack.append(sorted(stack.pop()))
        elif op == OP_JOIN:
            stack.append(str(instruction.argument).join(stack.pop()))
        elif op == OP_LENGTH:
            stack.append(len(stack.pop()))
        elif op in {OP_SYMMETRIC_DIFFERENCE, OP_INTERSECTION, OP_UNION}:
            right = _as_set(stack.pop())
            left = _as_set(stack.pop())
            if op == OP_SYMMETRIC_DIFFERENCE:
                stack.append(sorted(left.symmetric_difference(right)))
            elif op == OP_INTERSECTION:
                stack.append(sorted(left.intersection(right)))
            else:
                stack.append(sorted(left.union(right)))
        elif op == OP_SAFE_DIVIDE:
            right = stack.pop()
            left = stack.pop()
            if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
                raise NativeVMError("safe_divide requires numbers")
            stack.append(0 if right == 0 else left / right)
        else:
            raise NativeVMError(f"unknown opcode: {op}")
    if len(stack) != 1:
        raise NativeVMError("native program did not converge to one value")
    return stack[0]


def verify_native(program: NativeProgram, examples: Sequence[NativeExample]) -> NativeVerification:
    if not examples:
        raise NativeVMError("verification requires examples")
    passed = 0
    for example in examples:
        if execute_native(program, example.arguments) == example.expected:
            passed += 1
    return NativeVerification(
        program_identity=program.identity,
        tape_identity=program.tape_identity,
        examples=len(examples),
        passed=passed,
        verified=passed == len(examples),
    )


def native_capability_field_value(
    *,
    name: str,
    program: NativeProgram,
    verification: NativeVerification,
) -> Mapping[str, Any]:
    return {
        "name": name,
        "representation": VM_REVISION,
        "program_identity": program.identity,
        "tape_identity": program.tape_identity,
        "parameters": list(program.parameters),
        "opcodes": [instruction.opcode for instruction in program.tape],
        "verified": verification.verified,
        "examples": verification.examples,
        "passed": verification.passed,
        "source_generation_required": False,
        "filesystem_build_required": False,
        "subprocess_test_required": False,
    }


__all__ = [
    "NativeExample",
    "NativeInstruction",
    "NativeProgram",
    "NativeVMError",
    "NativeVerification",
    "VM_REVISION",
    "compile_native",
    "execute_native",
    "native_capability_field_value",
    "verify_native",
]
