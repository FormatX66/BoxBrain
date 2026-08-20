#!/usr/bin/env python3
"""Durable Gen1 capability and trait registry for Aurum.

Resident capabilities are substrate abilities every normal Aurum generation
must preserve. Traits are user-meaningful capabilities whose implementation
may evolve without changing their semantic identity.
"""
from __future__ import annotations

from typing import Any

SCHEMA = "aurum.traits.v1"

RESIDENT_CAPABILITIES: tuple[dict[str, str], ...] = (
    {"id": "CORE:BOOT", "name": "Boot + Generation", "summary": "Boot, generation identity, and known-good continuation."},
    {"id": "CORE:INPUT", "name": "Input", "summary": "Keyboard, pointer, touch, accessibility, and future input projections."},
    {"id": "CORE:DISPLAY", "name": "Display", "summary": "Physical and projected human-facing presentation surfaces."},
    {"id": "CORE:IDENTITY", "name": "Identity + Permissions", "summary": "Machine and user identity with bounded authorization."},
    {"id": "CORE:TRANSPORT", "name": "Transport", "summary": "Network and local transports without tying the capability to one interface."},
    {"id": "CORE:STORAGE", "name": "Storage + State", "summary": "Durable state, removable media, and storage substrate access."},
    {"id": "CORE:TIME", "name": "Time", "summary": "Clock synchronization and monotonic runtime timing."},
    {"id": "CORE:GROWTH", "name": "Update + Self-build", "summary": "Generation growth, guarded runtime update, and local self-build."},
    {"id": "CORE:SAFETY", "name": "Safety + Recovery", "summary": "Diagnostics, rollback, recovery console, and bounded physical changes."},
    {"id": "CORE:CONTROL", "name": "AI Control Plane", "summary": "Expose every OS domain to authorized model intent while Aurum owns policy, execution, verification, and recovery."},
)

TRAITS: tuple[dict[str, Any], ...] = (
    {
        "id": "TRAIT:GPT",
        "name": "GPT",
        "stage": "foundation-building",
        "resident": True,
        "priority": 0,
        "summary": "OpenAI reasoning and coding bridge that can graduate from conversation into policy-mediated Aurum build and OS control on Hopper.",
    },
    {
        "id": "TRAIT:INTENT",
        "name": "Intent",
        "stage": "foundation-ready",
        "resident": True,
        "priority": 1,
        "summary": "Translate natural user intent into bounded capability requests and adaptive input help.",
    },
    {
        "id": "TRAIT:CONNECT",
        "name": "Connect",
        "stage": "foundation-ready",
        "resident": True,
        "priority": 2,
        "summary": "Manage network and device connectivity as one capability rather than separate admin tools.",
    },
    {
        "id": "TRAIT:RECOVER",
        "name": "Recover",
        "stage": "foundation-ready",
        "resident": True,
        "priority": 3,
        "summary": "Diagnose, restore, and return to a known-good generation without specialist administration.",
    },
    {
        "id": "TRAIT:WEB",
        "name": "Web",
        "stage": "planned",
        "resident": True,
        "priority": 4,
        "summary": "Browse and use web experiences without exposing browser plumbing as the capability itself.",
    },
    {
        "id": "TRAIT:FILES",
        "name": "Files",
        "stage": "planned",
        "resident": True,
        "priority": 5,
        "summary": "Human-friendly access to local, removable, and connected storage projections.",
    },
    {
        "id": "TRAIT:WRITE",
        "name": "Write",
        "stage": "planned",
        "resident": True,
        "priority": 6,
        "summary": "Create and edit text while preserving user intent, voice, and reversible assistance.",
    },
    {
        "id": "TRAIT:MEDIA",
        "name": "Media",
        "stage": "planned",
        "resident": True,
        "priority": 7,
        "summary": "Play and inspect image, audio, and video content through a durable media capability.",
    },
)


def resident_capabilities() -> list[dict[str, str]]:
    return [dict(item) for item in RESIDENT_CAPABILITIES]


def catalog() -> list[dict[str, Any]]:
    """Return a copy-safe ordered trait catalog for presentation and planning."""
    return [dict(item) for item in sorted(TRAITS, key=lambda item: int(item.get("priority", 999)))]


def trait(trait_id: str) -> dict[str, Any] | None:
    key = str(trait_id or "").strip().upper()
    for item in TRAITS:
        if item["id"] == key:
            return dict(item)
    return None


def summary() -> dict[str, Any]:
    traits = catalog()
    foundation = [item for item in traits if item["stage"] == "foundation-ready"]
    building = [item for item in traits if item["stage"] == "foundation-building"]
    planned = [item for item in traits if item["stage"] == "planned"]
    resident = [item for item in traits if item.get("resident") is True]
    core = resident_capabilities()
    return {
        "schema": SCHEMA,
        "total": len(traits),
        "foundation_ready": len(foundation),
        "foundation_building": len(building),
        "planned": len(planned),
        "resident_traits": len(resident),
        "resident_capabilities": core,
        "resident_capability_count": len(core),
        "traits": traits,
        "host_actuation": False,
    }
