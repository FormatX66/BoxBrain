import unittest

from execution_route import (
    ExecutionRoute,
    RouteDisposition,
    RouteKind,
    preferred_route,
    rank_execution_routes,
    route_disposition,
)


class ExecutionRouteTests(unittest.TestCase):
    def route(self, name, kind, **overrides):
        values = dict(
            available=True,
            authority_ready=True,
            expected_success=0.85,
            evidence_quality=0.90,
            autonomy=0.90,
            reversibility=0.90,
            risk=0.10,
            setup_cost=0.20,
            latency_cost=0.20,
            human_steps=0,
            stale=False,
        )
        values.update(overrides)
        return ExecutionRoute(name=name, kind=kind, **values)

    def test_machine_route_beats_copy_paste_when_similarly_viable(self):
        machine = self.route("bounded local bridge", RouteKind.CONNECTED_CAPABILITY)
        human = self.route(
            "ask person to paste prompt",
            RouteKind.HUMAN_ASSISTED,
            autonomy=0.10,
            human_steps=2,
            setup_cost=0.10,
            latency_cost=0.10,
        )
        self.assertEqual(preferred_route([human, machine]), machine)

    def test_human_route_can_win_when_machine_path_is_materially_worse(self):
        machine = self.route(
            "fragile remote runner",
            RouteKind.AUTHORIZED_RUNNER,
            expected_success=0.25,
            evidence_quality=0.30,
            risk=0.55,
            setup_cost=1.5,
            latency_cost=1.5,
        )
        human = self.route(
            "local operator interaction",
            RouteKind.HUMAN_ASSISTED,
            expected_success=0.99,
            evidence_quality=0.95,
            autonomy=0.05,
            reversibility=0.95,
            risk=0.02,
            setup_cost=0.0,
            latency_cost=0.0,
            human_steps=1,
        )
        self.assertEqual(preferred_route([machine, human]), human)

    def test_stale_prepared_route_is_excluded(self):
        stale = self.route("cached runner path", RouteKind.AUTHORIZED_RUNNER, stale=True)
        fresh = self.route("fresh capability", RouteKind.CONNECTED_CAPABILITY, expected_success=0.70)
        self.assertEqual(preferred_route([stale, fresh]), fresh)

    def test_unavailable_routes_stay_out_of_preferred_path(self):
        unavailable = self.route("direct local", RouteKind.DIRECT_LOCAL, available=False)
        human = self.route(
            "operator fallback",
            RouteKind.HUMAN_ASSISTED,
            autonomy=0.10,
            human_steps=1,
        )
        self.assertEqual(preferred_route([unavailable, human]), human)

    def test_authority_not_ready_means_prepare_not_execute(self):
        route = self.route("runner", RouteKind.AUTHORIZED_RUNNER, authority_ready=False)
        self.assertEqual(route_disposition(route), RouteDisposition.PREPARE)

    def test_human_route_is_explicit_boundary(self):
        route = self.route("operator", RouteKind.HUMAN_ASSISTED, human_steps=1)
        self.assertEqual(route_disposition(route), RouteDisposition.ASK_HUMAN)

    def test_rank_keeps_alternates_warm(self):
        ranked = rank_execution_routes([
            self.route("connector", RouteKind.CONNECTED_CAPABILITY),
            self.route("runner", RouteKind.AUTHORIZED_RUNNER, expected_success=0.80),
            self.route(
                "human",
                RouteKind.HUMAN_ASSISTED,
                autonomy=0.10,
                human_steps=1,
            ),
        ])
        self.assertEqual(len(ranked), 3)
        self.assertEqual(ranked[0]["name"], "connector")
        self.assertIn("runner", [item["name"] for item in ranked[1:]])

    def test_no_available_route_returns_none(self):
        self.assertIsNone(preferred_route([
            self.route("missing", RouteKind.DIRECT_LOCAL, available=False),
            self.route("stale", RouteKind.AUTHORIZED_RUNNER, stale=True),
        ]))


if __name__ == "__main__":
    unittest.main()
