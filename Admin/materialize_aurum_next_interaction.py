#!/usr/bin/env python3
"""Materialize a ready-to-render Future Branch next-interaction packet.

This is a zero-authority projection. It turns the current Future Branch interaction
frontier into a compact packet that can be consumed on the user's next real
interaction. It never schedules a message, grants authority, changes recovery
state, mutates LKG, or infers physical proof.

Important: authority/action freshness can expire without a repository write. The
packet therefore treats all authority-like live-control values as a snapshot only
and requires a fresh Action Ownership / canonical-evidence read at consumption
before any human-only or destructive step may be surfaced.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRANCH = ROOT / "Projects/Aurum/future-branches.json"
PACKET = ROOT / "Projects/Aurum/next-interaction-packet.json"
SEED = ROOT / "Prompts/FutureBranchSeed.txt"
HANDOFF_SENTENCE = (
    "Future Branch handoff: next-interaction packet materialized from current canonical "
    "evidence; activation is the next real interaction, not a clock; consumption proof "
    "is not yet verified; any human/destructive boundary must be revalidated live at consumption."
)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def stable_digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def require_seed_contract(text: str) -> None:
    required = (
        "INTERACTION — treat likely next user questions and status checks as first-class Future Branches.",
        "maintain a parallel interaction frontier.",
        "HANDOFF — continuously materialize a ready-to-render next-interaction packet",
        "activated by the user's next real interaction, not by a clock.",
        "Never create a scheduled morning report, reminder, or notification to simulate prediction.",
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise ValueError(f"Future Branch interaction/handoff contract incomplete: {missing}")


def _post_flash_ready(live_controls: dict | None) -> bool:
    return bool(
        isinstance(live_controls, dict)
        and live_controls.get("current_release_flash_ready_to_boot") is True
        and live_controls.get("flash_receipt_matches_current_release") is True
    )


def _post_flash_program() -> str:
    return (
        "Current-release Tiny Seed media is READY_TO_BOOT with matching full raw-readback proof; "
        "effective next gate=physical-hopper-boot-proof. The canonical release remains "
        "READY_TO_FLASH as an artifact state, but another media write is not required unless "
        "later evidence invalidates the media/provenance or a new bounded flash cycle is explicitly "
        "started. Physical Hopper boot proof and Guardian forced-rollback proof remain unverified. "
        "Canonical evidence may prepare a branch but never grants destructive authority or physical proof."
    )


def _normalize_post_flash_inputs(inputs: list[object], enabled: bool) -> list[object]:
    """Remove stale flash-as-next-step truth after current media is readback proven.

    The preflight and old authorization branch remain historical evidence, but they
    must not stay ranked above the physical boot outcome once the exact current
    release has a matching READY_TO_BOOT receipt.
    """
    if not enabled:
        return inputs

    preferred = {
        "physical-result-success": 0,
        "physical-result-mixed": 1,
        "physical-result-failure": 2,
        "status-or-so": 3,
        "generic-prompt-intent-expansion": 4,
    }
    normalized: list[object] = []
    for value in inputs:
        if not isinstance(value, dict):
            normalized.append(value)
            continue
        item = dict(value)
        family = item.get("input_family")
        if family == "status-or-so":
            item["prepared_response"] = _post_flash_program()
            item["action_if_safe"] = (
                "Re-read the matching current-release flash receipt and current completion graph, "
                "then continue only toward physical Hopper boot-proof collection; do not request or "
                "infer another media write."
            )
        elif family == "generic-prompt-intent-expansion":
            item["prepared_response"] = (
                "Treat a generic continuation prompt against the proven post-flash state: current-release "
                "media is READY_TO_BOOT and the effective next gate is physical-hopper-boot-proof. "
                "Do all shared safe reversible work, but never infer physical boot success."
            )
            item["action_if_safe"] = (
                "Advance boot-proof preparation and evidence handling from the matching readback-verified "
                "receipt without granting a new write."
            )
        elif family == "explicit-guarded-flash-authorization":
            item["prepared_response"] = (
                "Do not request another flash by default. The current release already has a matching "
                "readback-verified READY_TO_BOOT receipt; a new bounded flash cycle requires fresh evidence "
                "that the existing media is invalid or an explicit decision to replace it."
            )
            item["action_if_safe"] = (
                "Keep new write authority false and continue to physical boot proof unless later evidence "
                "invalidates the media/provenance."
            )
        normalized.append(item)

    sortable = [item for item in normalized if isinstance(item, dict) and isinstance(item.get("rank"), int)]
    sortable.sort(
        key=lambda item: (
            preferred.get(str(item.get("input_family")), 100),
            int(item["rank"]),
            str(item.get("input_family", "")),
        )
    )
    for rank, item in enumerate(sortable, start=1):
        item["rank"] = rank
    rank_by_family = {
        str(item.get("input_family")): int(item["rank"])
        for item in sortable
        if isinstance(item.get("input_family"), str)
    }
    for item in normalized:
        if isinstance(item, dict) and isinstance(item.get("input_family"), str):
            rank = rank_by_family.get(item["input_family"])
            if rank is not None:
                item["rank"] = rank
    return sorted(
        normalized,
        key=lambda item: (
            int(item.get("rank", 10**9)) if isinstance(item, dict) else 10**9,
            str(item.get("input_family", "")) if isinstance(item, dict) else "",
        ),
    )


def _post_flash_frontier(candidates: list[dict], live_controls: dict | None) -> list[dict]:
    """Promote physical-boot outcomes after current-release raw readback is proven.

    A stale preflight may still name flash authorization as its historical next gate.
    Once a matching current-release READY_TO_BOOT receipt exists, interaction planning
    must stop treating another flash as the leading future. This changes prediction
    order only; it grants no authority and infers no boot success.
    """

    if not _post_flash_ready(live_controls):
        return sorted(candidates, key=lambda item: item["rank"])

    preferred = {
        "physical-result-success": 0,
        "physical-result-mixed": 1,
        "physical-result-failure": 2,
        "status-or-so": 3,
        "generic-prompt-intent-expansion": 4,
    }
    ordered = sorted(
        candidates,
        key=lambda item: (preferred.get(item["input_family"], 100), item["rank"]),
    )
    for rank, item in enumerate(ordered, start=1):
        item["rank"] = rank
    return ordered


def materialize() -> dict:
    branch = read_json(BRANCH)
    require_seed_contract(SEED.read_text(encoding="utf-8"))

    canonical = branch.get("canonical_evidence")
    live_controls = branch.get("live_controls")
    release = canonical.get("release") if isinstance(canonical, dict) else None
    post_flash_ready = _post_flash_ready(live_controls if isinstance(live_controls, dict) else None)

    inputs = branch.get("likely_user_inputs")
    if not isinstance(inputs, list):
        raise ValueError("likely_user_inputs must be an array")
    normalized_inputs = _normalize_post_flash_inputs(inputs, post_flash_ready)

    candidates = []
    for entry in normalized_inputs:
        if not isinstance(entry, dict):
            continue
        rank = entry.get("rank")
        family = entry.get("input_family")
        prepared = entry.get("prepared_response")
        action = entry.get("action_if_safe")
        if not isinstance(rank, int) or not isinstance(family, str) or not isinstance(prepared, str):
            continue
        candidates.append({
            "rank": rank,
            "input_family": family,
            "prepared_response": prepared,
            "action_if_safe": action if isinstance(action, str) else None,
            "authority": "prediction-only-requires-live-consumption-recheck",
        })
    candidates = _post_flash_frontier(candidates, live_controls if isinstance(live_controls, dict) else None)
    candidates = candidates[:5]
    if not candidates:
        raise ValueError("no renderable interaction candidates")

    base_program = branch.get("current_program")
    if not isinstance(base_program, str):
        base_program = ""
    marker = " Future Branch handoff:"
    if marker in base_program:
        base_program = base_program.split(marker, 1)[0].rstrip()
    if post_flash_ready:
        # Do not prepend current truth to a stale pre-flash narrative. Once the exact
        # current media is readback-proven, the operational program is physical boot.
        base_program = _post_flash_program()

    visible_program = f"{base_program} {HANDOFF_SENTENCE}".strip()

    handoff_state = {
        "schema": "aurum-next-interaction-handoff-v1",
        "packet_path": "Projects/Aurum/next-interaction-packet.json",
        "activation": "next-real-interaction-not-clock",
        "materialization_evidence": "packet-file-rendered-from-current-future-branch-state",
        "consumption_evidence": "not-verified",
        "consumption_gate": "re-read-canonical-evidence-and-action-ownership-before-human-or-destructive-step",
        "authority_snapshot_authoritative": False,
        "scheduled_simulation_allowed": False,
        "authority_granted": False,
        "human_action_inferred": False,
    }

    branch_changed = (
        branch.get("current_program") != visible_program
        or branch.get("interaction_handoff") != handoff_state
        or branch.get("likely_user_inputs") != normalized_inputs
    )
    if branch_changed:
        branch["current_program"] = visible_program
        branch["likely_user_inputs"] = normalized_inputs
        branch["interaction_handoff"] = handoff_state
        BRANCH.write_text(json.dumps(branch, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    live_snapshot = dict(live_controls) if isinstance(live_controls, dict) else None
    if post_flash_ready and live_snapshot is not None:
        live_snapshot["physical_preflight_next_gate"] = live_snapshot.get("next_gate")
        live_snapshot["next_gate"] = "physical-hopper-boot-proof"
        live_snapshot["frontier_mode"] = "post-flash-physical-boot"

    packet = {
        "schema": "aurum-next-interaction-packet-v1",
        "activation": "next-real-interaction-not-clock",
        "refresh_rule": "refresh-when-future-branch-or-canonical-evidence-changes",
        "consumption_gate": "re-read-canonical-evidence-and-action-ownership-before-human-or-destructive-step",
        "source": "Projects/Aurum/future-branches.json",
        "source_schema": branch.get("schema"),
        "source_evidence_sha256": stable_digest(canonical),
        "release_source_commit": release.get("source_commit") if isinstance(release, dict) else None,
        "current_program": visible_program,
        "frontier": candidates,
        "live_controls_snapshot": live_snapshot,
        "authority_snapshot_authoritative": False,
        "time_sensitive_authority_requires_live_recheck": True,
        "materialization_evidence": "packet-file-rendered-from-current-future-branch-state",
        "consumption_evidence": "not-verified",
        "scheduled_simulation_allowed": False,
        "authority_granted": False,
        "physical_proof_inferred": False,
        "lkg_mutation_allowed": False,
        "human_action_inferred": False,
    }

    rendered = json.dumps(packet, indent=2, sort_keys=False) + "\n"
    before = PACKET.read_text(encoding="utf-8") if PACKET.exists() else None
    packet_changed = before != rendered
    if packet_changed:
        PACKET.write_text(rendered, encoding="utf-8")
    return {"changed": branch_changed or packet_changed, "packet": packet}


if __name__ == "__main__":
    result = materialize()
    print(json.dumps({
        "changed": result["changed"],
        "schema": result["packet"]["schema"],
        "activation": result["packet"]["activation"],
        "frontier_count": len(result["packet"]["frontier"]),
        "authority_granted": result["packet"]["authority_granted"],
        "authority_snapshot_authoritative": result["packet"]["authority_snapshot_authoritative"],
        "consumption_evidence": result["packet"]["consumption_evidence"],
    }, sort_keys=True))
