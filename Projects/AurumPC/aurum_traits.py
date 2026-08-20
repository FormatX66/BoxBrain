#!/usr/bin/env python3
"""Durable Gen1 capability-trait registry for Aurum.

Traits describe user-meaningful capabilities, not a permanent app model.  A
trait may initially be backed by compatibility software, but its semantic
identity remains stable while the implementation evolves underneath it.
"""
from __future__ import annotations

from typing import Any

SCHEMA = "aurum.traits.v1"

TRAITS: tuple[dict[str, Any], ...] = (
    {
        "id": "TR8:WEB",
        "name": "Web",
        "stage": "planned",
        "summary": "Browse and use web experiences without exposing browser plumbing as the capability itself.",
    },
    {
        "id": "TR8:FILES",
        "name": "Files",
        "stage": "planned",
        "summary": "Human-friendly access to local, removable, and connected storage projections.",
    },
    {
        "id": "TR8:MEDIA",
        "name": "Media",
        "stage": "planned",
        "summary": "Play and inspect image, audio, and video content through a durable media capability.",
    },
    {
        "id": "TR8:WRITE",
        "name": "Write",
        "stage": "planned",
        "summary": "Create and edit text while preserving user intent, voice, and reversible assistance.",
    },
    {
        "id": "TR8:INTENT",
        "name": "Intent",
        "stage": "foundation-ready",
        "summary": "Translate natural user intent into bounded capability requests and adaptive input help.",
    },
    {
        "id": "TR8:CONNECT",
        "name": "Connect",
        "stage": "foundation-ready",
        "summary": "Manage network and device connectivity as one capability rather than separate admin tools.",
    },
    {
        "id": "TR8:RECOVER",
        "name": "Recover",
        "stage": "foundation-ready",
        "summary": "Diagnose, restore, and return to a known-good generation without specialist administration.",
    },
)


def catalog() -> list[dict[str, Any]]:
    """Return a copy-safe ordered trait catalog for presentation and planning."""
    return [dict(item) for item in TRAITS]


def trait(trait_id: str) -> dict[str, Any] | None:
    key = str(trait_id or "").strip().upper()
    for item in TRAITS:
        if item["id"] == key:
            return dict(item)
    return None


def summary() -> dict[str, Any]:
    traits = catalog()
    foundation = [item for item in traits if item["stage"] == "foundation-ready"]
    planned = [item for item in traits if item["stage"] == "planned"]
    return {
        "schema": SCHEMA,
        "total": len(traits),
        "foundation_ready": len(foundation),
        "planned": len(planned),
        "traits": traits,
        "host_actuation": False,
    }
