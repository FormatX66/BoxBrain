from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .models import EdgeAgentSummary


class EdgeAgentConfigurationError(ValueError):
    """Raised when an edge-agent endpoint violates the local-tunnel policy."""


@dataclass(frozen=True, slots=True)
class KaliPiEdgeAgentClient:
    base_url: str
    timeout_seconds: float = 1.5
    max_response_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise EdgeAgentConfigurationError(
                "The Kali Pi edge agent must be reached through a loopback-only "
                "HTTP endpoint, normally an SSH local-forward."
            )

    def describe(self) -> EdgeAgentSummary:
        try:
            payload = self._fetch_status()
        except (HTTPError, OSError, TimeoutError, URLError, ValueError):
            return EdgeAgentSummary(
                id="kali-pi",
                name="Kali Pi Edge Agent",
                role="edge-agent",
                transport="ssh-tunnel",
                mode="read-only-advisory",
                connected=False,
                version=None,
                hostname=None,
                target_count=0,
                recommendation_count=0,
            )

        agent = payload.get("agent")
        if not isinstance(agent, dict):
            agent = payload.get("controller")
        if not isinstance(agent, dict):
            agent = {}

        return EdgeAgentSummary(
            id="kali-pi",
            name="Kali Pi Edge Agent",
            role="edge-agent",
            transport="ssh-tunnel",
            mode="read-only-advisory",
            connected=True,
            version=self._optional_string(payload.get("version")),
            hostname=self._optional_string(payload.get("hostname")),
            target_count=self._non_negative_int(agent.get("target_count")),
            recommendation_count=self._non_negative_int(
                agent.get("recommendation_count")
            ),
        )

    def _fetch_status(self) -> dict[str, Any]:
        request = Request(
            f"{self.base_url.rstrip('/')}/api/v1/status",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            content_type = response.headers.get_content_type()
            if content_type != "application/json":
                raise ValueError("Edge agent returned a non-JSON response.")
            body = response.read(self.max_response_bytes + 1)
        if len(body) > self.max_response_bytes:
            raise ValueError("Edge agent response exceeded the size limit.")
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("Edge agent returned an invalid status object.")
        return payload

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized[:200] or None

    @staticmethod
    def _non_negative_int(value: object) -> int:
        if isinstance(value, bool):
            return 0
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0
