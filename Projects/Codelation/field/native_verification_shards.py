from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from aurum_field import Field, encode
from field_native_vm import NativeExample
from native_example_set import canonicalize_examples


SHARD_REVISION = "aurum-native-verification-shards-v0"


@dataclass(frozen=True)
class VerificationShard:
    index: int
    identity: str
    examples: tuple[NativeExample, ...]


@dataclass(frozen=True)
class VerificationShardPlan:
    identity: str
    shards: tuple[VerificationShard, ...]
    input_examples: int
    unique_examples: int
    duplicate_examples_removed: int
    requested_shards: int


def _example_bytes(example: NativeExample) -> bytes:
    return encode({"arguments": dict(example.arguments), "expected": example.expected})


def plan_verification_shards(
    examples: Iterable[NativeExample],
    *,
    requested_shards: int,
) -> VerificationShardPlan:
    """Partition unique native examples deterministically across independent cells."""
    if requested_shards <= 0:
        raise ValueError("requested_shards must be positive")
    canonical = canonicalize_examples(examples)
    buckets: list[list[NativeExample]] = [[] for _ in range(requested_shards)]
    for example in canonical.examples:
        digest = hashlib.blake2s(
            b"AURUM-NATIVE-VERIFY-EXAMPLE-0\x00" + _example_bytes(example),
            digest_size=8,
        ).digest()
        bucket = int.from_bytes(digest, "big") % requested_shards
        buckets[bucket].append(example)

    shards: list[VerificationShard] = []
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        ordered = tuple(sorted(bucket, key=_example_bytes))
        identity = hashlib.blake2s(
            b"AURUM-NATIVE-VERIFY-SHARD-0\x00"
            + encode(
                {
                    "revision": SHARD_REVISION,
                    "index": index,
                    "examples": [
                        {"arguments": dict(example.arguments), "expected": example.expected}
                        for example in ordered
                    ],
                }
            )
        ).hexdigest()
        shards.append(VerificationShard(index=index, identity=identity, examples=ordered))

    plan_identity = hashlib.blake2s(
        b"AURUM-NATIVE-VERIFY-SHARD-PLAN-0\x00"
        + encode(
            {
                "revision": SHARD_REVISION,
                "requested_shards": requested_shards,
                "example_set_identity": canonical.identity,
                "shards": [[shard.index, shard.identity] for shard in shards],
            }
        )
    ).hexdigest()
    return VerificationShardPlan(
        identity=plan_identity,
        shards=tuple(shards),
        input_examples=canonical.input_examples,
        unique_examples=len(canonical.examples),
        duplicate_examples_removed=canonical.duplicate_examples_removed,
        requested_shards=requested_shards,
    )


def verification_shard_field(plan: VerificationShardPlan) -> Field:
    field = Field()
    refs = []
    for shard in plan.shards:
        refs.append(
            field.add(
                "fact",
                {
                    "kind": "native-verification-shard",
                    "plan_identity": plan.identity,
                    "index": shard.index,
                    "identity": shard.identity,
                    "examples": len(shard.examples),
                },
            )
        )
    field.add(
        "view",
        {
            "name": "aurum-native-verification-shards",
            "plan_identity": plan.identity,
            "shards": refs,
            "input_examples": plan.input_examples,
            "unique_examples": plan.unique_examples,
            "duplicate_examples_removed": plan.duplicate_examples_removed,
            "requested_shards": plan.requested_shards,
            "model_reasoning_required": False,
        },
    )
    return field


__all__ = [
    "SHARD_REVISION",
    "VerificationShard",
    "VerificationShardPlan",
    "plan_verification_shards",
    "verification_shard_field",
]
