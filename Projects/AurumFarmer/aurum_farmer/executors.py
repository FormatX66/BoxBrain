"""Executor adapters subordinate to the Aurum Farmer control plane."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from .models import EvidenceItem, ExecutionResult, HumanBoundary, Outcome


class Executor(Protocol):
    def execute(self, context: Mapping[str, Any]) -> ExecutionResult: ...


def _bounded(value: str, limit: int = 16_000) -> str:
    return value if len(value) <= limit else f"{value[:limit]}\n[truncated]"


def _fingerprint(*values: Any) -> str:
    body = json.dumps(values, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class ExecutorRegistry:
    def __init__(self) -> None:
        self._executors: dict[str, Executor] = {}

    def register(self, name: str, executor: Executor) -> None:
        if not name or name in self._executors:
            raise ValueError(f"executor already registered or invalid: {name}")
        self._executors[name] = executor

    def get(self, name: str) -> Executor:
        try:
            return self._executors[name]
        except KeyError as error:
            raise KeyError(f"Farmer executor is not registered: {name}") from error

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._executors))


class NoopExecutor:
    """Internal evidence canary. It proves the full ledger path without side effects."""

    def execute(self, context: Mapping[str, Any]) -> ExecutionResult:
        payload = dict(context.get("payload", {}))
        marker = str(payload.get("marker", "aurum-farmer-canary"))
        return ExecutionResult(
            outcome=Outcome.SUCCEEDED,
            summary="Farmer canary executed and produced deterministic evidence.",
            evidence=(
                EvidenceItem(
                    kind="noop_verified",
                    source="aurum-farmer:no-op-executor",
                    data={
                        "marker": marker,
                        "marker_sha256": hashlib.sha256(marker.encode("utf-8")).hexdigest(),
                        "job_id": context["job_id"],
                        "attempt_id": context["id"],
                    },
                ),
            ),
            lkg_ref=f"canary:{hashlib.sha256(marker.encode('utf-8')).hexdigest()}",
        )


class HumanBoundaryExecutor:
    """Explicitly records a true physical, credential, authority, or preference edge."""

    def execute(self, context: Mapping[str, Any]) -> ExecutionResult:
        payload = dict(context.get("payload", {}))
        boundary = HumanBoundary.from_value(payload.get("boundary"))
        if boundary is None:
            boundary = HumanBoundary(
                kind="physical_action",
                summary="A physical action is required before this branch can execute.",
                requested_action="Complete the recorded physical action and resume this Farmer job.",
            )
        return ExecutionResult(
            outcome=Outcome.HUMAN_REQUIRED,
            summary=boundary.summary,
            human_boundary=boundary,
            next_action=boundary.requested_action,
        )


class LocalProcessExecutor:
    """Run a reviewed executable without a shell and return bounded process evidence."""

    def __init__(self, allowed_programs: list[str] | tuple[str, ...] = ()) -> None:
        resolved = []
        for program in allowed_programs:
            candidate = shutil.which(program) or program
            resolved.append(str(Path(candidate).expanduser().resolve()).lower())
        self.allowed_programs = frozenset(resolved)

    def execute(self, context: Mapping[str, Any]) -> ExecutionResult:
        payload = dict(context.get("payload", {}))
        program = str(payload.get("program", ""))
        resolved = shutil.which(program) or program
        try:
            resolved_path = str(Path(resolved).expanduser().resolve())
        except (OSError, ValueError):
            resolved_path = resolved
        if not program or resolved_path.lower() not in self.allowed_programs:
            boundary = HumanBoundary(
                kind="destructive_authorization",
                summary="The requested local executable is not in Farmer's reviewed allowlist.",
                requested_action=f"Review and explicitly add this executable to Farmer configuration: {program or '[missing]'}",
            )
            return ExecutionResult(
                outcome=Outcome.HUMAN_REQUIRED,
                summary=boundary.summary,
                human_boundary=boundary,
                failure_class="authority",
            )
        arguments = payload.get("args", [])
        if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
            return ExecutionResult(
                outcome=Outcome.FAILED,
                summary="Local process arguments must be a string array.",
                failure_class="invalid_request",
                failure_fingerprint=_fingerprint("arguments", arguments),
            )
        timeout = min(max(float(payload.get("timeout_seconds", 300)), 1), 3600)
        cwd = payload.get("cwd")
        try:
            completed = subprocess.run(
                [resolved_path, *arguments],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                check=False,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired as error:
            return ExecutionResult(
                outcome=Outcome.FAILED,
                summary=f"Reviewed local process exceeded its {timeout:.0f}s timeout.",
                failure_class="timeout",
                retryable=True,
                retry_after_seconds=15,
                failure_fingerprint=_fingerprint(resolved_path, arguments, "timeout"),
                evidence=(
                    EvidenceItem(
                        kind="local_process_timeout",
                        source=resolved_path,
                        data={"timeout_seconds": timeout, "stdout": _bounded(str(error.stdout or ""))},
                    ),
                ),
            )
        evidence = EvidenceItem(
            kind="local_process_exit",
            source=resolved_path,
            data={
                "program": resolved_path,
                "arguments_sha256": _fingerprint(arguments),
                "cwd": str(cwd) if cwd else None,
                "exit_code": completed.returncode,
                "stdout": _bounded(completed.stdout),
                "stderr": _bounded(completed.stderr),
            },
            verified=True,
        )
        if completed.returncode == 0:
            return ExecutionResult(
                outcome=Outcome.SUCCEEDED,
                summary="Reviewed local process exited successfully.",
                evidence=(evidence,),
                lkg_ref=payload.get("lkg_ref"),
            )
        return ExecutionResult(
            outcome=Outcome.FAILED,
            summary=f"Reviewed local process exited with code {completed.returncode}.",
            evidence=(evidence,),
            failure_class=str(payload.get("failure_class", "process_failure")),
            retryable=bool(payload.get("retryable", False)),
            changed_dimensions=frozenset(payload.get("changed_dimensions", [])),
            failure_fingerprint=_fingerprint(resolved_path, arguments, completed.returncode, completed.stderr),
        )


class GhClient:
    def __init__(self, executable: str = "gh") -> None:
        resolved = shutil.which(executable)
        if not resolved:
            raise RuntimeError("GitHub CLI is required for GitHub executor adapters")
        self.executable = resolved

    def run(self, args: list[str], *, input_bytes: bytes | None = None, timeout: float = 120) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [self.executable, *args],
            input=input_bytes,
            capture_output=True,
            timeout=timeout,
            shell=False,
            check=False,
            env=os.environ.copy(),
        )

    def json(self, args: list[str], *, input_value: Mapping[str, Any] | None = None, timeout: float = 120) -> Any:
        raw = None if input_value is None else json.dumps(input_value, separators=(",", ":")).encode("utf-8")
        completed = self.run(args, input_bytes=raw, timeout=timeout)
        if completed.returncode != 0:
            message = _bounded(completed.stderr.decode("utf-8", errors="replace"), 4000)
            raise RuntimeError(f"gh {' '.join(args[:3])} failed: {message}")
        text = completed.stdout.decode("utf-8", errors="strict").strip()
        return None if not text else json.loads(text)


class GitHubWorkflowExecutor:
    """Dispatch and verify a GitHub workflow run as one Farmer executor."""

    def __init__(self, client: GhClient | None = None) -> None:
        self.client = client or GhClient()

    def _prior_dispatch(self, context: Mapping[str, Any]) -> Mapping[str, Any] | None:
        values = context.get("prior_evidence", [])
        for item in reversed(values):
            if item.get("kind") == "github_workflow_dispatch":
                return item.get("payload")
        return None

    def execute(self, context: Mapping[str, Any]) -> ExecutionResult:
        payload = dict(context.get("payload", {}))
        repository = str(payload.get("repository", "FormatX66/BoxBrain"))
        workflow = str(payload.get("workflow", ""))
        ref = str(payload.get("ref", "main"))
        if not workflow:
            return ExecutionResult(
                outcome=Outcome.FAILED,
                summary="GitHub workflow executor requires payload.workflow.",
                failure_class="invalid_request",
                failure_fingerprint=_fingerprint(payload),
            )
        prior = self._prior_dispatch(context)
        dispatched_at = prior.get("dispatched_at") if prior else None
        if prior and (prior.get("repository"), prior.get("workflow"), prior.get("ref")) != (repository, workflow, ref):
            prior = None
            dispatched_at = None
        dispatch_evidence: EvidenceItem | None = None
        try:
            if not prior:
                args = ["workflow", "run", workflow, "--repo", repository, "--ref", ref]
                for key, value in sorted(dict(payload.get("inputs", {})).items()):
                    args.extend(["-f", f"{key}={value}"])
                completed = self.client.run(args, timeout=120)
                if completed.returncode != 0:
                    stderr = completed.stderr.decode("utf-8", errors="replace")
                    failure_class = "rate_limit" if "rate limit" in stderr.lower() else "transport"
                    return ExecutionResult(
                        outcome=Outcome.FAILED,
                        summary=f"GitHub workflow dispatch failed: {_bounded(stderr, 1000)}",
                        failure_class=failure_class,
                        retryable=True,
                        retry_after_seconds=30,
                        failure_fingerprint=_fingerprint(repository, workflow, ref, stderr),
                    )
                dispatched_at = datetime.now(timezone.utc).isoformat()
                prior = {"repository": repository, "workflow": workflow, "ref": ref, "dispatched_at": dispatched_at}
                dispatch_evidence = EvidenceItem(
                    kind="github_workflow_dispatch",
                    source=f"https://github.com/{repository}/actions",
                    data=prior,
                )

            deadline = time.monotonic() + min(max(float(payload.get("observe_seconds", 30)), 1), 300)
            selected = None
            while time.monotonic() < deadline:
                runs = self.client.json(
                    [
                        "run", "list", "--repo", repository, "--workflow", workflow,
                        "--event", "workflow_dispatch", "--limit", "30", "--json",
                        "databaseId,createdAt,event,headBranch,status,conclusion,url,headSha,workflowName",
                    ]
                )
                minimum = datetime.fromisoformat(str(dispatched_at).replace("Z", "+00:00")).timestamp() - 5
                candidates = [
                    item for item in runs
                    if datetime.fromisoformat(item["createdAt"].replace("Z", "+00:00")).timestamp() >= minimum
                    and (item.get("headBranch") == ref or ref in {"main", item.get("headBranch")})
                ]
                if candidates:
                    selected = sorted(candidates, key=lambda item: item["createdAt"])[0]
                    if selected["status"] == "completed":
                        break
                time.sleep(2)
            evidence = tuple(item for item in (dispatch_evidence,) if item is not None)
            if selected is None or selected["status"] != "completed":
                return ExecutionResult(
                    outcome=Outcome.WAITING,
                    summary="GitHub accepted the workflow; the run is still pending or executing.",
                    evidence=evidence,
                    retry_after_seconds=15,
                    next_action="observe the already-dispatched workflow run",
                )
            run_evidence = EvidenceItem(
                kind="github_actions_run",
                source=selected["url"],
                data=selected,
            )
            if selected["conclusion"] == "success":
                return ExecutionResult(
                    outcome=Outcome.SUCCEEDED,
                    summary="GitHub workflow completed successfully and its run state was read back.",
                    evidence=(*evidence, run_evidence),
                    lkg_ref=f"github-run:{repository}:{selected['databaseId']}:{selected.get('headSha')}",
                )
            return ExecutionResult(
                outcome=Outcome.FAILED,
                summary=f"GitHub workflow concluded {selected['conclusion']}.",
                evidence=(*evidence, run_evidence),
                failure_class="workflow_failure",
                failure_fingerprint=_fingerprint(repository, workflow, selected["databaseId"], selected["conclusion"], selected.get("headSha")),
            )
        except (RuntimeError, subprocess.TimeoutExpired, ValueError) as error:
            return ExecutionResult(
                outcome=Outcome.FAILED,
                summary=f"GitHub executor could not complete observation: {error}",
                failure_class="transport",
                retryable=True,
                retry_after_seconds=30,
                failure_fingerprint=_fingerprint(repository, workflow, ref, str(error)),
            )


class ChatToGitExecutor:
    """Use the verified Chat-to-Git pipeline as one bounded Farmer executor."""

    STATUS_MARKER = re.compile(r"pipeline-status:([A-Za-z0-9._-]+):([a-z_]+)")
    RUN_URL = re.compile(r"https://github\.com/[^/]+/[^/]+/actions/runs/(\d+)")

    def __init__(self, client: GhClient | None = None) -> None:
        self.client = client or GhClient()

    def _request(self, context: Mapping[str, Any], repository: str) -> dict[str, Any]:
        payload = dict(context.get("payload", {}))
        supplied = payload.get("request")
        if supplied:
            request = dict(supplied)
        else:
            raw_id = f"farmer-{context['job_id'].lower()}"
            request_id = re.sub(r"[^A-Za-z0-9._-]", "-", raw_id)[:64]
            request = {
                "request_id": request_id,
                "source": "gpt",
                "issued_at": datetime.now(timezone.utc).isoformat(),
                "prompt": str(payload.get("prompt", context["goal"]))[:4000],
                "target": {"repository": repository, "mode": "same_repository"},
                "task": dict(payload.get("task", {"type": "repository_status", "parameters": {}})),
                "feedback": dict(payload.get("feedback", {})),
            }
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,63}", str(request.get("request_id", ""))):
            raise ValueError("Chat-to-Git request_id is invalid")
        request["target"] = {"repository": repository, "mode": "same_repository"}
        return request

    def _feedback(self, repository: str, request_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        issues = self.client.json(
            ["api", f"repos/{repository}/issues?state=all&labels=pipeline-feedback&per_page=100"]
        )
        issue = next((item for item in issues if item.get("title", "").startswith(f"[pipeline:{request_id}]")), None)
        if issue is None:
            return None, []
        comments = self.client.json(["api", f"repos/{repository}/issues/{issue['number']}/comments?per_page=100"])
        return issue, comments

    def _dispatch_primary(self, repository: str, request: Mapping[str, Any]) -> None:
        completed = self.client.run(
            ["api", f"repos/{repository}/dispatches", "--method", "POST", "--input", "-"],
            input_bytes=json.dumps(
                {"event_type": "voice_chat_request", "client_payload": {"request": request}},
                separators=(",", ":"),
            ).encode("utf-8"),
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.decode("utf-8", errors="replace"))

    def _dispatch_fallback(self, url: str, request: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
        body = json.dumps(request, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        shared_secret_env = payload.get("webhook_shared_secret_env")
        bearer_env = payload.get("webhook_bearer_token_env")
        if shared_secret_env and os.environ.get(str(shared_secret_env)):
            secret = os.environ[str(shared_secret_env)].encode("utf-8")
            signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
            headers["X-Pipeline-Signature"] = f"sha256={signature}"
        elif bearer_env and os.environ.get(str(bearer_env)):
            headers["Authorization"] = f"Bearer {os.environ[str(bearer_env)]}"
        else:
            raise RuntimeError("fallback webhook credential environment variable is unavailable")
        request_object = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request_object, timeout=30) as response:
            if response.status != 202:
                raise RuntimeError(f"fallback webhook returned HTTP {response.status}")

    def _artifact_receipt(self, repository: str, run_id: int, request_id: str) -> tuple[dict[str, Any], str]:
        artifacts = self.client.json(["api", f"repos/{repository}/actions/runs/{run_id}/artifacts"])
        candidate = next(
            (item for item in artifacts.get("artifacts", []) if item.get("name", "").startswith(f"receipt-{request_id}-")),
            None,
        )
        if candidate is None:
            raise RuntimeError("Chat-to-Git run has no matching receipt artifact")
        completed = self.client.run(["api", f"repos/{repository}/actions/artifacts/{candidate['id']}/zip"], timeout=120)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.decode("utf-8", errors="replace"))
        with tempfile.TemporaryDirectory(prefix="aurum-farmer-receipt-") as directory:
            archive = Path(directory) / "receipt.zip"
            archive.write_bytes(completed.stdout)
            with zipfile.ZipFile(archive) as value:
                names = value.namelist()
                receipt_name = next((name for name in names if name.endswith("receipt.json")), None)
                if receipt_name is None:
                    raise RuntimeError("Chat-to-Git artifact did not contain receipt.json")
                receipt = json.loads(value.read(receipt_name).decode("utf-8"))
        if receipt.get("request_id") != request_id or receipt.get("status") != "succeeded":
            raise RuntimeError("Chat-to-Git receipt identity or status did not verify")
        return receipt, str(candidate.get("archive_download_url", ""))

    def execute(self, context: Mapping[str, Any]) -> ExecutionResult:
        payload = dict(context.get("payload", {}))
        repository = str(payload.get("repository", "FormatX66/Chat-to-Git-Pipeline"))
        try:
            request = self._request(context, repository)
            request_id = request["request_id"]
            issue, comments = self._feedback(repository, request_id)
            dispatch_route = "existing_feedback"
            if issue is None:
                try:
                    self._dispatch_primary(repository, request)
                    dispatch_route = "github_repository_dispatch"
                except RuntimeError as primary_error:
                    fallback_url = payload.get("fallback_url")
                    if not fallback_url:
                        raise RuntimeError(f"primary failed and no fallback is configured: {primary_error}") from primary_error
                    self._dispatch_fallback(str(fallback_url), request, payload)
                    dispatch_route = "signed_webhook_fallback"

            deadline = time.monotonic() + min(max(float(payload.get("observe_seconds", 120)), 5), 600)
            last_status = "accepted"
            run_id = None
            issue = None
            comments = []
            while time.monotonic() < deadline:
                issue, comments = self._feedback(repository, request_id)
                if issue:
                    for comment in comments:
                        body = comment.get("body", "")
                        marker = self.STATUS_MARKER.search(body)
                        if marker and marker.group(1) == request_id:
                            last_status = marker.group(2)
                        match = self.RUN_URL.search(body)
                        if match:
                            run_id = int(match.group(1))
                    if last_status in {"succeeded", "failed"} and run_id:
                        break
                time.sleep(3)
            dispatch_item = EvidenceItem(
                kind="chat_to_git_dispatch",
                source=f"https://github.com/{repository}",
                data={"request_id": request_id, "route": dispatch_route, "repository": repository},
            )
            if not issue or not run_id or last_status not in {"succeeded", "failed"}:
                return ExecutionResult(
                    outcome=Outcome.WAITING,
                    summary="Chat-to-Git accepted the request; verified terminal feedback is not available yet.",
                    evidence=(dispatch_item,),
                    retry_after_seconds=30,
                    next_action="observe the existing Chat-to-Git request without redispatching it",
                )
            run = self.client.json(
                [
                    "run", "view", str(run_id), "--repo", repository, "--json",
                    "databaseId,status,conclusion,url,headSha,workflowName,event",
                ]
            )
            feedback_item = EvidenceItem(
                kind="github_issue_feedback",
                source=issue["html_url"],
                data={
                    "issue_number": issue["number"],
                    "issue_url": issue["html_url"],
                    "request_id": request_id,
                    "status": last_status,
                },
            )
            run_item = EvidenceItem(kind="github_actions_run", source=run["url"], data=run)
            if last_status != "succeeded" or run.get("conclusion") != "success":
                return ExecutionResult(
                    outcome=Outcome.FAILED,
                    summary=f"Chat-to-Git request concluded {last_status}/{run.get('conclusion')}.",
                    evidence=(dispatch_item, feedback_item, run_item),
                    failure_class="executor_failure",
                    failure_fingerprint=_fingerprint(request_id, last_status, run),
                )
            receipt, artifact_url = self._artifact_receipt(repository, run_id, request_id)
            receipt_item = EvidenceItem(
                kind="chat_to_git_receipt",
                source=artifact_url or run["url"],
                data=receipt,
            )
            return ExecutionResult(
                outcome=Outcome.SUCCEEDED,
                summary="Chat-to-Git executed as a Farmer adapter; run, feedback, and receipt all verified.",
                evidence=(dispatch_item, feedback_item, run_item, receipt_item),
                lkg_ref=f"github-run:{repository}:{run_id}:{run.get('headSha')}",
            )
        except urllib.error.HTTPError as error:
            return ExecutionResult(
                outcome=Outcome.FAILED,
                summary=f"Chat-to-Git webhook returned HTTP {error.code}.",
                failure_class="authorization" if error.code in {401, 403} else "transport",
                retryable=error.code in {408, 429, 500, 502, 503, 504},
                retry_after_seconds=float(error.headers.get("Retry-After", "30")),
                failure_fingerprint=_fingerprint("webhook", error.code),
            )
        except (RuntimeError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
            text = str(error)
            stable_auth = any(token in text.lower() for token in ("auth", "credential", "permission", "401", "403"))
            return ExecutionResult(
                outcome=Outcome.FAILED,
                summary=f"Chat-to-Git adapter failed verification: {text}",
                failure_class="authorization" if stable_auth else "transport",
                retryable=not stable_auth,
                retry_after_seconds=30,
                failure_fingerprint=_fingerprint("chat-to-git", text),
            )


class EvidenceFileExecutor:
    """Observe a deterministic external receipt without treating file presence alone as proof."""

    def execute(self, context: Mapping[str, Any]) -> ExecutionResult:
        payload = dict(context.get("payload", {}))
        raw_path = payload.get("path")
        expected_sha256 = payload.get("sha256")
        if not raw_path:
            return ExecutionResult(
                outcome=Outcome.FAILED,
                summary="Evidence-file executor requires payload.path.",
                failure_class="invalid_request",
            )
        path = Path(str(raw_path)).expanduser().resolve()
        if not path.is_file():
            return ExecutionResult(
                outcome=Outcome.WAITING,
                summary="External evidence file is not present yet.",
                retry_after_seconds=float(payload.get("poll_seconds", 30)),
                next_action=f"wait for evidence file {path}",
            )
        body = path.read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        if expected_sha256 and not hmac.compare_digest(digest, str(expected_sha256).lower()):
            return ExecutionResult(
                outcome=Outcome.FAILED,
                summary="External evidence file hash did not match the required identity.",
                failure_class="evidence_gate",
                failure_fingerprint=_fingerprint(str(path), digest, expected_sha256),
            )
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = {"content_sha256": digest, "bytes": len(body)}
        return ExecutionResult(
            outcome=Outcome.SUCCEEDED,
            summary="External evidence file identity and content hash verified.",
            evidence=(
                EvidenceItem(
                    kind=str(payload.get("evidence_kind", "external_receipt")),
                    source=str(path),
                    data={"sha256": digest, "bytes": len(body), "receipt": parsed},
                ),
            ),
            lkg_ref=payload.get("lkg_ref"),
        )


def build_default_registry(config: Mapping[str, Any] | None = None) -> ExecutorRegistry:
    values = dict(config or {})
    registry = ExecutorRegistry()
    registry.register("noop", NoopExecutor())
    registry.register("human_boundary", HumanBoundaryExecutor())
    registry.register("evidence_file", EvidenceFileExecutor())
    registry.register("local_process", LocalProcessExecutor(values.get("allowed_programs", [])))
    try:
        client = GhClient(str(values.get("gh_executable", "gh")))
    except RuntimeError:
        client = None
    if client:
        registry.register("github_workflow", GitHubWorkflowExecutor(client))
        registry.register("chat_to_git", ChatToGitExecutor(client))
    return registry
