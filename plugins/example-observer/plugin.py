"""Inert example plugin.

The controller alpha does not import this module. It exists only to illustrate
the future request/response boundary.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MockObservation:
    source: str = "example.observer"
    summary: str = "No target connected."


def observe() -> MockObservation:
    return MockObservation()

