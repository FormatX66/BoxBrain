from __future__ import annotations

import unittest

from diagnostic_branch import (
    DiagnosticDomain,
    DiagnosticHypothesis,
    DiagnosticProbe,
    diagnostic_plan,
    rank_hypotheses,
    rank_probes,
)


class DiagnosticBranchTests(unittest.TestCase):
    def hypothesis(self, name: str, domain: DiagnosticDomain, **changes) -> DiagnosticHypothesis:
        values = {
            "name": name,
            "domain": domain,
            "prior_probability": 0.4,
            "impact": 0.8,
            "evidence_support": 0.0,
            "evidence_conflict": 0.0,
            "freshness": 1.0,
            "stable_failed_attempts": 0,
        }
        values.update(changes)
        return DiagnosticHypothesis(**values)

    def test_fresh_support_promotes_competing_cause(self):
        supported = self.hypothesis(
            "usb-link-config",
            DiagnosticDomain.TRANSPORT,
            prior_probability=0.35,
            evidence_support=0.8,
        )
        weak = self.hypothesis("dns", DiagnosticDomain.DNS, prior_probability=0.35)
        ranked = rank_hypotheses([weak, supported])
        self.assertEqual(ranked[0]["name"], "usb-link-config")

    def test_strongly_disproven_hypothesis_is_quarantined(self):
        item = self.hypothesis(
            "bad-trackpad-hardware",
            DiagnosticDomain.HARDWARE,
            prior_probability=0.25,
            evidence_support=0.05,
            evidence_conflict=0.95,
        )
        ranked = rank_hypotheses([item])
        self.assertEqual(ranked[0]["disposition"], "quarantine")

    def test_unchanged_failed_retry_never_becomes_next_probe(self):
        hypotheses = [self.hypothesis("service-down", DiagnosticDomain.SERVICE)]
        probes = [
            DiagnosticProbe(
                "repeat-same-command",
                (DiagnosticDomain.SERVICE,),
                read_only=True,
                evidence_gain=1.0,
                human_time_saved=2.0,
                compute_cost=0.01,
                unchanged_retry=True,
            ),
            DiagnosticProbe(
                "read-service-state",
                (DiagnosticDomain.SERVICE,),
                read_only=True,
                evidence_gain=0.7,
                human_time_saved=1.0,
                compute_cost=0.05,
            ),
        ]
        ranked = rank_probes(probes, hypotheses)
        self.assertEqual(ranked[0]["name"], "read-service-state")
        retry = next(item for item in ranked if item["name"] == "repeat-same-command")
        self.assertEqual(retry["disposition"], "quarantine")

    def test_identity_broadening_is_not_a_transport_fallback(self):
        hypotheses = [self.hypothesis("usb-transport", DiagnosticDomain.TRANSPORT)]
        probes = [
            DiagnosticProbe(
                "trust-any-neighbor",
                (DiagnosticDomain.TRANSPORT,),
                read_only=True,
                evidence_gain=1.0,
                human_time_saved=3.0,
                compute_cost=0.01,
                identity_broadening=True,
            )
        ]
        ranked = rank_probes(probes, hypotheses)
        self.assertEqual(ranked[0]["disposition"], "quarantine")
        self.assertEqual(ranked[0]["reason"], "identity-trust-broadening")

    def test_side_effecting_repair_is_held_behind_authority(self):
        hypotheses = [self.hypothesis("routing", DiagnosticDomain.ROUTING)]
        probes = [
            DiagnosticProbe(
                "rewrite-route",
                (DiagnosticDomain.ROUTING,),
                read_only=False,
                evidence_gain=0.8,
                human_time_saved=2.0,
                compute_cost=0.05,
                risk=0.2,
                authority_required=True,
            )
        ]
        ranked = rank_probes(probes, hypotheses)
        self.assertEqual(ranked[0]["disposition"], "hold")
        self.assertEqual(ranked[0]["reason"], "authority-or-side-effect-boundary")

    def test_read_only_cross_domain_probe_can_win(self):
        hypotheses = [
            self.hypothesis("dns", DiagnosticDomain.DNS, prior_probability=0.35),
            self.hypothesis("routing", DiagnosticDomain.ROUTING, prior_probability=0.35),
            self.hypothesis("tls", DiagnosticDomain.TLS, prior_probability=0.20),
        ]
        probes = [
            DiagnosticProbe(
                "network-facts",
                (DiagnosticDomain.DNS, DiagnosticDomain.ROUTING, DiagnosticDomain.TLS),
                read_only=True,
                evidence_gain=0.75,
                human_time_saved=2.0,
                compute_cost=0.08,
                network_cost=0.02,
            ),
            DiagnosticProbe(
                "dns-only",
                (DiagnosticDomain.DNS,),
                read_only=True,
                evidence_gain=0.8,
                human_time_saved=1.0,
                compute_cost=0.08,
            ),
        ]
        ranked = rank_probes(probes, hypotheses)
        self.assertEqual(ranked[0]["name"], "network-facts")

    def test_plan_never_grants_external_or_destructive_authority(self):
        plan = diagnostic_plan(
            [self.hypothesis("ci-config", DiagnosticDomain.CONFIGURATION)],
            [
                DiagnosticProbe(
                    "read-ci-config",
                    (DiagnosticDomain.CONFIGURATION,),
                    read_only=True,
                    evidence_gain=0.8,
                    human_time_saved=1.0,
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
