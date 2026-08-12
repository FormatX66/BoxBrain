import asyncio
import unittest
from unittest.mock import patch

from Projects.Codelation import cluster_probe


class ClusterProbeTests(unittest.TestCase):
    def test_literal_scope_rejects_public_addresses(self):
        self.assertEqual(cluster_probe.resolve_allowed_host("10.12.194.1"), ("10.12.194.1",))
        self.assertEqual(cluster_probe.resolve_allowed_host("169.254.10.20"), ("169.254.10.20",))
        self.assertEqual(cluster_probe.resolve_allowed_host("8.8.8.8"), ())

    def test_hostname_is_resolved_once_and_only_private_answers_are_pinned(self):
        answers = [
            (2, 1, 6, "", ("10.42.194.1", 0)),
            (2, 1, 6, "", ("8.8.8.8", 0)),
            (2, 1, 6, "", ("10.12.194.1", 0)),
        ]
        with patch.object(cluster_probe.socket, "getaddrinfo", return_value=answers) as resolver:
            targets = cluster_probe.resolve_targets(["bbpi4.local"])
        resolver.assert_called_once()
        self.assertEqual(
            targets,
            [("bbpi4.local", "10.12.194.1"), ("bbpi4.local", "10.42.194.1")],
        )

    def test_unresolved_or_public_only_hostname_is_refused(self):
        answers = [(2, 1, 6, "", ("8.8.8.8", 0))]
        with patch.object(cluster_probe.socket, "getaddrinfo", return_value=answers):
            with self.assertRaisesRegex(ValueError, "refusing non-private"):
                cluster_probe.resolve_targets(["example.invalid"])

    def test_port_parser_is_bounded(self):
        self.assertEqual(cluster_probe.parse_ports("5986,22,5985,22"), (22, 5985, 5986))
        for value in ("", "0", "65536", "abc"):
            with self.assertRaisesRegex(ValueError, "invalid ports"):
                cluster_probe.parse_ports(value)

    def test_defaults_cover_known_aurum_carriers(self):
        for port in (22, 80, 443, 3000, 3389, 5985, 5986, 8000, 8080):
            self.assertIn(port, cluster_probe.DEFAULT_PORTS)
        self.assertLessEqual(cluster_probe.MAX_CONCURRENCY, 256)

    def test_local_connectivity_observation_is_machine_readable(self):
        async def exercise():
            server = await asyncio.start_server(lambda _reader, writer: writer.close(), "127.0.0.1", 0)
            try:
                port = server.sockets[0].getsockname()[1]
                result = await cluster_probe.run(
                    [("self-test", "127.0.0.1")], (port,), timeout=0.5, concurrency=4
                )
            finally:
                server.close()
                await server.wait_closed()
            return port, result

        port, result = asyncio.run(exercise())
        self.assertEqual(result["schema"], "aurum.observation.connectivity.v0")
        self.assertEqual(result["resolved"], {"self-test": ["127.0.0.1"]})
        self.assertEqual(result["services_by_host"], {"self-test": [port]})
        self.assertTrue(result["verification"]["connect_only"])
        self.assertTrue(result["verification"]["resolve_once_then_pin"])
        self.assertTrue(result["verification"]["reversible"])


if __name__ == "__main__":
    unittest.main()
