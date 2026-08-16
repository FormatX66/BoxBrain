from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
import re
import time
from typing import Any, Mapping

from native_gap_catalog import NativeSemanticGap


EVIDENCE_SCHEMA = "aurum-external-prerequisite-evidence-v0"
BBPI4_PRESENCE_KIND = "bbpi4-physical-presence"
BBPI4_PRESENCE_SOURCE = "aurum-public-controller-fresh-node"
READINESS_EVIDENCE_SCHEMA = "aurum-adaptive-shell-live-trial-readiness-evidence-v1"
READINESS_EVIDENCE_KIND = "adaptive-shell-live-trial-readiness"
READINESS_EVIDENCE_SOURCE = "aurum-windows-usb-kvm-bounded-proof"
TRIAL_EVIDENCE_SCHEMA = "aurum-adaptive-shell-live-trial-evidence-v1"
TRIAL_EVIDENCE_KIND = "adaptive-shell-bounded-live-trial"
TRIAL_EVIDENCE_SOURCE = "aurum-ephemeral-shell-state-trial"
ITERATION_OBSERVATION_EVIDENCE_SCHEMA = "aurum-adaptive-shell-iteration-observation-readiness-evidence-v1"
ITERATION_OBSERVATION_EVIDENCE_KIND = "adaptive-shell-iteration-observation-readiness"
ITERATION_OBSERVATION_EVIDENCE_SOURCE = "aurum-bbpi4-console-status-proof"
GUI_CAPABILITY_EVIDENCE_SCHEMA = "aurum-adaptive-shell-iteration-observation-evidence-v1"
GUI_CAPABILITY_EVIDENCE_KIND = "adaptive-shell-iteration-observation"
GUI_CAPABILITY_EVIDENCE_SOURCE = "aurum-bbpi4-gui-capability-snapshot"
GUI_LIVE_TRIAL_EVIDENCE_SCHEMA = "aurum-adaptive-shell-gui-live-trial-evidence-v1"
GUI_LIVE_TRIAL_EVIDENCE_KIND = "adaptive-shell-gui-live-trial"
GUI_LIVE_TRIAL_EVIDENCE_SOURCE = "aurum-bbpi4-loopback-gui-proof"
GUI_PREFERENCE_TRIAL_EVIDENCE_SCHEMA = "aurum-adaptive-shell-gui-preference-live-trial-evidence-v1"
GUI_PREFERENCE_TRIAL_EVIDENCE_KIND = "adaptive-shell-gui-preference-live-trial"
GUI_PREFERENCE_TRIAL_EVIDENCE_SOURCE = "aurum-bbpi4-reversible-gui-preference-proof"
GUI_KEY_BOOTSTRAP_TRIAL_EVIDENCE_SCHEMA = "aurum-adaptive-shell-gui-key-bootstrap-live-trial-evidence-v1"
GUI_KEY_BOOTSTRAP_TRIAL_EVIDENCE_KIND = "adaptive-shell-gui-key-bootstrap-live-trial"
GUI_KEY_BOOTSTRAP_TRIAL_EVIDENCE_SOURCE = "aurum-windows-pi-one-time-key-bootstrap-proof"
CONSOLE_DEPLOYMENT_EVIDENCE_SCHEMA = "aurum-bbpi4-console-evidence-v1"
WINDOWS_CONTROLLER_NODE_IDS = frozenset({"825e5a7b7d4a7aed", "85404f41d5507372"})
EXTERNAL_EVIDENCE_DIR = Path(__file__).resolve().parents[1] / "autobuild" / "external_evidence"
EVIDENCE_PATH = EXTERNAL_EVIDENCE_DIR / "bbpi4_presence.json"
READINESS_EVIDENCE_PATH = EXTERNAL_EVIDENCE_DIR / "adaptive_shell_live_trial_readiness.json"
TRIAL_EVIDENCE_PATH = EXTERNAL_EVIDENCE_DIR / "adaptive_shell_live_trial.json"
ITERATION_OBSERVATION_EVIDENCE_PATH = EXTERNAL_EVIDENCE_DIR / "adaptive_shell_iteration_observation_readiness.json"
GUI_CAPABILITY_EVIDENCE_PATH = EXTERNAL_EVIDENCE_DIR / "adaptive_shell_iteration_observation.json"
GUI_LIVE_TRIAL_EVIDENCE_PATH = EXTERNAL_EVIDENCE_DIR / "adaptive_shell_gui_live_trial.json"
GUI_PREFERENCE_TRIAL_EVIDENCE_PATH = EXTERNAL_EVIDENCE_DIR / "adaptive_shell_gui_preference_live_trial.json"
GUI_KEY_BOOTSTRAP_TRIAL_EVIDENCE_PATH = EXTERNAL_EVIDENCE_DIR / "adaptive_shell_gui_key_bootstrap_live_trial.json"
CONSOLE_DEPLOYMENT_EVIDENCE_PATH = EXTERNAL_EVIDENCE_DIR / "bbpi4_aurum_console.json"
EVIDENCE_BOUND_GAPS = frozenset(
    {
        "adaptive_shell_live_trial_readiness",
        "adaptive_shell_live_trial",
        "adaptive_shell_iteration_observation_readiness",
        "adaptive_shell_iteration_observation",
        "adaptive_shell_gui_live_trial",
        "adaptive_shell_gui_preference_live_trial",
        "adaptive_shell_gui_key_bootstrap_live_trial",
    }
)
MAX_EVIDENCE_BYTES = 16384
MAX_NODE_AGE_SECONDS = 300
MAX_EVIDENCE_LIFETIME_SECONDS = 1800
MAX_FUTURE_SKEW_SECONDS = 120
USB_SSH_ROUTE = "10.12.194.1"
PERMISSION_SCOPE = "bounded-adaptive-shell-live-trial"
ROLLBACK_METHOD = "neutral-hid-release-and-ephemeral-state"
ITERATION_OBSERVATION_PERMISSION_SCOPE = "adaptive-shell-iteration-observation"
GUI_CAPABILITY_PERMISSION_SCOPE = "adaptive-shell-gui-candidate"
GUI_LIVE_TRIAL_PERMISSION_SCOPE = "adaptive-shell-gui-live-trial"
GUI_PREFERENCE_TRIAL_PERMISSION_SCOPE = "adaptive-shell-gui-preference-live-trial"
GUI_KEY_BOOTSTRAP_TRIAL_PERMISSION_SCOPE = "adaptive-shell-gui-key-bootstrap-live-trial"
GUI_HUMAN_CONSTANTS = frozenset(
    {
        "home",
        "back",
        "search",
        "settings",
        "notifications",
        "workspace-switcher",
        "accessibility",
        "session-power",
        "recovery-safe-layout",
        "adaptation-lock",
    }
)
GUI_LIVE_TRIAL_COMPATIBLE_SCHEMAS = frozenset(
    {"aurum.gui.v1", "aurum.gui.v2", "aurum.gui.v3"}
)


@dataclass(frozen=True)
class ExternalEvidenceApplication:
    spec: NativeSemanticGap
    applied: bool
    reason: str
    evidence: Mapping[str, Any] | None = None


def _bounded_text(value: object, maximum: int) -> str:
    text = str(value or "")
    return text if 0 < len(text) <= maximum else ""


def _hex_digest(value: object) -> str:
    text = _bounded_text(value, 64)
    return text.lower() if re.fullmatch(r"[0-9a-fA-F]{64}", text) else ""


def _evidence_window(
    evidence: Mapping[str, Any],
    *,
    now: int | None,
) -> tuple[tuple[int, int] | None, str | None]:
    try:
        observed_at = int(evidence.get("observed_at"))
        expires_at = int(evidence.get("expires_at"))
    except (TypeError, ValueError):
        return None, "evidence-time-invalid"
    current = int(time.time()) if now is None else int(now)
    if observed_at > current + MAX_FUTURE_SKEW_SECONDS:
        return None, "evidence-time-in-future"
    if expires_at < current:
        return None, "evidence-expired"
    if expires_at <= observed_at or expires_at - observed_at > MAX_EVIDENCE_LIFETIME_SECONDS:
        return None, "evidence-lifetime-invalid"
    return (observed_at, expires_at), None


