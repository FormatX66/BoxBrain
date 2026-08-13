from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Sequence

from aurum_field import encode
from field_native_vm import (
    NativeExample,
    NativeProgram,
    NativeVerification,
    compile_native,
    verify_native,
)


CACHE_REVISION = "aurum-field-native-cache-v0"


@dataclass(frozen=True)
class NativeCacheResult:
    program: NativeProgram
    verification: NativeVerification
    compile_cache_hit: bool
    verification_cache_hit: bool


class NativeBuildCache:
    """Bounded identity cache for pure native compile/verification work.

    No clocks are semantic. Eviction follows deterministic insertion order.
    Cached verification is valid only for the exact VM-bound program identity and
    exact canonical example set.
    """

    def __init__(self, *, max_programs: int = 256, max_verifications: int = 512) -> None:
        if max_programs <= 0 or max_verifications <= 0:
            raise ValueError("cache bounds must be positive")
        self.max_programs = max_programs
        self.max_verifications = max_verifications
        self._programs: dict[str, NativeProgram] = {}
        self._verifications: dict[str, NativeVerification] = {}

    @staticmethod
    def request_identity(parameters: Sequence[str], expression: Mapping[str, Any]) -> str:
        payload = encode(
            {
                "revision": CACHE_REVISION,
                "parameters": list(parameters),
                "expression": dict(expression),
            }
        )
        return hashlib.blake2s(b"AURUM-NATIVE-COMPILE-REQUEST-0\x00" + payload).hexdigest()

    @staticmethod
    def verification_identity(program: NativeProgram, examples: Sequence[NativeExample]) -> str:
        payload = encode(
            {
                "program_identity": program.identity,
                "examples": [
                    {"arguments": dict(example.arguments), "expected": example.expected}
                    for example in examples
                ],
            }
        )
        return hashlib.blake2s(b"AURUM-NATIVE-VERIFY-REQUEST-0\x00" + payload).hexdigest()

    @staticmethod
    def _bounded_put(mapping: dict[str, Any], key: str, value: Any, limit: int) -> None:
        if key in mapping:
            mapping[key] = value
            return
        while len(mapping) >= limit:
            oldest = next(iter(mapping))
            del mapping[oldest]
        mapping[key] = value

    def resolve(
        self,
        parameters: Sequence[str],
        expression: Mapping[str, Any],
        examples: Sequence[NativeExample],
    ) -> NativeCacheResult:
        compile_key = self.request_identity(parameters, expression)
        program = self._programs.get(compile_key)
        compile_hit = program is not None
        if program is None:
            program = compile_native(parameters, expression)
            self._bounded_put(self._programs, compile_key, program, self.max_programs)

        verify_key = self.verification_identity(program, examples)
        verification = self._verifications.get(verify_key)
        verification_hit = verification is not None
        if verification is None:
            verification = verify_native(program, examples)
            self._bounded_put(
                self._verifications,
                verify_key,
                verification,
                self.max_verifications,
            )

        return NativeCacheResult(
            program=program,
            verification=verification,
            compile_cache_hit=compile_hit,
            verification_cache_hit=verification_hit,
        )

    def stats(self) -> Mapping[str, int]:
        return {
            "programs": len(self._programs),
            "verifications": len(self._verifications),
            "max_programs": self.max_programs,
            "max_verifications": self.max_verifications,
        }


__all__ = [
    "CACHE_REVISION",
    "NativeBuildCache",
    "NativeCacheResult",
]
