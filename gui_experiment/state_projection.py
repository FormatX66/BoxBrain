from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ViewIntent:
    profile: str
    constraints: tuple[str, ...]


PROFILE_CONSTRAINTS = {
    "windows": ("taskbar", "start-surface", "windowed-apps", "desktop-icons"),
    "linux-security": ("workspace-grid", "terminal-first", "tool-launcher", "status-panel"),
    "minimal": ("command-surface", "status-panel"),
}


def compile_view_request(text: str) -> ViewIntent:
    """Translate a human appearance request into UI constraints, not OS commands."""

    normalized = " ".join(text.lower().split())
    if "windows" in normalized:
        profile = "windows"
    elif "security" in normalized or "kali" in normalized or "penetration" in normalized:
        profile = "linux-security"
    else:
        profile = "minimal"
    return ViewIntent(profile=profile, constraints=PROFILE_CONSTRAINTS[profile])


def project_machine_state(machine_state: Mapping[str, Any], intent: ViewIntent) -> dict[str, Any]:
    """Create a disposable human view without mutating machine state.

    The projection only exposes a bounded status/capability surface. Kernel and
    hardware control data remain outside the GUI representation.
    """

    capabilities = tuple(sorted(str(x) for x in machine_state.get("capabilities", ())))
    status = deepcopy(machine_state.get("status", {}))
    return {
        "profile": intent.profile,
        "constraints": intent.constraints,
        "status": status,
        "capabilities": capabilities,
        "view_epoch": int(machine_state.get("view_epoch", 0)),
    }


def request_state_change(view_model: Mapping[str, Any], capability: str, desired: Any) -> dict[str, Any]:
    """Emit desired-state intent for the controller; never execute from the GUI."""

    allowed = set(view_model.get("capabilities", ()))
    if capability not in allowed:
        raise ValueError(f"capability not exposed to view: {capability}")
    return {
        "kind": "desired-state",
        "capability": capability,
        "desired": deepcopy(desired),
        "origin": "gui-projection",
        "view_epoch": int(view_model.get("view_epoch", 0)),
    }
