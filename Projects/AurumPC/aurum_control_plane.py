#!/usr/bin/env python3
"""Policy-mediated full-OS control plane for Aurum models.

Models are allowed to express intent across every OS domain. Aurum, not the
model, owns authorization, execution, verification, healing, cull-and-regrow
decisions, and durable
receipts. This keeps the long-term interface conversational without making raw
shell access the operating-system contract.
"""
from __future__ import annotations

import json
import time
from typing import Any

SCHEMA = "aurum.control-plane.v1"
REQUEST_SCHEMA = "aurum.control-request.v1"

DOMAINS: tuple[dict[str, Any], ...] = (
    {"id": "appearance", "name": "Appearance", "examples": ["layout", "theme", "density", "presentation"]},
    {"id": "interaction", "name": "Interaction", "examples": ["input behavior", "accessibility", "shortcuts", "voice"]},
    {"id": "traits", "name": "Traits", "examples": ["create", "adapt", "compose", "retire"]},
    {"id": "build", "name": "Build", "examples": ["edit", "test", "compile", "validate", "promote"]},
    {"id": "runtime", "name": "Runtime", "examples": ["services", "processes", "resource policy", "startup"]},
    {"id": "kernel", "name": "Kernel", "examples": ["configuration", "capabilities", "driver model", "generation"]},
    {"id": "devices", "name": "Devices", "examples": ["discover", "model", "configure", "bind"]},
    {"id": "transport", "name": "Transport", "examples": ["network", "USB", "Bluetooth", "local links"]},
    {"id": "storage", "name": "Storage", "examples": ["files", "state", "media", "backup", "projection"]},
    {"id": "identity", "name": "Identity", "examples": ["user", "machine", "session", "presence"]},
    {"id": "permissions", "name": "Permissions", "examples": ["access", "confidence", "delegation", "approval"]},
    {"id": "recovery", "name": "Recovery", "examples": ["diagnose", "heal", "cull", "regrow forward"]},
    {"id": "power", "name": "Power", "examples": ["sleep", "wake", "shutdown", "thermal-aware policy"]},
)


def catalog() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "scope": "all-os-domains",
        "model_intent_scope": "full",
        "execution_authority": "aurum-policy-broker",
        "verification_required": True,
        "generation_history": "forward-only",
        "generation_rollback_permitted": False,
        "failure_disposition": "heal-or-cull-and-regrow-forward",
        "domains": [dict(item) for item in DOMAINS],
    }


def request(domain: str, action: str, *, parameters: dict[str, Any] | None = None, source: str = "model") -> dict[str, Any]:
    domain_key = str(domain or "").strip().lower()
    valid = {item["id"] for item in DOMAINS}
    if domain_key not in valid:
        raise ValueError(f"unsupported Aurum control domain: {domain_key or '<empty>'}")
    clean_action = " ".join(str(action or "").split())
    if not clean_action:
        raise ValueError("control action is empty")
    return {
        "schema": REQUEST_SCHEMA,
        "status": "planned",
        "source": str(source or "model"),
        "domain": domain_key,
        "action": clean_action,
        "parameters": dict(parameters or {}),
        "execution_authority": "aurum-policy-broker",
        "requires_authorization": True,
        "requires_verification": True,
        "direct_shell_contract": False,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main() -> int:
    print(json.dumps(catalog(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