def _read_evidence(path: Path) -> tuple[Mapping[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "evidence-file-missing"
    if path.stat().st_size > MAX_EVIDENCE_BYTES:
        return None, "evidence-file-too-large"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "evidence-file-invalid"
    if not isinstance(raw, dict):
        return None, "evidence-file-not-object"
    return raw, None


def apply_external_prerequisite_evidence(
    spec: NativeSemanticGap,
    evidence: Mapping[str, Any] | None,
    *,
    now: int | None = None,
) -> ExternalEvidenceApplication:
    """Apply fresh controller-observed BBPI4 presence and nothing else."""
    if spec.name != "adaptive_shell_live_trial_readiness":
        return ExternalEvidenceApplication(spec, False, "gap-not-evidence-bound")
    if "physical_node_present" not in spec.invocation_arguments:
        return ExternalEvidenceApplication(spec, False, "physical-presence-parameter-missing")
    if not isinstance(evidence, Mapping):
        return ExternalEvidenceApplication(spec, False, "evidence-missing")

    if evidence.get("schema") != EVIDENCE_SCHEMA:
        return ExternalEvidenceApplication(spec, False, "evidence-schema-invalid")
    if evidence.get("kind") != BBPI4_PRESENCE_KIND:
        return ExternalEvidenceApplication(spec, False, "evidence-kind-invalid")
    if evidence.get("source") != BBPI4_PRESENCE_SOURCE:
        return ExternalEvidenceApplication(spec, False, "evidence-source-invalid")
    if evidence.get("verified") is not True:
        return ExternalEvidenceApplication(spec, False, "evidence-not-verified")

    node_id = _bounded_text(evidence.get("node_id"), 64)
    node_name = _bounded_text(evidence.get("name"), 128)
    carrier = _bounded_text(evidence.get("carrier"), 64)
    if not node_id or node_id in WINDOWS_CONTROLLER_NODE_IDS:
        return ExternalEvidenceApplication(spec, False, "physical-node-identity-invalid")
    if not node_name or not carrier:
        return ExternalEvidenceApplication(spec, False, "physical-node-description-invalid")

    window, reason = _evidence_window(evidence, now=now)
    if window is None:
        return ExternalEvidenceApplication(spec, False, str(reason))
    observed_at, expires_at = window
    try:
        last_seen = int(evidence.get("last_seen"))
    except (TypeError, ValueError):
        return ExternalEvidenceApplication(spec, False, "evidence-time-invalid")
    if last_seen > observed_at + MAX_FUTURE_SKEW_SECONDS:
        return ExternalEvidenceApplication(spec, False, "evidence-time-in-future")
    if observed_at - last_seen > MAX_NODE_AGE_SECONDS:
        return ExternalEvidenceApplication(spec, False, "physical-node-heartbeat-stale")

    invocation = dict(spec.invocation_arguments)
    invocation["physical_node_present"] = "yes"
    applied_spec = replace(spec, invocation_arguments=invocation)
    trace = {
        "schema": EVIDENCE_SCHEMA,
        "kind": BBPI4_PRESENCE_KIND,
        "source": BBPI4_PRESENCE_SOURCE,
        "node_id": node_id,
        "name": node_name,
        "carrier": carrier,
        "last_seen": last_seen,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "authority_granted": False,
        "permission_granted": False,
        "input_carrier_verified": False,
        "display_carrier_verified": False,
    }
    return ExternalEvidenceApplication(applied_spec, True, "fresh-physical-node-evidence", trace)


def apply_adaptive_shell_live_trial_readiness_evidence(
    spec: NativeSemanticGap,
    evidence: Mapping[str, Any] | None,
    *,
    expected_node_id: str,
    now: int | None = None,
) -> ExternalEvidenceApplication:
    """Bind fresh neutral USB-KVM proof and explicit scoped permission to readiness."""
    if spec.name != "adaptive_shell_live_trial_readiness":
        return ExternalEvidenceApplication(spec, False, "gap-not-readiness-evidence-bound")
    if spec.invocation_arguments.get("physical_node_present") != "yes":
        return ExternalEvidenceApplication(spec, False, "physical-presence-not-verified")
    if not isinstance(evidence, Mapping):
        return ExternalEvidenceApplication(spec, False, "readiness-evidence-missing")
    if evidence.get("schema") != READINESS_EVIDENCE_SCHEMA:
        return ExternalEvidenceApplication(spec, False, "readiness-evidence-schema-invalid")
    if evidence.get("kind") != READINESS_EVIDENCE_KIND:
        return ExternalEvidenceApplication(spec, False, "readiness-evidence-kind-invalid")
    if evidence.get("source") != READINESS_EVIDENCE_SOURCE:
        return ExternalEvidenceApplication(spec, False, "readiness-evidence-source-invalid")
    if evidence.get("verified") is not True:
        return ExternalEvidenceApplication(spec, False, "readiness-evidence-not-verified")

    node_id = _bounded_text(evidence.get("node_id"), 64)
    route = _bounded_text(evidence.get("route"), 64)
    host_key = _bounded_text(evidence.get("ssh_host_key_fingerprint"), 96)
    if not node_id or node_id != expected_node_id:
        return ExternalEvidenceApplication(spec, False, "readiness-node-identity-mismatch")
    if route != USB_SSH_ROUTE:
        return ExternalEvidenceApplication(spec, False, "readiness-route-not-usb-ssh")
    if not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", host_key):
        return ExternalEvidenceApplication(spec, False, "readiness-host-key-invalid")

    window, reason = _evidence_window(evidence, now=now)
    if window is None:
        return ExternalEvidenceApplication(spec, False, f"readiness-{reason}")
    observed_at, expires_at = window

    display = evidence.get("display")
    if not isinstance(display, Mapping) or display.get("verified") is not True:
        return ExternalEvidenceApplication(spec, False, "display-carrier-not-verified")
    content_type = _bounded_text(display.get("content_type"), 128)
    try:
        http_status = int(display.get("http_status"))
        sample_bytes = int(display.get("sample_bytes"))
    except (TypeError, ValueError):
        return ExternalEvidenceApplication(spec, False, "display-proof-invalid")
    display_sha256 = _hex_digest(display.get("sample_sha256"))
    if (
        http_status != 200
        or not content_type.startswith("multipart/x-mixed-replace")
        or not 1024 <= sample_bytes <= 65536
        or not display_sha256
    ):
        return ExternalEvidenceApplication(spec, False, "display-proof-invalid")

    input_proof = evidence.get("input")
    if not isinstance(input_proof, Mapping) or input_proof.get("verified") is not True:
        return ExternalEvidenceApplication(spec, False, "input-carrier-not-verified")
    if (
        input_proof.get("action") != "release"
        or input_proof.get("acknowledged") is not True
        or input_proof.get("before_neutral") is not True
        or input_proof.get("after_neutral") is not True
    ):
        return ExternalEvidenceApplication(spec, False, "input-proof-not-neutral")

    permission = evidence.get("permission")
    if not isinstance(permission, Mapping) or permission.get("present") is not True:
        return ExternalEvidenceApplication(spec, False, "permission-evidence-missing")
    authorization_reference = _bounded_text(permission.get("authorization_reference"), 128)
    if permission.get("scope") != PERMISSION_SCOPE or not authorization_reference:
        return ExternalEvidenceApplication(spec, False, "permission-scope-invalid")

    rollback = evidence.get("rollback")
    if (
        not isinstance(rollback, Mapping)
        or rollback.get("verified") is not True
        or rollback.get("method") != ROLLBACK_METHOD
    ):
        return ExternalEvidenceApplication(spec, False, "rollback-evidence-invalid")
    proof_view = evidence.get("proof_view")
    if (
        not isinstance(proof_view, Mapping)
        or proof_view.get("present") is not True
        or _hex_digest(proof_view.get("display_sample_sha256")) != display_sha256
    ):
        return ExternalEvidenceApplication(spec, False, "proof-view-evidence-invalid")

    invocation = dict(spec.invocation_arguments)
    invocation.update(
        {
            "display_carrier_verified": "yes",
            "input_carrier_verified": "yes",
            "permission_present": "yes",
            "rollback_verified": "yes",
            "proof_view_present": "yes",
        }
    )
    applied_spec = replace(spec, invocation_arguments=invocation)
    trace = {
        "schema": READINESS_EVIDENCE_SCHEMA,
        "kind": READINESS_EVIDENCE_KIND,
        "source": READINESS_EVIDENCE_SOURCE,
        "node_id": node_id,
        "route": route,
        "ssh_host_key_fingerprint": host_key,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "display_carrier_verified": True,
        "display_sample_sha256": display_sha256,
        "input_carrier_verified": True,
        "input_action": "release",
        "permission_verified": True,
        "permission_scope": PERMISSION_SCOPE,
        "authorization_reference": authorization_reference,
        "rollback_verified": True,
        "proof_view_present": True,
        "authority_granted": False,
        "persistent_change_authorized": False,
    }
    return ExternalEvidenceApplication(
        applied_spec,
        True,
        "fresh-bounded-live-trial-readiness-evidence",
        trace,
    )


def apply_adaptive_shell_live_trial_evidence(
    spec: NativeSemanticGap,
    evidence: Mapping[str, Any] | None,
    *,
    now: int | None = None,
) -> ExternalEvidenceApplication:
    """Apply a completed ephemeral trial proof without granting persistent authority."""
    if spec.name != "adaptive_shell_live_trial":
        return ExternalEvidenceApplication(spec, False, "gap-not-trial-evidence-bound")
    if not isinstance(evidence, Mapping):
        return ExternalEvidenceApplication(spec, False, "trial-evidence-missing")
    if evidence.get("schema") != TRIAL_EVIDENCE_SCHEMA:
        return ExternalEvidenceApplication(spec, False, "trial-evidence-schema-invalid")
    if evidence.get("kind") != TRIAL_EVIDENCE_KIND:
        return ExternalEvidenceApplication(spec, False, "trial-evidence-kind-invalid")
    if evidence.get("source") != TRIAL_EVIDENCE_SOURCE:
        return ExternalEvidenceApplication(spec, False, "trial-evidence-source-invalid")
    if evidence.get("verified") is not True:
        return ExternalEvidenceApplication(spec, False, "trial-evidence-not-verified")

    window, reason = _evidence_window(evidence, now=now)
    if window is None:
        return ExternalEvidenceApplication(spec, False, f"trial-{reason}")
    observed_at, expires_at = window
    node_id = _bounded_text(evidence.get("node_id"), 64)
    route = _bounded_text(evidence.get("route"), 64)
    readiness_sha256 = _hex_digest(evidence.get("readiness_evidence_sha256"))
    if not node_id or route != USB_SSH_ROUTE or not readiness_sha256:
        return ExternalEvidenceApplication(spec, False, "trial-binding-invalid")

    proposal = evidence.get("proposal")
    application = evidence.get("application")
    rollback = evidence.get("rollback")
    proof_view = evidence.get("proof_view")
    safety = evidence.get("safety")
    if (
        not isinstance(proposal, Mapping)
        or proposal.get("verified") is not True
        or proposal.get("delta") != "add=terminal;remove=none;evidence=coding-confidence-high"
    ):
        return ExternalEvidenceApplication(spec, False, "trial-proposal-invalid")
    if (
        not isinstance(application, Mapping)
        or application.get("verified") is not True
        or application.get("scope") != "ephemeral-trial-workspace"
        or application.get("persistent") is not False
        or not _hex_digest(application.get("candidate_sha256"))
    ):
        return ExternalEvidenceApplication(spec, False, "trial-application-invalid")
    baseline_sha256 = _hex_digest(rollback.get("baseline_sha256")) if isinstance(rollback, Mapping) else ""
    restored_sha256 = _hex_digest(rollback.get("restored_sha256")) if isinstance(rollback, Mapping) else ""
    if (
        not isinstance(rollback, Mapping)
        or rollback.get("verified") is not True
        or not baseline_sha256
        or restored_sha256 != baseline_sha256
    ):
        return ExternalEvidenceApplication(spec, False, "trial-rollback-invalid")
    if (
        not isinstance(proof_view, Mapping)
        or proof_view.get("present") is not True
        or _hex_digest(proof_view.get("trial_identity")) != _hex_digest(evidence.get("trial_identity"))
    ):
        return ExternalEvidenceApplication(spec, False, "trial-proof-view-invalid")
    if (
        not isinstance(safety, Mapping)
        or safety.get("raw_disk_changed") is not False
        or safety.get("firmware_changed") is not False
        or safety.get("bootloader_changed") is not False
        or safety.get("service_state_changed") is not False
        or safety.get("persistent_interface_changed") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "trial-safety-boundary-invalid")

    invocation = {name: "yes" for name in spec.parameters}
    applied_spec = replace(spec, invocation_arguments=invocation)
    trace = {
        "schema": TRIAL_EVIDENCE_SCHEMA,
        "kind": TRIAL_EVIDENCE_KIND,
        "source": TRIAL_EVIDENCE_SOURCE,
        "node_id": node_id,
        "route": route,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "readiness_evidence_sha256": readiness_sha256,
        "trial_identity": _hex_digest(evidence.get("trial_identity")),
        "proposal_verified": True,
        "ephemeral_application_verified": True,
        "rollback_verified": True,
        "proof_view_present": True,
        "persistent_change": False,
        "authority_granted": False,
    }
    return ExternalEvidenceApplication(
        spec=applied_spec,
        applied=True,
        reason="bounded-live-trial-evidence",
        evidence=trace,
    )


def apply_adaptive_shell_iteration_observation_readiness_evidence(
    spec: NativeSemanticGap,
    evidence: Mapping[str, Any] | None,
    deployment_evidence: Mapping[str, Any] | None,
    *,
    now: int | None = None,
) -> ExternalEvidenceApplication:
    """Bind a fresh dialogue-free console status observation to one iteration."""
    if spec.name != "adaptive_shell_iteration_observation_readiness":
        return ExternalEvidenceApplication(spec, False, "gap-not-iteration-observation-bound")
    if spec.invocation_arguments.get("prior_iteration_closed") != "yes":
        return ExternalEvidenceApplication(spec, False, "prior-iteration-not-closed")
    if not isinstance(evidence, Mapping):
        return ExternalEvidenceApplication(spec, False, "iteration-observation-evidence-missing")
    if not isinstance(deployment_evidence, Mapping):
        return ExternalEvidenceApplication(spec, False, "console-deployment-evidence-missing")
    if (
        deployment_evidence.get("schema") != CONSOLE_DEPLOYMENT_EVIDENCE_SCHEMA
        or deployment_evidence.get("verified") is not True
        or deployment_evidence.get("route") != USB_SSH_ROUTE
    ):
        return ExternalEvidenceApplication(spec, False, "console-deployment-evidence-invalid")

    deployment_console = deployment_evidence.get("console")
    deployment_node_id = _bounded_text(deployment_evidence.get("node_id"), 64)
    deployment_host_key = _bounded_text(
        deployment_evidence.get("ssh_host_key_fingerprint"), 96
    )
    if (
        not deployment_node_id
        or deployment_node_id in WINDOWS_CONTROLLER_NODE_IDS
        or not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", deployment_host_key)
        or not isinstance(deployment_console, Mapping)
        or deployment_console.get("command") != "/usr/local/bin/aurum"
        or not _hex_digest(deployment_console.get("command_sha256"))
        or deployment_console.get("module")
        != "/opt/boxbrain/codelation/seed/aurum_console.py"
        or not _hex_digest(deployment_console.get("module_sha256"))
        or not _hex_digest(deployment_console.get("dialogue_supervisor_sha256"))
        or deployment_console.get("dialogue_only") is not True
        or deployment_console.get("host_actuation") is not False
        or deployment_console.get("api_key_persisted") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "console-deployment-binding-invalid")

    if evidence.get("schema") != ITERATION_OBSERVATION_EVIDENCE_SCHEMA:
        return ExternalEvidenceApplication(spec, False, "iteration-observation-schema-invalid")
    if evidence.get("kind") != ITERATION_OBSERVATION_EVIDENCE_KIND:
        return ExternalEvidenceApplication(spec, False, "iteration-observation-kind-invalid")
    if evidence.get("source") != ITERATION_OBSERVATION_EVIDENCE_SOURCE:
        return ExternalEvidenceApplication(spec, False, "iteration-observation-source-invalid")
    if evidence.get("verified") is not True:
        return ExternalEvidenceApplication(spec, False, "iteration-observation-not-verified")

    window, reason = _evidence_window(evidence, now=now)
    if window is None:
        return ExternalEvidenceApplication(spec, False, f"iteration-observation-{reason}")
    observed_at, expires_at = window
    node_id = _bounded_text(evidence.get("node_id"), 64)
    route = _bounded_text(evidence.get("route"), 64)
    host_key = _bounded_text(evidence.get("ssh_host_key_fingerprint"), 96)
    if (
        node_id != deployment_node_id
        or route != USB_SSH_ROUTE
        or host_key != deployment_host_key
    ):
        return ExternalEvidenceApplication(spec, False, "iteration-observation-node-binding-invalid")

    console = evidence.get("console")
    if not isinstance(console, Mapping) or console.get("status_verified") is not True:
        return ExternalEvidenceApplication(spec, False, "console-status-not-verified")
    try:
        mind_version = int(console.get("mind_version"))
    except (TypeError, ValueError):
        return ExternalEvidenceApplication(spec, False, "console-mind-status-invalid")
    mind_sha256 = _hex_digest(console.get("mind_sha256"))
    command_sha256 = _hex_digest(console.get("command_sha256"))
    module_sha256 = _hex_digest(console.get("module_sha256"))
    dialogue_sha256 = _hex_digest(console.get("dialogue_supervisor_sha256"))
    if (
        console.get("command") != deployment_console.get("command")
        or command_sha256 != _hex_digest(deployment_console.get("command_sha256"))
        or console.get("module") != deployment_console.get("module")
        or module_sha256 != _hex_digest(deployment_console.get("module_sha256"))
        or dialogue_sha256
        != _hex_digest(deployment_console.get("dialogue_supervisor_sha256"))
        or console.get("identity") != "BBPI4/Aurum"
        or mind_version < 1
        or not mind_sha256
        or console.get("dialogue_only") is not True
        or console.get("host_actuation") is not False
        or console.get("api_key_persisted") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "console-mind-status-invalid")

    observation = evidence.get("observation")
    if (
        not isinstance(observation, Mapping)
        or observation.get("type") != "console-status-and-capability-snapshot"
        or observation.get("read_only") is not True
        or observation.get("dialogue_generated") is not False
        or observation.get("user_content_captured") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "iteration-observation-content-boundary-invalid")

    permission = evidence.get("permission")
    authorization_reference = (
        _bounded_text(permission.get("authorization_reference"), 128)
        if isinstance(permission, Mapping)
        else ""
    )
    if (
        not isinstance(permission, Mapping)
        or permission.get("present") is not True
        or permission.get("scope") != ITERATION_OBSERVATION_PERMISSION_SCOPE
        or not authorization_reference
    ):
        return ExternalEvidenceApplication(spec, False, "iteration-observation-permission-invalid")

    proof_view = evidence.get("proof_view")
    if (
        not isinstance(proof_view, Mapping)
        or proof_view.get("present") is not True
        or _hex_digest(proof_view.get("mind_sha256")) != mind_sha256
        or proof_view.get("user_content_captured") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "iteration-observation-proof-view-invalid")
    if (
        evidence.get("authority_granted") is not False
        or evidence.get("persistent_change_authorized") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "iteration-observation-authority-invalid")

    invocation = {name: "yes" for name in spec.parameters}
    applied_spec = replace(spec, invocation_arguments=invocation)
    trace = {
        "schema": ITERATION_OBSERVATION_EVIDENCE_SCHEMA,
        "kind": ITERATION_OBSERVATION_EVIDENCE_KIND,
        "source": ITERATION_OBSERVATION_EVIDENCE_SOURCE,
        "node_id": node_id,
        "route": route,
        "ssh_host_key_fingerprint": host_key,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "console_observation_fresh": True,
        "console_command_sha256": command_sha256,
        "console_module_sha256": module_sha256,
        "dialogue_supervisor_sha256": dialogue_sha256,
        "mind_version": mind_version,
        "mind_sha256": mind_sha256,
        "permission_scope": ITERATION_OBSERVATION_PERMISSION_SCOPE,
        "authorization_reference": authorization_reference,
        "user_content_captured": False,
        "dialogue_generated": False,
        "proof_view_present": True,
        "authority_granted": False,
        "persistent_change_authorized": False,
    }
    return ExternalEvidenceApplication(
        applied_spec,
        True,
        "fresh-console-iteration-observation-readiness-evidence",
        trace,
    )


def apply_adaptive_shell_iteration_observation_evidence(
    spec: NativeSemanticGap,
    evidence: Mapping[str, Any] | None,
    *,
    now: int | None = None,
) -> ExternalEvidenceApplication:
    """Apply a read-only BBPI4 GUI capability snapshot to one iteration."""
    if spec.name != "adaptive_shell_iteration_observation":
        return ExternalEvidenceApplication(spec, False, "gap-not-gui-capability-bound")
    if not isinstance(evidence, Mapping):
        return ExternalEvidenceApplication(spec, False, "gui-capability-evidence-missing")
    if evidence.get("schema") != GUI_CAPABILITY_EVIDENCE_SCHEMA:
        return ExternalEvidenceApplication(spec, False, "gui-capability-schema-invalid")
    if evidence.get("kind") != GUI_CAPABILITY_EVIDENCE_KIND:
        return ExternalEvidenceApplication(spec, False, "gui-capability-kind-invalid")
    if evidence.get("source") != GUI_CAPABILITY_EVIDENCE_SOURCE:
        return ExternalEvidenceApplication(spec, False, "gui-capability-source-invalid")
    if evidence.get("verified") is not True:
        return ExternalEvidenceApplication(spec, False, "gui-capability-not-verified")

    window, reason = _evidence_window(evidence, now=now)
    if window is None:
        return ExternalEvidenceApplication(spec, False, f"gui-capability-{reason}")
    observed_at, expires_at = window
    node_id = _bounded_text(evidence.get("node_id"), 64)
    route = _bounded_text(evidence.get("route"), 64)
    host_key = _bounded_text(evidence.get("ssh_host_key_fingerprint"), 96)
    if (
        not node_id
        or node_id in WINDOWS_CONTROLLER_NODE_IDS
        or route != USB_SSH_ROUTE
        or not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", host_key)
    ):
        return ExternalEvidenceApplication(spec, False, "gui-capability-node-binding-invalid")

    console = evidence.get("console")
    if not isinstance(console, Mapping):
        return ExternalEvidenceApplication(spec, False, "gui-capability-console-invalid")
    try:
        mind_version = int(console.get("mind_version"))
    except (TypeError, ValueError):
        return ExternalEvidenceApplication(spec, False, "gui-capability-console-invalid")
    mind_sha256 = _hex_digest(console.get("mind_sha256"))
    if (
        console.get("identity") != "BBPI4/Aurum"
        or mind_version < 1
        or not mind_sha256
        or console.get("dialogue_only") is not True
        or console.get("host_actuation") is not False
        or console.get("api_key_persisted") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "gui-capability-console-invalid")

    capabilities = evidence.get("capabilities")
    required_commands = {
        "python3": "/usr/bin/python3",
        "browser": "/usr/bin/chromium",
        "virtual_display": "/usr/bin/Xvfb",
        "websocket_bridge": "/usr/bin/websockify",
    }
    if not isinstance(capabilities, Mapping):
        return ExternalEvidenceApplication(spec, False, "gui-runtime-capabilities-invalid")
    for name, expected_path in required_commands.items():
        if capabilities.get(name) != expected_path:
            return ExternalEvidenceApplication(spec, False, "gui-runtime-capabilities-invalid")
    if (
        capabilities.get("python_supported") is not True
        or capabilities.get("gui_port_available") is not True
        or capabilities.get("package_install_required") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "gui-runtime-capabilities-invalid")

    display = evidence.get("display")
    if (
        not isinstance(display, Mapping)
        or display.get("screen_path_installed") is not True
        or display.get("virtual_display_active") is not True
        or display.get("desktop_active") is not True
        or display.get("private_transport") != "strict-ssh-loopback-forward"
    ):
        return ExternalEvidenceApplication(spec, False, "gui-display-path-invalid")

    observation = evidence.get("observation")
    if (
        not isinstance(observation, Mapping)
        or observation.get("read_only") is not True
        or observation.get("dialogue_generated") is not False
        or observation.get("user_content_captured") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "gui-observation-content-boundary-invalid")

    permission = evidence.get("permission")
    authorization_reference = (
        _bounded_text(permission.get("authorization_reference"), 128)
        if isinstance(permission, Mapping)
        else ""
    )
    if (
        not isinstance(permission, Mapping)
        or permission.get("present") is not True
        or permission.get("scope") != GUI_CAPABILITY_PERMISSION_SCOPE
        or not authorization_reference
    ):
        return ExternalEvidenceApplication(spec, False, "gui-capability-permission-invalid")
    proof_view = evidence.get("proof_view")
    capability_sha256 = _hex_digest(evidence.get("capability_snapshot_sha256"))
    if (
        not capability_sha256
        or not isinstance(proof_view, Mapping)
        or proof_view.get("present") is not True
        or _hex_digest(proof_view.get("capability_snapshot_sha256")) != capability_sha256
        or proof_view.get("user_content_captured") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "gui-capability-proof-view-invalid")
    if (
        evidence.get("authority_granted") is not False
        or evidence.get("persistent_change_authorized") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "gui-capability-authority-invalid")

    invocation = {name: "yes" for name in spec.parameters}
    applied_spec = replace(spec, invocation_arguments=invocation)
    trace = {
        "schema": GUI_CAPABILITY_EVIDENCE_SCHEMA,
        "kind": GUI_CAPABILITY_EVIDENCE_KIND,
        "source": GUI_CAPABILITY_EVIDENCE_SOURCE,
        "node_id": node_id,
        "route": route,
        "ssh_host_key_fingerprint": host_key,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "mind_version": mind_version,
        "mind_sha256": mind_sha256,
        "capability_snapshot_sha256": capability_sha256,
        "gui_runtime_present": True,
        "display_path_present": True,
        "gui_port_available": True,
        "permission_scope": GUI_CAPABILITY_PERMISSION_SCOPE,
        "authorization_reference": authorization_reference,
        "user_content_captured": False,
        "authority_granted": False,
    }
    return ExternalEvidenceApplication(
        applied_spec,
        True,
        "fresh-bbpi4-gui-capability-observation",
        trace,
    )


def apply_adaptive_shell_gui_live_trial_evidence(
    spec: NativeSemanticGap,
    evidence: Mapping[str, Any] | None,
    *,
    now: int | None = None,
) -> ExternalEvidenceApplication:
    """Apply proof of a transient loopback Aurum GUI running on BBPI4."""
    if spec.name != "adaptive_shell_gui_live_trial":
        return ExternalEvidenceApplication(spec, False, "gap-not-gui-live-trial-bound")
    if not isinstance(evidence, Mapping):
        return ExternalEvidenceApplication(spec, False, "gui-live-trial-evidence-missing")
    if evidence.get("schema") != GUI_LIVE_TRIAL_EVIDENCE_SCHEMA:
        return ExternalEvidenceApplication(spec, False, "gui-live-trial-schema-invalid")
    if evidence.get("kind") != GUI_LIVE_TRIAL_EVIDENCE_KIND:
        return ExternalEvidenceApplication(spec, False, "gui-live-trial-kind-invalid")
    if evidence.get("source") != GUI_LIVE_TRIAL_EVIDENCE_SOURCE:
        return ExternalEvidenceApplication(spec, False, "gui-live-trial-source-invalid")
    if evidence.get("verified") is not True:
        return ExternalEvidenceApplication(spec, False, "gui-live-trial-not-verified")

    window, reason = _evidence_window(evidence, now=now)
    if window is None:
        return ExternalEvidenceApplication(spec, False, f"gui-live-trial-{reason}")
    observed_at, expires_at = window
    node_id = _bounded_text(evidence.get("node_id"), 64)
    route = _bounded_text(evidence.get("route"), 64)
    host_key = _bounded_text(evidence.get("ssh_host_key_fingerprint"), 96)
    if (
        not node_id
        or node_id in WINDOWS_CONTROLLER_NODE_IDS
        or route != USB_SSH_ROUTE
        or not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", host_key)
    ):
        return ExternalEvidenceApplication(spec, False, "gui-live-trial-node-binding-invalid")

    candidate = evidence.get("candidate")
    gui_schema = (
        _bounded_text(candidate.get("gui_schema"), 32)
        if isinstance(candidate, Mapping)
        else ""
    )
    module_sha256 = (
        _hex_digest(candidate.get("module_sha256"))
        if isinstance(candidate, Mapping)
        else ""
    )
    if (
        not isinstance(candidate, Mapping)
        or candidate.get("module") != "/opt/boxbrain/codelation/seed/aurum_gui.py"
        or not module_sha256
        or gui_schema not in GUI_LIVE_TRIAL_COMPATIBLE_SCHEMAS
        or candidate.get("tests_passed") is not True
    ):
        return ExternalEvidenceApplication(spec, False, "gui-live-trial-candidate-invalid")

    runtime = evidence.get("runtime")
    page_sha256 = _hex_digest(runtime.get("page_sha256")) if isinstance(runtime, Mapping) else ""
    status_sha256 = _hex_digest(runtime.get("status_sha256")) if isinstance(runtime, Mapping) else ""
    if (
        not isinstance(runtime, Mapping)
        or runtime.get("service_active") is not True
        or runtime.get("service_enabled") is not False
        or runtime.get("transient") is not True
        or runtime.get("address") != "127.0.0.1"
        or runtime.get("port") != 8765
        or runtime.get("listener_loopback_only") is not True
        or runtime.get("http_status") != 200
        or not str(runtime.get("content_type", "")).startswith("text/html")
        or not page_sha256
        or not status_sha256
        or runtime.get("status_schema") != gui_schema
        or runtime.get("console_identity") != "BBPI4/Aurum"
    ):
        return ExternalEvidenceApplication(spec, False, "gui-live-trial-runtime-invalid")

    transport = evidence.get("transport")
    if (
        not isinstance(transport, Mapping)
        or transport.get("strict_host_key_checking") is not True
        or transport.get("dedicated_identity") is not True
        or transport.get("usb_route") != USB_SSH_ROUTE
        or transport.get("windows_endpoint_loopback") is not True
        or transport.get("pi_endpoint_loopback") is not True
    ):
        return ExternalEvidenceApplication(spec, False, "gui-live-trial-transport-invalid")

    interface = evidence.get("interface")
    raw_constants = interface.get("human_constants") if isinstance(interface, Mapping) else None
    if (
        not isinstance(interface, Mapping)
        or not isinstance(raw_constants, list)
        or frozenset(str(item) for item in raw_constants) != GUI_HUMAN_CONSTANTS
        or interface.get("safe_layout_available") is not True
        or interface.get("proof_view_present") is not True
        or interface.get("dialogue_only") is not True
        or interface.get("host_actuation") is not False
        or interface.get("api_key_persisted") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "gui-live-trial-interface-invalid")

    safety = evidence.get("safety")
    if (
        not isinstance(safety, Mapping)
        or safety.get("packages_installed") is not False
        or safety.get("persistent_service_enabled") is not False
        or safety.get("raw_disk_changed") is not False
        or safety.get("firmware_changed") is not False
        or safety.get("bootloader_changed") is not False
        or safety.get("security_reduced") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "gui-live-trial-safety-invalid")

    permission = evidence.get("permission")
    authorization_reference = (
        _bounded_text(permission.get("authorization_reference"), 128)
        if isinstance(permission, Mapping)
        else ""
    )
    if (
        not isinstance(permission, Mapping)
        or permission.get("present") is not True
        or permission.get("scope") != GUI_LIVE_TRIAL_PERMISSION_SCOPE
        or not authorization_reference
    ):
        return ExternalEvidenceApplication(spec, False, "gui-live-trial-permission-invalid")
    proof_view = evidence.get("proof_view")
    if (
        not isinstance(proof_view, Mapping)
        or proof_view.get("present") is not True
        or _hex_digest(proof_view.get("page_sha256")) != page_sha256
        or _hex_digest(proof_view.get("status_sha256")) != status_sha256
        or proof_view.get("user_content_captured") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "gui-live-trial-proof-view-invalid")
    if (
        evidence.get("authority_granted") is not False
        or evidence.get("persistent_service_enabled") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "gui-live-trial-authority-invalid")

    invocation = {name: "yes" for name in spec.parameters}
    applied_spec = replace(spec, invocation_arguments=invocation)
    trace = {
        "schema": GUI_LIVE_TRIAL_EVIDENCE_SCHEMA,
        "kind": GUI_LIVE_TRIAL_EVIDENCE_KIND,
        "source": GUI_LIVE_TRIAL_EVIDENCE_SOURCE,
        "node_id": node_id,
        "route": route,
        "ssh_host_key_fingerprint": host_key,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "module_sha256": module_sha256,
        "page_sha256": page_sha256,
        "status_sha256": status_sha256,
        "gui_schema": gui_schema,
        "console_identity": "BBPI4/Aurum",
        "loopback_only": True,
        "safe_layout_available": True,
        "proof_view_present": True,
        "dialogue_only": True,
        "api_key_persisted": False,
        "permission_scope": GUI_LIVE_TRIAL_PERMISSION_SCOPE,
        "authorization_reference": authorization_reference,
        "user_content_captured": False,
        "authority_granted": False,
        "persistent_service_enabled": False,
    }
    return ExternalEvidenceApplication(
        applied_spec,
        True,
        "bounded-bbpi4-aurum-gui-live-trial",
        trace,
    )


def apply_adaptive_shell_gui_preference_live_trial_evidence(
    spec: NativeSemanticGap,
    evidence: Mapping[str, Any] | None,
    *,
    now: int | None = None,
) -> ExternalEvidenceApplication:
    """Apply a reversible, revision-guarded GUI preference trial proof."""
    if spec.name != "adaptive_shell_gui_preference_live_trial":
        return ExternalEvidenceApplication(spec, False, "gap-not-gui-preference-trial-bound")
    if not isinstance(evidence, Mapping):
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-evidence-missing")
    if evidence.get("schema") != GUI_PREFERENCE_TRIAL_EVIDENCE_SCHEMA:
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-schema-invalid")
    if evidence.get("kind") != GUI_PREFERENCE_TRIAL_EVIDENCE_KIND:
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-kind-invalid")
    if evidence.get("source") != GUI_PREFERENCE_TRIAL_EVIDENCE_SOURCE:
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-source-invalid")
    if evidence.get("verified") is not True:
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-not-verified")

    window, reason = _evidence_window(evidence, now=now)
    if window is None:
        return ExternalEvidenceApplication(spec, False, f"gui-preference-trial-{reason}")
    observed_at, expires_at = window
    node_id = _bounded_text(evidence.get("node_id"), 64)
    route = _bounded_text(evidence.get("route"), 64)
    host_key = _bounded_text(evidence.get("ssh_host_key_fingerprint"), 96)
    if (
        not node_id
        or node_id in WINDOWS_CONTROLLER_NODE_IDS
        or route != USB_SSH_ROUTE
        or not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", host_key)
    ):
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-node-binding-invalid")

    candidate = evidence.get("candidate")
    gui_schema = (
        _bounded_text(candidate.get("gui_schema"), 32)
        if isinstance(candidate, Mapping)
        else ""
    )
    module_sha256 = (
        _hex_digest(candidate.get("module_sha256"))
        if isinstance(candidate, Mapping)
        else ""
    )
    if (
        not isinstance(candidate, Mapping)
        or candidate.get("module") != "/opt/boxbrain/codelation/seed/aurum_gui.py"
        or not module_sha256
        or gui_schema not in GUI_LIVE_TRIAL_COMPATIBLE_SCHEMAS
        or candidate.get("preference_schema") != "aurum.gui.preferences.v1"
        or candidate.get("tests_passed") is not True
    ):
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-candidate-invalid")

    runtime = evidence.get("runtime")
    status_sha256 = _hex_digest(runtime.get("status_sha256")) if isinstance(runtime, Mapping) else ""
    if (
        not isinstance(runtime, Mapping)
        or runtime.get("service_active") is not True
        or runtime.get("service_enabled") is not False
        or runtime.get("transient") is not True
        or runtime.get("address") != "127.0.0.1"
        or runtime.get("port") != 8765
        or runtime.get("listener_loopback_only") is not True
        or runtime.get("status_schema") != gui_schema
        or not status_sha256
    ):
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-runtime-invalid")

    trial = evidence.get("trial")
    if not isinstance(trial, Mapping):
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-proof-invalid")
    baseline = trial.get("baseline")
    proposal = trial.get("proposal")
    application = trial.get("application")
    rollback = trial.get("rollback")
    if not all(isinstance(item, Mapping) for item in (baseline, proposal, application, rollback)):
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-proof-invalid")
    try:
        baseline_revision = int(baseline.get("revision"))
        application_revision = int(application.get("revision"))
        rollback_revision = int(rollback.get("revision"))
    except (TypeError, ValueError):
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-revision-invalid")
    baseline_sha256 = _hex_digest(baseline.get("state_sha256"))
    restored_sha256 = _hex_digest(rollback.get("state_sha256"))
    if (
        not isinstance(baseline.get("safe_layout"), bool)
        or not isinstance(baseline.get("adaptation_locked"), bool)
        or baseline_revision < 0
        or not baseline_sha256
        or proposal.get("field") != "safe_layout"
        or proposal.get("from") is not baseline.get("safe_layout")
        or not isinstance(proposal.get("to"), bool)
        or proposal.get("to") is baseline.get("safe_layout")
        or trial.get("stale_revision_rejected") is not True
        or application.get("verified") is not True
        or application_revision != baseline_revision + 1
        or application.get("safe_layout") is not proposal.get("to")
        or application.get("adaptation_locked") is not baseline.get("adaptation_locked")
        or rollback.get("verified") is not True
        or rollback_revision != baseline_revision + 2
        or rollback.get("safe_layout") is not baseline.get("safe_layout")
        or rollback.get("adaptation_locked") is not baseline.get("adaptation_locked")
        or restored_sha256 != baseline_sha256
        or trial.get("revision_monotonic") is not True
    ):
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-proof-invalid")

    interface = evidence.get("interface")
    raw_constants = interface.get("human_constants") if isinstance(interface, Mapping) else None
    if (
        not isinstance(interface, Mapping)
        or not isinstance(raw_constants, list)
        or frozenset(str(item) for item in raw_constants) != GUI_HUMAN_CONSTANTS
        or interface.get("safe_layout_available") is not True
        or interface.get("adaptation_lock_available") is not True
        or interface.get("proof_view_present") is not True
        or interface.get("preference_path")
        != "/opt/boxbrain/codelation/state/interface/gui_preferences.json"
        or interface.get("user_content_captured") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-interface-invalid")

    transport = evidence.get("transport")
    if (
        not isinstance(transport, Mapping)
        or transport.get("strict_host_key_checking") is not True
        or transport.get("dedicated_identity") is not True
        or transport.get("usb_route") != USB_SSH_ROUTE
        or transport.get("windows_endpoint_loopback") is not True
        or transport.get("pi_endpoint_loopback") is not True
    ):
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-transport-invalid")
    safety = evidence.get("safety")
    if (
        not isinstance(safety, Mapping)
        or safety.get("packages_installed") is not False
        or safety.get("persistent_service_enabled") is not False
        or safety.get("dialogue_generated") is not False
        or safety.get("api_key_persisted") is not False
        or safety.get("raw_disk_changed") is not False
        or safety.get("firmware_changed") is not False
        or safety.get("bootloader_changed") is not False
        or safety.get("host_actuation") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-safety-invalid")

    permission = evidence.get("permission")
    authorization_reference = (
        _bounded_text(permission.get("authorization_reference"), 128)
        if isinstance(permission, Mapping)
        else ""
    )
    if (
        not isinstance(permission, Mapping)
        or permission.get("present") is not True
        or permission.get("scope") != GUI_PREFERENCE_TRIAL_PERMISSION_SCOPE
        or not authorization_reference
    ):
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-permission-invalid")
    proof_view = evidence.get("proof_view")
    if (
        not isinstance(proof_view, Mapping)
        or proof_view.get("present") is not True
        or _hex_digest(proof_view.get("baseline_state_sha256")) != baseline_sha256
        or _hex_digest(proof_view.get("restored_state_sha256")) != restored_sha256
        or proof_view.get("user_content_captured") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-proof-view-invalid")
    if evidence.get("authority_granted") is not False:
        return ExternalEvidenceApplication(spec, False, "gui-preference-trial-authority-invalid")

    invocation = {name: "yes" for name in spec.parameters}
    applied_spec = replace(spec, invocation_arguments=invocation)
    trace = {
        "schema": GUI_PREFERENCE_TRIAL_EVIDENCE_SCHEMA,
        "kind": GUI_PREFERENCE_TRIAL_EVIDENCE_KIND,
        "source": GUI_PREFERENCE_TRIAL_EVIDENCE_SOURCE,
        "node_id": node_id,
        "route": route,
        "ssh_host_key_fingerprint": host_key,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "module_sha256": module_sha256,
        "status_sha256": status_sha256,
        "gui_schema": gui_schema,
        "preference_schema": "aurum.gui.preferences.v1",
        "baseline_revision": baseline_revision,
        "restored_revision": rollback_revision,
        "baseline_state_sha256": baseline_sha256,
        "restored_state_sha256": restored_sha256,
        "revision_guard_verified": True,
        "apply_verified": True,
        "rollback_verified": True,
        "safe_layout_available": True,
        "adaptation_lock_available": True,
        "proof_view_present": True,
        "permission_scope": GUI_PREFERENCE_TRIAL_PERMISSION_SCOPE,
        "authorization_reference": authorization_reference,
        "user_content_captured": False,
        "authority_granted": False,
    }
    return ExternalEvidenceApplication(
        applied_spec,
        True,
        "bounded-bbpi4-gui-preference-live-trial",
        trace,
    )


def apply_adaptive_shell_gui_key_bootstrap_live_trial_evidence(
    spec: NativeSemanticGap,
    evidence: Mapping[str, Any] | None,
    *,
    now: int | None = None,
) -> ExternalEvidenceApplication:
    """Apply a content-free, one-time GUI key-bootstrap trial proof."""
    if spec.name != "adaptive_shell_gui_key_bootstrap_live_trial":
        return ExternalEvidenceApplication(spec, False, "gap-not-gui-key-bootstrap-trial-bound")
    if not isinstance(evidence, Mapping):
        return ExternalEvidenceApplication(spec, False, "gui-key-bootstrap-trial-evidence-missing")
    if evidence.get("schema") != GUI_KEY_BOOTSTRAP_TRIAL_EVIDENCE_SCHEMA:
        return ExternalEvidenceApplication(spec, False, "gui-key-bootstrap-trial-schema-invalid")
    if evidence.get("kind") != GUI_KEY_BOOTSTRAP_TRIAL_EVIDENCE_KIND:
        return ExternalEvidenceApplication(spec, False, "gui-key-bootstrap-trial-kind-invalid")
    if evidence.get("source") != GUI_KEY_BOOTSTRAP_TRIAL_EVIDENCE_SOURCE:
        return ExternalEvidenceApplication(spec, False, "gui-key-bootstrap-trial-source-invalid")
    if evidence.get("verified") is not True:
        return ExternalEvidenceApplication(spec, False, "gui-key-bootstrap-trial-not-verified")

    window, reason = _evidence_window(evidence, now=now)
    if window is None:
        return ExternalEvidenceApplication(spec, False, f"gui-key-bootstrap-trial-{reason}")
    observed_at, expires_at = window
    node_id = _bounded_text(evidence.get("node_id"), 64)
    route = _bounded_text(evidence.get("route"), 64)
    host_key = _bounded_text(evidence.get("ssh_host_key_fingerprint"), 96)
    if (
        not node_id
        or node_id in WINDOWS_CONTROLLER_NODE_IDS
        or route != USB_SSH_ROUTE
        or not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", host_key)
    ):
        return ExternalEvidenceApplication(spec, False, "gui-key-bootstrap-trial-node-binding-invalid")

    candidate = evidence.get("candidate")
    module_sha256 = (
        _hex_digest(candidate.get("module_sha256"))
        if isinstance(candidate, Mapping)
        else ""
    )
    if (
        not isinstance(candidate, Mapping)
        or candidate.get("module") != "/opt/boxbrain/codelation/seed/aurum_gui.py"
        or not module_sha256
        or candidate.get("gui_schema") != "aurum.gui.v3"
        or candidate.get("key_bootstrap_schema") != "aurum.gui.key-bootstrap.v1"
        or candidate.get("tests_passed") is not True
    ):
        return ExternalEvidenceApplication(spec, False, "gui-key-bootstrap-trial-candidate-invalid")

    runtime = evidence.get("runtime")
    status_sha256 = _hex_digest(runtime.get("status_sha256")) if isinstance(runtime, Mapping) else ""
    if (
        not isinstance(runtime, Mapping)
        or runtime.get("service_active") is not True
        or runtime.get("service_enabled") is not False
        or runtime.get("transient") is not True
        or runtime.get("address") != "127.0.0.1"
        or runtime.get("port") != 8765
        or runtime.get("listener_loopback_only") is not True
        or runtime.get("status_schema") != "aurum.gui.v3"
        or not status_sha256
    ):
        return ExternalEvidenceApplication(spec, False, "gui-key-bootstrap-trial-runtime-invalid")

    trial = evidence.get("trial")
    before_sha256 = (
        _hex_digest(trial.get("persistence_surface_before_sha256"))
        if isinstance(trial, Mapping)
        else ""
    )
    after_sha256 = (
        _hex_digest(trial.get("persistence_surface_after_sha256"))
        if isinstance(trial, Mapping)
        else ""
    )
    try:
        expiry_wait_seconds = int(trial.get("expiry_wait_seconds"))
    except (AttributeError, TypeError, ValueError):
        expiry_wait_seconds = -1
    if (
        not isinstance(trial, Mapping)
        or trial.get("stage_verified") is not True
        or trial.get("single_consume_verified") is not True
        or trial.get("second_consume_empty") is not True
        or trial.get("expiry_verified") is not True
        or trial.get("expired_consume_empty") is not True
        or trial.get("pending_before") is not False
        or trial.get("pending_after") is not False
        or trial.get("ttl_seconds") != 60
        or expiry_wait_seconds < 60
        or trial.get("synthetic_noncredential") is not True
        or trial.get("actual_api_key_observed") is not False
        or not before_sha256
        or after_sha256 != before_sha256
    ):
        return ExternalEvidenceApplication(spec, False, "gui-key-bootstrap-trial-proof-invalid")

    interface = evidence.get("interface")
    if (
        not isinstance(interface, Mapping)
        or interface.get("page_memory_assignment_present") is not True
        or interface.get("bounded_poll_present") is not True
        or interface.get("proof_view_present") is not True
        or interface.get("user_content_captured") is not False
        or interface.get("credential_content_captured") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "gui-key-bootstrap-trial-interface-invalid")
    transport = evidence.get("transport")
    if (
        not isinstance(transport, Mapping)
        or transport.get("strict_host_key_checking") is not True
        or transport.get("dedicated_identity") is not True
        or transport.get("usb_route") != USB_SSH_ROUTE
        or transport.get("windows_endpoint_loopback") is not True
        or transport.get("pi_endpoint_loopback") is not True
        or transport.get("csrf_verified") is not True
        or transport.get("origin_verified") is not True
    ):
        return ExternalEvidenceApplication(spec, False, "gui-key-bootstrap-trial-transport-invalid")
    safety = evidence.get("safety")
    if (
        not isinstance(safety, Mapping)
        or safety.get("packages_installed") is not False
        or safety.get("persistent_service_enabled") is not False
        or safety.get("dialogue_generated") is not False
        or safety.get("api_key_persisted") is not False
        or safety.get("api_key_logged") is not False
        or safety.get("api_key_in_url") is not False
        or safety.get("raw_disk_changed") is not False
        or safety.get("firmware_changed") is not False
        or safety.get("bootloader_changed") is not False
        or safety.get("host_actuation") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "gui-key-bootstrap-trial-safety-invalid")

    permission = evidence.get("permission")
    authorization_reference = (
        _bounded_text(permission.get("authorization_reference"), 128)
        if isinstance(permission, Mapping)
        else ""
    )
    if (
        not isinstance(permission, Mapping)
        or permission.get("present") is not True
        or permission.get("scope") != GUI_KEY_BOOTSTRAP_TRIAL_PERMISSION_SCOPE
        or not authorization_reference
    ):
        return ExternalEvidenceApplication(spec, False, "gui-key-bootstrap-trial-permission-invalid")
    proof_view = evidence.get("proof_view")
    if (
        not isinstance(proof_view, Mapping)
        or proof_view.get("present") is not True
        or _hex_digest(proof_view.get("status_sha256")) != status_sha256
        or _hex_digest(proof_view.get("persistence_surface_sha256")) != before_sha256
        or proof_view.get("user_content_captured") is not False
        or proof_view.get("credential_content_captured") is not False
    ):
        return ExternalEvidenceApplication(spec, False, "gui-key-bootstrap-trial-proof-view-invalid")
    if evidence.get("authority_granted") is not False:
        return ExternalEvidenceApplication(spec, False, "gui-key-bootstrap-trial-authority-invalid")

    invocation = {name: "yes" for name in spec.parameters}
    applied_spec = replace(spec, invocation_arguments=invocation)
    trace = {
        "schema": GUI_KEY_BOOTSTRAP_TRIAL_EVIDENCE_SCHEMA,
        "kind": GUI_KEY_BOOTSTRAP_TRIAL_EVIDENCE_KIND,
        "source": GUI_KEY_BOOTSTRAP_TRIAL_EVIDENCE_SOURCE,
        "node_id": node_id,
        "route": route,
        "ssh_host_key_fingerprint": host_key,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "module_sha256": module_sha256,
        "status_sha256": status_sha256,
        "gui_schema": "aurum.gui.v3",
        "key_bootstrap_schema": "aurum.gui.key-bootstrap.v1",
        "stage_verified": True,
        "single_consume_verified": True,
        "expiry_verified": True,
        "persistence_surface_sha256": before_sha256,
        "synthetic_noncredential": True,
        "actual_api_key_observed": False,
        "permission_scope": GUI_KEY_BOOTSTRAP_TRIAL_PERMISSION_SCOPE,
        "authorization_reference": authorization_reference,
        "user_content_captured": False,
        "credential_content_captured": False,
        "authority_granted": False,
    }
    return ExternalEvidenceApplication(
        applied_spec,
        True,
        "bounded-bbpi4-gui-key-bootstrap-live-trial",
        trace,
    )


def apply_external_prerequisite_evidence_from_file(
    spec: NativeSemanticGap,
    *,
    path: Path = EVIDENCE_PATH,
    readiness_path: Path = READINESS_EVIDENCE_PATH,
    trial_path: Path = TRIAL_EVIDENCE_PATH,
    iteration_observation_path: Path = ITERATION_OBSERVATION_EVIDENCE_PATH,
    gui_capability_path: Path = GUI_CAPABILITY_EVIDENCE_PATH,
    gui_live_trial_path: Path = GUI_LIVE_TRIAL_EVIDENCE_PATH,
    gui_preference_trial_path: Path = GUI_PREFERENCE_TRIAL_EVIDENCE_PATH,
    gui_key_bootstrap_trial_path: Path = GUI_KEY_BOOTSTRAP_TRIAL_EVIDENCE_PATH,
    console_deployment_path: Path = CONSOLE_DEPLOYMENT_EVIDENCE_PATH,
    now: int | None = None,
) -> ExternalEvidenceApplication:
    if spec.name == "adaptive_shell_gui_key_bootstrap_live_trial":
        raw, reason = _read_evidence(gui_key_bootstrap_trial_path)
        if raw is None:
            return ExternalEvidenceApplication(spec, False, f"gui-key-bootstrap-trial-{reason}")
        return apply_adaptive_shell_gui_key_bootstrap_live_trial_evidence(
            spec,
            raw,
            now=now,
        )
    if spec.name == "adaptive_shell_gui_preference_live_trial":
        raw, reason = _read_evidence(gui_preference_trial_path)
        if raw is None:
            return ExternalEvidenceApplication(spec, False, f"gui-preference-trial-{reason}")
        return apply_adaptive_shell_gui_preference_live_trial_evidence(
            spec,
            raw,
            now=now,
        )
    if spec.name == "adaptive_shell_gui_live_trial":
        raw, reason = _read_evidence(gui_live_trial_path)
        if raw is None:
            return ExternalEvidenceApplication(spec, False, f"gui-live-trial-{reason}")
        return apply_adaptive_shell_gui_live_trial_evidence(spec, raw, now=now)
    if spec.name == "adaptive_shell_iteration_observation":
        raw, reason = _read_evidence(gui_capability_path)
        if raw is None:
            return ExternalEvidenceApplication(spec, False, f"gui-capability-{reason}")
        return apply_adaptive_shell_iteration_observation_evidence(spec, raw, now=now)
    if spec.name == "adaptive_shell_iteration_observation_readiness":
        raw, reason = _read_evidence(iteration_observation_path)
        if raw is None:
            return ExternalEvidenceApplication(spec, False, f"iteration-observation-{reason}")
        deployment_raw, deployment_reason = _read_evidence(console_deployment_path)
        if deployment_raw is None:
            return ExternalEvidenceApplication(
                spec,
                False,
                f"console-deployment-{deployment_reason}",
            )
        return apply_adaptive_shell_iteration_observation_readiness_evidence(
            spec,
            raw,
            deployment_raw,
            now=now,
        )
    if spec.name == "adaptive_shell_live_trial":
        raw, reason = _read_evidence(trial_path)
        if raw is None:
            return ExternalEvidenceApplication(spec, False, f"trial-{reason}")
        return apply_adaptive_shell_live_trial_evidence(spec, raw, now=now)
    if spec.name != "adaptive_shell_live_trial_readiness":
        return ExternalEvidenceApplication(spec, False, "gap-not-evidence-bound")

    physical_raw, reason = _read_evidence(path)
    if physical_raw is None:
        return ExternalEvidenceApplication(spec, False, str(reason))
    physical = apply_external_prerequisite_evidence(spec, physical_raw, now=now)
    if not physical.applied or physical.evidence is None:
        return physical

    readiness_raw, readiness_reason = _read_evidence(readiness_path)
    if readiness_raw is None:
        trace = dict(physical.evidence)
        trace["readiness_evidence_reason"] = readiness_reason
        return ExternalEvidenceApplication(
            physical.spec,
            True,
            f"fresh-physical-node-evidence;readiness-{readiness_reason}",
            trace,
        )
    readiness = apply_adaptive_shell_live_trial_readiness_evidence(
        physical.spec,
        readiness_raw,
        expected_node_id=str(physical.evidence["node_id"]),
        now=now,
    )
    if not readiness.applied or readiness.evidence is None:
        trace = dict(physical.evidence)
        trace["readiness_evidence_reason"] = readiness.reason
        return ExternalEvidenceApplication(
            physical.spec,
            True,
            f"fresh-physical-node-evidence;{readiness.reason}",
            trace,
        )
    trace = dict(readiness.evidence)
    trace["physical_presence"] = dict(physical.evidence)
    return ExternalEvidenceApplication(readiness.spec, True, readiness.reason, trace)


__all__ = [
    "BBPI4_PRESENCE_KIND",
    "BBPI4_PRESENCE_SOURCE",
    "EVIDENCE_BOUND_GAPS",
    "EVIDENCE_PATH",
    "EVIDENCE_SCHEMA",
    "ExternalEvidenceApplication",
    "PERMISSION_SCOPE",
    "CONSOLE_DEPLOYMENT_EVIDENCE_PATH",
    "CONSOLE_DEPLOYMENT_EVIDENCE_SCHEMA",
    "GUI_CAPABILITY_EVIDENCE_KIND",
    "GUI_CAPABILITY_EVIDENCE_PATH",
    "GUI_CAPABILITY_EVIDENCE_SCHEMA",
    "GUI_CAPABILITY_EVIDENCE_SOURCE",
    "GUI_CAPABILITY_PERMISSION_SCOPE",
    "GUI_HUMAN_CONSTANTS",
    "GUI_LIVE_TRIAL_EVIDENCE_KIND",
    "GUI_LIVE_TRIAL_EVIDENCE_PATH",
    "GUI_LIVE_TRIAL_EVIDENCE_SCHEMA",
    "GUI_LIVE_TRIAL_EVIDENCE_SOURCE",
    "GUI_LIVE_TRIAL_PERMISSION_SCOPE",
    "GUI_PREFERENCE_TRIAL_EVIDENCE_KIND",
    "GUI_PREFERENCE_TRIAL_EVIDENCE_PATH",
    "GUI_PREFERENCE_TRIAL_EVIDENCE_SCHEMA",
    "GUI_PREFERENCE_TRIAL_EVIDENCE_SOURCE",
    "GUI_PREFERENCE_TRIAL_PERMISSION_SCOPE",
    "GUI_KEY_BOOTSTRAP_TRIAL_EVIDENCE_KIND",
    "GUI_KEY_BOOTSTRAP_TRIAL_EVIDENCE_PATH",
    "GUI_KEY_BOOTSTRAP_TRIAL_EVIDENCE_SCHEMA",
    "GUI_KEY_BOOTSTRAP_TRIAL_EVIDENCE_SOURCE",
    "GUI_KEY_BOOTSTRAP_TRIAL_PERMISSION_SCOPE",
    "ITERATION_OBSERVATION_EVIDENCE_KIND",
    "ITERATION_OBSERVATION_EVIDENCE_PATH",
    "ITERATION_OBSERVATION_EVIDENCE_SCHEMA",
    "ITERATION_OBSERVATION_EVIDENCE_SOURCE",
    "ITERATION_OBSERVATION_PERMISSION_SCOPE",
    "READINESS_EVIDENCE_KIND",
    "READINESS_EVIDENCE_PATH",
    "READINESS_EVIDENCE_SCHEMA",
    "READINESS_EVIDENCE_SOURCE",
    "ROLLBACK_METHOD",
    "TRIAL_EVIDENCE_KIND",
    "TRIAL_EVIDENCE_PATH",
    "TRIAL_EVIDENCE_SCHEMA",
    "TRIAL_EVIDENCE_SOURCE",
    "USB_SSH_ROUTE",
    "apply_adaptive_shell_live_trial_evidence",
    "apply_adaptive_shell_live_trial_readiness_evidence",
    "apply_adaptive_shell_iteration_observation_readiness_evidence",
    "apply_adaptive_shell_iteration_observation_evidence",
    "apply_adaptive_shell_gui_live_trial_evidence",
    "apply_adaptive_shell_gui_preference_live_trial_evidence",
    "apply_adaptive_shell_gui_key_bootstrap_live_trial_evidence",
    "apply_external_prerequisite_evidence",
    "apply_external_prerequisite_evidence_from_file",
]
