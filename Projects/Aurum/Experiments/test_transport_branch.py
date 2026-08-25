from __future__ import annotations

import unittest

from transport_branch import TransportCandidate, TransportKind, transport_plan


class TransportBranchTests(unittest.TestCase):
    def candidate(self, name: str, kind: TransportKind, **changes) -> TransportCandidate:
        values = {
            "available": True,
            "reachable": True,
            "identity_verified": True,
            "capability_fit": 0.9,
            "reliability": 0.9,
            "freshness": 0.9,
            "human_time_saved": 1.0,
            "latency_cost": 0.1,
        }
        values.update(changes)
        return TransportCandidate(name=name, kind=kind, **values)

    def test_verified_reachable_route_is_prepared(self):
        plan = transport_plan(
            [
                self.candidate("usb-direct", TransportKind.USB),
                self.candidate("wifi-stale", TransportKind.WIFI, freshness=0.2, reliability=0.6),
            ]
        )
        self.assertEqual(plan["prepared_transport"], "usb-direct")
        self.assertEqual(plan["transports"][0]["reason"], "verified-reachable-route")

    def test_alternate_route_never_broadens_trust(self):
        plan = transport_plan(
            [
                self.candidate(
                    "peer-relay",
                    TransportKind.PEER_RELAY,
                    trust_broadening_required=True,
                ),
                self.candidate("ethernet", TransportKind.ETHERNET),
            ]
        )
        peer = next(item for item in plan["transports"] if item["name"] == "peer-relay")
        self.assertEqual(peer["disposition"], "quarantine")
        self.assertFalse(plan["identity_trust_broadening_allowed"])
        self.assertFalse(plan["connection_authority"])

    def test_target_identity_change_is_not_treated_as_connectivity_fix(self):
        plan = transport_plan(
            [
                self.candidate(
                    "wrong-device-but-reachable",
                    TransportKind.USB,
                    target_identity_changed=True,
                )
            ]
        )
        self.assertEqual(plan["transports"][0]["reason"], "target-identity-changed")
        self.assertEqual(plan["transports"][0]["disposition"], "quarantine")
        self.assertFalse(plan["target_identity_reinterpretation_allowed"])

    def test_offline_queue_stays_warm_when_live_routes_are_down(self):
        plan = transport_plan(
            [
                self.candidate("usb-down", TransportKind.USB, reachable=False),
                self.candidate(
                    "offline-queue",
                    TransportKind.OFFLINE_QUEUE,
                    reachable=False,
                    identity_verified=False,
                    latency_cost=0.02,
                    network_cost=0.0,
                ),
            ]
        )
        offline = next(item for item in plan["transports"] if item["name"] == "offline-queue")
        self.assertEqual(offline["disposition"], "warm")
        self.assertIn("offline-queue", plan["warm_fallbacks"])
        self.assertFalse(plan["external_action_allowed"])

    def test_stable_failed_route_is_quarantined_instead_of_retried_forever(self):
        plan = transport_plan(
            [self.candidate("wifi-loop", TransportKind.WIFI, stable_failed_attempts=4)]
        )
        self.assertEqual(plan["transports"][0]["disposition"], "quarantine")
        self.assertEqual(plan["transports"][0]["reason"], "stable-failed-route")


if __name__ == "__main__":
    unittest.main()
