from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re


CONTEXT_STATE_SCHEMA = "aurum.context.exchange.v1"
ZERO_CHAIN_SHA256 = "0" * 64
MAX_CONTEXT_ID_CHARS = 64
_CONTEXT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ContextState:
    schema: str
    context_id: str
    sequence: int
    input_sha256: str
    output_sha256: str
    previous_chain_sha256: str
    chain_sha256: str


def _validate_context_id(value: object) -> str:
    if not isinstance(value, str) or _CONTEXT_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("context id is invalid")
    return value


def _validate_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} is not a lowercase SHA-256 digest")
    return value


def _chain_digest(
    previous_chain_sha256: str,
    context_id: str,
    sequence: int,
    input_sha256: str,
    output_sha256: str,
) -> str:
    payload = "\0".join(
        (
            CONTEXT_STATE_SCHEMA,
            previous_chain_sha256,
            context_id,
            str(sequence),
            input_sha256,
            output_sha256,
        )
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_context_state(value: object) -> ContextState:
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "context_id",
        "sequence",
        "input_sha256",
        "output_sha256",
        "previous_chain_sha256",
        "chain_sha256",
    }:
        raise ValueError("context state does not match the bounded schema")
    if value.get("schema") != CONTEXT_STATE_SCHEMA:
        raise ValueError("context state schema mismatch")
    context_id = _validate_context_id(value.get("context_id"))
    sequence = value.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise ValueError("context sequence is invalid")
    input_sha256 = _validate_digest(value.get("input_sha256"), "input digest")
    output_sha256 = _validate_digest(value.get("output_sha256"), "output digest")
    previous_chain_sha256 = _validate_digest(
        value.get("previous_chain_sha256"), "previous chain digest"
    )
    chain_sha256 = _validate_digest(value.get("chain_sha256"), "chain digest")
    if sequence == 1 and previous_chain_sha256 != ZERO_CHAIN_SHA256:
        raise ValueError("initial context state has a nonzero predecessor")
    expected_chain = _chain_digest(
        previous_chain_sha256,
        context_id,
        sequence,
        input_sha256,
        output_sha256,
    )
    if chain_sha256 != expected_chain:
        raise ValueError("context state integrity check failed")
    return ContextState(
        schema=CONTEXT_STATE_SCHEMA,
        context_id=context_id,
        sequence=sequence,
        input_sha256=input_sha256,
        output_sha256=output_sha256,
        previous_chain_sha256=previous_chain_sha256,
        chain_sha256=chain_sha256,
    )


def serialize_context_state(state: ContextState) -> str:
    validate_context_state(asdict(state))
    return json.dumps(asdict(state), sort_keys=True, separators=(",", ":"))


def parse_context_state(raw: str) -> ContextState:
    if not isinstance(raw, str) or not raw:
        raise ValueError("context state is empty")
    if len(raw) > 1024:
        raise ValueError("context state exceeded its bound")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("context state is not valid JSON") from exc
    return validate_context_state(value)


def advance_context_state(
    prior_state: str | None,
    *,
    context_id: str,
    sequence: int,
    input_sha256: str,
    output_sha256: str,
) -> str:
    """Advance a content-free, integrity-linked exchange envelope.

    The envelope deliberately stores only correlation metadata and SHA-256
    digests. It does not store prompts, responses, credentials, or machine
    authority. A serialized envelope can be loaded after restart so sequence
    loss, replay, context mixing, or corruption is detected rather than
    silently accepted.
    """
    context_id = _validate_context_id(context_id)
    input_sha256 = _validate_digest(input_sha256, "input digest")
    output_sha256 = _validate_digest(output_sha256, "output digest")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise ValueError("context sequence is invalid")

    if prior_state in (None, ""):
        if sequence != 1:
            raise ValueError("new context must start at sequence 1")
        previous_chain_sha256 = ZERO_CHAIN_SHA256
    else:
        prior = parse_context_state(prior_state)
        if prior.context_id != context_id:
            raise ValueError("context isolation mismatch")
        if sequence != prior.sequence + 1:
            raise ValueError("context sequence is not monotonic")
        previous_chain_sha256 = prior.chain_sha256

    state = ContextState(
        schema=CONTEXT_STATE_SCHEMA,
        context_id=context_id,
        sequence=sequence,
        input_sha256=input_sha256,
        output_sha256=output_sha256,
        previous_chain_sha256=previous_chain_sha256,
        chain_sha256=_chain_digest(
            previous_chain_sha256,
            context_id,
            sequence,
            input_sha256,
            output_sha256,
        ),
    )
    return serialize_context_state(state)


__all__ = [
    "CONTEXT_STATE_SCHEMA",
    "ContextState",
    "advance_context_state",
    "parse_context_state",
    "serialize_context_state",
    "validate_context_state",
]
