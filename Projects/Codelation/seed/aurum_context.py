from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

FIELD_DIR = Path(__file__).resolve().parents[1] / "field"
if str(FIELD_DIR) not in sys.path:
    sys.path.insert(0, str(FIELD_DIR))

from context_exchange import advance_context_state, parse_context_state  # noqa: E402

MAX_PRIOR_TURNS = 6
MAX_TURN_CHARS = 12_000
MAX_CONTEXT_CHARS = 36_000

Reasoner = Callable[[list[dict[str, Any]], str, str], tuple[str, str | None]]


@dataclass(frozen=True)
class SemanticTurn:
    prompt: str
    response: str


def _input_message(role: str, text: str) -> dict[str, Any]:
    return {"role": role, "content": [{"type": "input_text", "text": text}]}


def _validate_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is empty")
    if len(value) > MAX_TURN_CHARS:
        raise ValueError(f"{label} exceeded its bound")
    return value


class BoundedContextSession:
    """Keep bounded semantic turns in memory while persisting only an integrity marker.

    Raw prompts and responses are deliberately process-local. The serialized marker
    contains only digests, ordering, and context identity. If a process restarts with
    a non-empty marker but without the raw semantic turns, continuity is reported as
    lost and the session fails closed instead of pretending it remembers prior turns.
    API credentials are call arguments only and are never retained on the session.
    """

    def __init__(self, *, context_id: str, system_message: str) -> None:
        self.context_id = context_id
        self.system_message = _validate_text(system_message, "system message")
        self._turns: list[SemanticTurn] = []
        self._ledger_state: str | None = None
        self._sequence = 0
        self._semantic_context_lost = False

    @classmethod
    def from_restart_marker(
        cls,
        *,
        context_id: str,
        system_message: str,
        marker: str,
    ) -> "BoundedContextSession":
        restored = parse_context_state(marker)
        if restored.context_id != context_id:
            raise ValueError("context isolation mismatch")
        session = cls(context_id=context_id, system_message=system_message)
        session._ledger_state = marker
        session._sequence = restored.sequence
        session._semantic_context_lost = restored.sequence > 0
        return session

    @property
    def semantic_context_lost(self) -> bool:
        return self._semantic_context_lost

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def retained_turns(self) -> tuple[SemanticTurn, ...]:
        return tuple(self._turns)

    def integrity_marker(self) -> str | None:
        return self._ledger_state

    def _bounded_prior_turns(self) -> list[SemanticTurn]:
        turns: list[SemanticTurn] = []
        used = 0
        for turn in reversed(self._turns):
            size = len(turn.prompt) + len(turn.response)
            if turns and (len(turns) >= MAX_PRIOR_TURNS or used + size > MAX_CONTEXT_CHARS):
                break
            if size > MAX_CONTEXT_CHARS:
                continue
            turns.append(turn)
            used += size
        turns.reverse()
        return turns

    def build_messages(self, prompt: str) -> list[dict[str, Any]]:
        if self._semantic_context_lost:
            raise ValueError("semantic context unavailable after restart")
        prompt = _validate_text(prompt, "prompt")
        messages = [_input_message("developer", self.system_message)]
        for turn in self._bounded_prior_turns():
            messages.append(_input_message("user", turn.prompt))
            messages.append(_input_message("assistant", turn.response))
        messages.append(_input_message("user", prompt))
        return messages

    def exchange(
        self,
        *,
        prompt: str,
        model: str,
        api_key: str,
        reasoner: Reasoner,
    ) -> tuple[str, str]:
        messages = self.build_messages(prompt)
        response, _request_id = reasoner(messages, model, api_key)
        response = _validate_text(response, "response")

        next_sequence = self._sequence + 1
        self._ledger_state = advance_context_state(
            self._ledger_state,
            context_id=self.context_id,
            sequence=next_sequence,
            input_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            output_sha256=hashlib.sha256(response.encode("utf-8")).hexdigest(),
        )
        self._sequence = next_sequence
        self._turns.append(SemanticTurn(prompt=prompt, response=response))
        if len(self._turns) > MAX_PRIOR_TURNS:
            self._turns = self._turns[-MAX_PRIOR_TURNS:]
        return response, self._ledger_state


__all__ = [
    "BoundedContextSession",
    "MAX_CONTEXT_CHARS",
    "MAX_PRIOR_TURNS",
    "MAX_TURN_CHARS",
    "SemanticTurn",
]
