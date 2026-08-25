from __future__ import annotations

import unittest
from pathlib import Path

import diagnostic_branch
import diagnostics


class DiagnosticSurfaceTests(unittest.TestCase):
    def test_compatibility_surface_reexports_canonical_planner(self):
        self.assertIs(diagnostics.DiagnosticHypothesis, diagnostic_branch.DiagnosticHypothesis)
        self.assertIs(diagnostics.DiagnosticProbe, diagnostic_branch.DiagnosticProbe)
        self.assertIs(diagnostics.diagnostic_plan, diagnostic_branch.diagnostic_plan)

    def test_dashboard_reference_resolves_to_real_surface(self):
        root = Path(__file__).resolve().parents[3]
        dashboard = (root / "Web" / "Aurum-Arkmatx" / "future-branch-v1.js").read_text(
            encoding="utf-8"
        )
        expected = "Projects/Aurum/Experiments/diagnostics.py"
        self.assertIn(expected, dashboard)
        self.assertTrue((root / expected).is_file())

    def test_surface_stays_zero_authority(self):
        plan = diagnostics.diagnostic_plan(
            [
                diagnostics.DiagnosticHypothesis(
                    "dns-stale",
                    diagnostics.DiagnosticDomain.DNS,
                    prior_probability=0.6,
                    impact=0.8,
                    evidence_support=0.5,
                )
            ],
            [
                diagnostics.DiagnosticProbe(
                    "read-resolver-state",
                    (diagnostics.DiagnosticDomain.DNS,),
                    read_only=True,
                    evidence_gain=0.9,
                    human_time_saved=0.5,
                    compute_cost=0.05,
                )
            ],
        )
        self.assertFalse(plan["external_action_allowed"])
        self.assertFalse(plan["identity_trust_broadening_allowed"])
        self.assertFalse(plan["destructive_authority"])
        self.assertFalse(plan["retry_unchanged_failure_allowed"])


if __name__ == "__main__":
    unittest.main()
