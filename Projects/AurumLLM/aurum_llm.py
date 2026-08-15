#!/usr/bin/env python3
"""Stable Aurum-owned client contract for the local LLM runtime."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


class AurumLLMError(RuntimeError):
    """Raised when the local model runtime does not satisfy the Aurum contract."""


@dataclass(frozen=True)
class AurumLLMConfig:
    server_url: str = "http://127.0.0.1:8080"
    model_alias: str = "aurum-seed"
    timeout_seconds: float = 120.0


@dataclass(frozen=True)
class AurumReply:
    content: str
    reasoning_content: str
    tool_calls: tuple[Mapping[str, Any], ...]
    raw: Mapping[str, Any]


class AurumLLM:
    """Model-agnostic interface used by higher Aurum layers."""

    def __init__(self, config: AurumLLMConfig | None = None) -> None:
        self.config = config or AurumLLMConfig()

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        url = self.config.server_url.rstrip("/") + path
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                data = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise AurumLLMError(f"local LLM request failed: {exc}") from exc
        try:
            decoded = json.loads(data)
        except json.JSONDecodeError as exc:
            raise AurumLLMError("local LLM returned non-JSON data") from exc
        if not isinstance(decoded, dict):
            raise AurumLLMError("local LLM returned an unexpected JSON shape")
        return decoded

    def health(self) -> Mapping[str, Any]:
        return self._request_json("GET", "/health")

    def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 256,
        tools: Iterable[Mapping[str, Any]] | None = None,
    ) -> AurumReply:
        payload: dict[str, Any] = {
            "model": self.config.model_alias,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools is not None:
            payload["tools"] = list(tools)
        raw = self._request_json("POST", "/v1/chat/completions", payload)
        choices = raw.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AurumLLMError("local LLM response contained no choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise AurumLLMError("local LLM choice had an unexpected shape")
        message = first.get("message")
        if not isinstance(message, dict):
            raise AurumLLMError("local LLM response contained no message")
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or ""
        tool_calls_raw = message.get("tool_calls") or []
        if not isinstance(content, str) or not isinstance(reasoning, str):
            raise AurumLLMError("local LLM returned invalid text fields")
        if not isinstance(tool_calls_raw, list):
            raise AurumLLMError("local LLM returned invalid tool calls")
        tool_calls = tuple(item for item in tool_calls_raw if isinstance(item, dict))
        return AurumReply(
            content=content,
            reasoning_content=reasoning,
            tool_calls=tool_calls,
            raw=raw,
        )


def _main() -> int:
    parser = argparse.ArgumentParser(description="Talk to the Aurum local LLM core")
    parser.add_argument("--server-url", default="http://127.0.0.1:8080")
    parser.add_argument("--model", default="aurum-seed")
    parser.add_argument("--system", default="You are the local Aurum seed reasoning core.")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    client = AurumLLM(AurumLLMConfig(server_url=args.server_url, model_alias=args.model))
    reply = client.chat(
        [
            {"role": "system", "content": args.system},
            {"role": "user", "content": args.prompt},
        ],
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    if args.json:
        print(json.dumps(reply.raw, indent=2, sort_keys=True))
    else:
        print(reply.content or reply.reasoning_content)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
