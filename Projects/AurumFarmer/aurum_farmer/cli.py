"""Command-line and daemon entrypoint for Aurum Farmer."""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from .api import FarmerApiServer, serve_in_thread
from .config import default_config_path, load_config, read_api_token, write_initial_config
from .executors import build_default_registry
from .ledger import Ledger
from .models import BranchSpec, EvidenceRequirement, JobSpec
from .supervisor import Supervisor
from .decision_engine import Budget, DecisionEngine
from .verification import command_probes


def _runtime(config_path: str | None) -> tuple[dict[str, Any], Ledger]:
    config = load_config(config_path)
    ledger = Ledger(config["ledger_path"], signing_key_path=config["signing_key_path"])
    return config, ledger


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def _load_json(path: str) -> dict[str, Any]:
    if path == "-":
        value = json.load(sys.stdin)
    else:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("input must contain one JSON object")
    return value


def _chat_to_git_job(args: argparse.Namespace) -> JobSpec:
    if args.request_file:
        request = _load_json(args.request_file)
        payload = {"request": request, "observe_seconds": args.observe_seconds}
        request_id = str(request.get("request_id", "unknown"))
    else:
        payload = {
            "prompt": args.prompt,
            "task": {"type": args.task_type, "parameters": {}},
            "observe_seconds": args.observe_seconds,
        }
        request_id = args.dedupe_key or args.prompt[:48]
    payload["repository"] = args.repository
    if args.fallback_url:
        payload["fallback_url"] = args.fallback_url
        if args.webhook_secret_env:
            payload["webhook_shared_secret_env"] = args.webhook_secret_env
        if args.webhook_bearer_env:
            payload["webhook_bearer_token_env"] = args.webhook_bearer_env
    return JobSpec(
        goal=args.goal or f"Execute Chat-to-Git request {request_id} under Aurum Farmer",
        priority=args.priority,
        dedupe_key=args.dedupe_key,
        context={"ingress": "farmer-cli", "adapter": "chat_to_git"},
        branches=(
            BranchSpec(
                id="chat-to-git-primary",
                label="Verified Chat-to-Git GitHub executor with signed webhook fallback",
                executor="chat_to_git",
                payload=payload,
                expected_evidence=(
                    EvidenceRequirement("chat_to_git_dispatch"),
                    EvidenceRequirement("github_issue_feedback"),
                    EvidenceRequirement("github_actions_run"),
                    EvidenceRequirement("chat_to_git_receipt"),
                ),
                priority=90,
                confidence=0.95,
                impact=0.8,
                evidence_quality=1.0,
                risk=0.05,
                cost=0.15,
                reversibility=1.0,
                max_attempts=4,
                lkg_scope="chat-to-git-executor",
            ),
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aurum-farmer", description="Persistent Aurum/BoxBrain orchestration")
    parser.add_argument("--config", default=str(default_config_path()), help="Farmer configuration JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="initialize a durable local runtime")
    init.add_argument("--root", help="runtime data directory")

    submit = subparsers.add_parser("submit", help="submit a complete durable job JSON")
    submit.add_argument("--file", required=True, help="job JSON or - for standard input")

    chat = subparsers.add_parser("submit-chat-to-git", help="submit Chat-to-Git as one Farmer executor")
    source = chat.add_mutually_exclusive_group(required=True)
    source.add_argument("--request-file", help="validated Chat-to-Git request JSON")
    source.add_argument("--prompt", help="prompt recorded with a bounded built-in task")
    chat.add_argument("--task-type", choices=("echo", "repository_status"), default="repository_status")
    chat.add_argument("--repository", default="FormatX66/Chat-to-Git-Pipeline")
    chat.add_argument("--goal")
    chat.add_argument("--priority", type=int, default=80)
    chat.add_argument("--dedupe-key")
    chat.add_argument("--observe-seconds", type=float, default=120)
    chat.add_argument("--fallback-url")
    chat.add_argument("--webhook-secret-env")
    chat.add_argument("--webhook-bearer-env")

    canary = subparsers.add_parser("canary", help="submit an end-to-end internal evidence canary")
    canary.add_argument("--marker", default="aurum-farmer-canary")
    canary.add_argument("--dedupe-key")

    status = subparsers.add_parser("status", help="read durable status")
    status.add_argument("--job")
    status.add_argument("--limit", type=int, default=100)
    future = subparsers.add_parser("futures", help="read measured branch DAG and calibration telemetry")
    future.add_argument("--job")

    receipts = subparsers.add_parser("receipts", help="export sealed receipts for one job")
    receipts.add_argument("--job", required=True)

    resume = subparsers.add_parser("resume", help="resume after a real state dimension changed")
    resume.add_argument("--job", required=True)
    resume.add_argument(
        "--changed-dimension",
        required=True,
        choices=("input", "state", "evidence", "implementation", "environment", "dependency", "hypothesis", "authority"),
    )
    resume.add_argument("--note", required=True)

    run = subparsers.add_parser("run", help="run one or continuous supervisor cycles")
    run.add_argument("--once", action="store_true")

    subparsers.add_parser("daemon", help="run persistent supervisor and loopback API")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "init":
        values = write_initial_config(args.config, root=args.root)
        Ledger(values["ledger_path"], signing_key_path=values["signing_key_path"])
        _print({"status": "initialized", "config": str(Path(args.config).resolve()), "runtime_root": values["runtime_root"]})
        return 0

    config, ledger = _runtime(args.config)
    future_config = config.get("future_branch", {})
    ledger.decision_engine = DecisionEngine(budget=Budget(**future_config.get("budget", {})),
                                            probes=command_probes(future_config))
    if args.command == "futures":
        _print(ledger.future_status(args.job))
        return 0
    if args.command == "submit":
        job_id, created = ledger.submit(JobSpec.from_dict(_load_json(args.file)))
        _print({"job_id": job_id, "created": created})
        return 0
    if args.command == "submit-chat-to-git":
        job_id, created = ledger.submit(_chat_to_git_job(args))
        _print({"job_id": job_id, "created": created})
        return 0
    if args.command == "canary":
        job_id, created = ledger.submit(
            JobSpec(
                goal="Verify Aurum Farmer durable schedule, execution, evidence, receipt, and LKG path",
                priority=100,
                dedupe_key=args.dedupe_key,
                context={"ingress": "farmer-cli", "kind": "canary"},
                branches=(
                    BranchSpec(
                        id="internal-canary",
                        label="Deterministic internal evidence canary",
                        executor="noop",
                        payload={"marker": args.marker},
                        expected_evidence=(EvidenceRequirement("noop_verified"),),
                        priority=100,
                        confidence=1.0,
                        impact=1.0,
                        evidence_quality=1.0,
                        risk=0.0,
                        cost=0.01,
                        reversibility=1.0,
                        max_attempts=1,
                        lkg_scope="aurum-farmer-runtime",
                    ),
                ),
            )
        )
        _print({"job_id": job_id, "created": created})
        return 0
    if args.command == "status":
        _print(ledger.get_job(args.job) if args.job else {"stats": ledger.stats(), "jobs": ledger.list_jobs(limit=args.limit)})
        return 0
    if args.command == "receipts":
        _print({"job_id": args.job, "receipts": ledger.export_receipts(args.job)})
        return 0
    if args.command == "resume":
        ledger.resume(args.job, changed_dimension=args.changed_dimension, note=args.note)
        _print(ledger.get_job(args.job))
        return 0

    registry = build_default_registry(config.get("executors"))
    supervisor = Supervisor(
        ledger,
        registry,
        lease_seconds=float(config.get("lease_seconds", 90)),
        poll_seconds=float(config.get("poll_seconds", 2)),
    )
    if args.command == "run":
        if args.once:
            _print(supervisor.tick())
        else:
            supervisor.run_forever()
        return 0
    if args.command == "daemon":
        token = read_api_token(config)
        server = FarmerApiServer((str(config["api_host"]), int(config["api_port"])), ledger, token)
        api_thread = serve_in_thread(server)

        def stop(*_: Any) -> None:
            supervisor.stop()
            server.shutdown()

        signal.signal(signal.SIGINT, stop)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, stop)
        try:
            supervisor.run_forever()
        finally:
            server.shutdown()
            server.server_close()
            api_thread.join(timeout=5)
        return 0
    return 2
