"""Stable dashboard/import surface for the Future Branch diagnostic planner.

The implementation lives in :mod:`diagnostic_branch`.  Keep this small shim so
human/status consumers can depend on a durable path while the internal planner
module is free to evolve.  Re-exporting does not add authority or side effects.
"""
from __future__ import annotations

try:
    from .diagnostic_branch import (
        DiagnosticDomain,
        DiagnosticHypothesis,
        DiagnosticProbe,
        ProbeDisposition,
        diagnostic_plan,
        hypothesis_score,
        probe_score,
        rank_hypotheses,
        rank_probes,
    )
except ImportError:  # direct execution from the Experiments directory
    from diagnostic_branch import (
        DiagnosticDomain,
        DiagnosticHypothesis,
        DiagnosticProbe,
        ProbeDisposition,
        diagnostic_plan,
        hypothesis_score,
        probe_score,
        rank_hypotheses,
        rank_probes,
    )

__all__ = [
    "DiagnosticDomain",
    "DiagnosticHypothesis",
    "DiagnosticProbe",
    "ProbeDisposition",
    "diagnostic_plan",
    "hypothesis_score",
    "probe_score",
    "rank_hypotheses",
    "rank_probes",
]
