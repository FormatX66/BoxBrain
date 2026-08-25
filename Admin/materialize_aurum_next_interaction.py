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


def materialize() -> dict:
    branch = read_json(BRANCH)
    require_seed_contract(SEED.read_text(encoding="utf-8"))

    inputs = branch.get("likely_user_inputs")
    if not isinstance(inputs, list):
        raise ValueError("likely_user_inputs must be an array")

    candidates = []
    for entry in inputs:
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
    candidates.sort(key=lambda item: item["rank"])
    candidates = candidates[:5]
    if not candidates:
        raise ValueError("no renderable interaction candidates")

    canonical = branch.get("canonical_evidence")
    live_controls = branch.get("live_controls")
    release = canonical.get("release") if isinstance(canonical, dict) else None

    base_program = branch.get("current_program")
    if not isinstance(base_program, str):
        base_program = ""
    marker = " Future Branch handoff:"
    if marker in base_program:
        base_program = base_program.split(marker, 1)[0].rstrip()
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
    )
    if branch_changed:
        branch["current_program"] = visible_program
        branch["interaction_handoff"] = handoff_state
        BRANCH.write_text(json.dumps(branch, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    live_snapshot = live_controls if isinstance(live_controls, dict) else None
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
