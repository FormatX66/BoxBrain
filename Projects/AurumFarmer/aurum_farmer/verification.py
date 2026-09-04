"""Independent result checks and administrator-configured tier probes."""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

from .decision_engine import Probe, digest
from .models import EvidenceItem, ExecutionResult, Outcome


def verify_result(context, result: ExecutionResult) -> ExecutionResult:
    if result.outcome not in {Outcome.SUCCEEDED, Outcome.NO_CHANGE}:
        return result
    problems = []
    mode = "evidence_contract"
    if context["executor"] == "noop":
        mode = "independent_marker_recomputation"
        marker = str(context.get("payload", {}).get("marker", "aurum-farmer-canary"))
        expected = hashlib.sha256(marker.encode()).hexdigest()
        if not any(e.kind == "noop_verified" and e.data.get("marker_sha256") == expected
                   and e.data.get("job_id") == context["job_id"]
                   and e.data.get("attempt_id") == context["id"] for e in result.evidence):
            problems.append("canary identity or digest mismatch")
    elif context["executor"] == "evidence_file":
        mode = "independent_file_readback"
        try:
            body = Path(context["payload"]["path"]).expanduser().resolve().read_bytes()
            expected = hashlib.sha256(body).hexdigest()
            if not any(e.verified and e.data.get("sha256") == expected for e in result.evidence):
                problems.append("external receipt changed between execution and verification")
        except (OSError, KeyError):
            problems.append("external receipt unavailable for independent readback")
    counts = {}
    for item in result.evidence:
        if item.verified:
            counts[item.kind] = counts.get(item.kind, 0) + 1
    for required in context.get("expected_evidence", []):
        if counts.get(required["kind"], 0) < required.get("minimum", 1):
            problems.append("missing required evidence: " + required["kind"])
    if problems:
        return ExecutionResult(outcome=Outcome.FAILED, summary="; ".join(problems),
                               failure_class="evidence_gate", evidence=result.evidence)
    receipt = EvidenceItem(kind="independent_verification", source="farmer-result-verifier-v1",
                           data={"attempt_id": context["id"], "mode": mode,
                                 "evidence_digest": digest([dict(e.data) for e in result.evidence]),
                                 "passed": True})
    return replace(result, evidence=(*result.evidence, receipt))


def command_probes(config):
    """Commands come ONLY from the restricted runtime configuration, never jobs.

    A probe receives JSON on stdin in a disposable directory. It must return a
    JSON receipt bound to the supplied input_digest. No shell and no ambient
    credentials are passed. Configured hardware probes retain their own identity,
    canary/rollback, and authorization gates.
    """
    probes = []
    for spec in config.get("probes", []):
        argv = spec["argv"]
        if not isinstance(argv, list) or not argv or not all(isinstance(s, str) for s in argv):
            raise ValueError("probe argv must be a nonempty string array")
        if not Path(argv[0]).is_absolute():
            raise ValueError("probe executable must be an absolute reviewed path")
        timeout = float(spec.get("timeout_seconds", 30))
        if not 0 < timeout <= 60:
            raise ValueError("probe deadline must be at most 60 seconds")

        def run(snapshot, branch, argv=tuple(argv), timeout=timeout):
            # No action payload/secret propagation to the speculative environment.
            request = {"state": snapshot, "action_id": digest(branch),
                       "branch_id": branch["logical_id"]}
            request["input_digest"] = digest(request)
            with tempfile.TemporaryDirectory(prefix="aurum-future-") as directory:
                with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
                    result = subprocess.run(argv, input=json.dumps(request).encode(), cwd=directory,
                                            env={}, stdout=stdout, stderr=stderr, timeout=timeout,
                                            shell=False, check=False)
                    stdout.seek(0)
                    raw = stdout.read(65537)
                    if len(raw) > 65536:
                        return {"passed": False, "evidence_ref": "receipt-too-large"}
                    receipt = json.loads(raw)
            return {"passed": result.returncode == 0 and receipt.get("passed") is True
                    and receipt.get("input_digest") == request["input_digest"],
                    "rollback_verified": receipt.get("rollback_verified") is True,
                    "evidence_ref": "sha256:" + hashlib.sha256(raw).hexdigest()}

        probes.append(Probe(spec["tier"], spec["identity"], run, spec.get("resource", "isolated"), digest(spec)))
    return tuple(probes)
