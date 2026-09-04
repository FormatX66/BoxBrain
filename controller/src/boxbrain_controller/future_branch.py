"""Default Future Branch coverage for every authenticated controller API route."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from aurum_farmer.operation_gate import OperationGate, source_revision, workspace_revision
from starlette.requests import Request
from starlette.responses import JSONResponse


class FutureBranchMiddleware:
    def __init__(self, app, *, gate: OperationGate, repository_root: Path):
        self.app = app
        self.gate = gate
        self.repository_root = repository_root

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api/") or scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)
        request = Request(scope, receive)
        body = await request.body()
        try:
            inputs = json.loads(body) if body else None
        except (ValueError, UnicodeDecodeError):
            inputs = {"unparsed_body_hex": body.hex()}
        inputs = {"body": inputs, "query": sorted(request.query_params.multi_items())}
        # Remove only transport keys at the request body's top level.
        from aurum_farmer.operation_gate import semantic_input
        inputs["body"] = semantic_input(inputs["body"])
        recovery = scope["method"] in {"GET", "HEAD"} or path == "/api/v1/safety/emergency-stop/engage"
        try:
            observed = "recovery_observation" if recovery else await asyncio.to_thread(workspace_revision, self.repository_root)
            ticket = await asyncio.to_thread(self.gate.begin, scope["method"] + " " + path,
                        inputs, {"workspace_revision": observed}, recovery_observation=recovery)
        except Exception:
            # Emergency stop must still be reachable if storage is unavailable.
            if path == "/api/v1/safety/emergency-stop/engage":
                return await self.app(scope, self._replay(body, receive), send)
            return await JSONResponse({"detail": "Future Branch evidence store unavailable.",
                "status": "waiting"}, status_code=503)(scope, receive, send)
        if not ticket["allowed"]:
            return await JSONResponse({"status": "waiting", "detail": ticket["reason"],
                "future_branch": {"state_id": ticket["state_id"],
                "next_action": "inspect evidence or change the failed input, implementation, or observed state"}},
                status_code=409)(scope, receive, send)

        response_status = 0
        response_body = bytearray()
        finished = False

        async def observe(message):
            nonlocal response_status, finished
            if message["type"] == "http.response.start":
                response_status = message["status"]
                message = {**message, "headers": [*message.get("headers", []),
                    (b"x-aurum-future-branch", ticket["state_id"].encode()),
                    (b"x-aurum-future-branch-scope", b"admission_only")]}
            if message["type"] == "http.response.body":
                if len(response_body) <= 65536:
                    response_body.extend(message.get("body", b"")[:65537 - len(response_body)])
                if not message.get("more_body", False):
                    outcome = "failed" if response_status >= 500 else "refused" if response_status >= 400 else "observed"
                    try:
                        value = json.loads(response_body)
                        status = value.get("status") if isinstance(value, dict) else None
                        if status == "failed":
                            outcome = "failed"
                        elif status in {"waiting", "blocked", "machine_blocked", "escalated"}:
                            outcome = "waiting"
                        elif status in {"refused", "rejected"}:
                            outcome = "refused"
                    except (ValueError, UnicodeDecodeError):
                        pass
                    try:
                        await asyncio.to_thread(self.gate.finish, ticket, outcome,
                            {"http_status": response_status, "response_prefix_hex": response_body.hex()})
                        finished = True
                    except Exception:
                        # The unresolved admission stays blocked. A bookkeeping
                        # error cannot turn an executed effect into a retryable 500.
                        pass
            await send(message)

        try:
            await self.app(scope, self._replay(body, receive), observe)
        except BaseException:
            if not finished:
                try:
                    await asyncio.to_thread(self.gate.finish, ticket, "uncertain", {"response_status": response_status})
                except Exception:
                    pass
            raise

    @staticmethod
    def _replay(body, receive):
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()
        return replay


def make_gate(data_dir: Path) -> OperationGate:
    sources = Path(__file__).parent.glob("*.py")
    return OperationGate(data_dir / "future-branch.sqlite3", implementation=source_revision(sources))
