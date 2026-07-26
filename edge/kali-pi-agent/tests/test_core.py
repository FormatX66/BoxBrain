from __future__ import annotations

import json
import ipaddress
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.request import urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boxbrain.server import build_server  # noqa: E402
from boxbrain.agent import agent_state, recommendations  # noqa: E402
from boxbrain.diagnostics import (  # noqa: E402
    DIAGNOSTIC_AUTHORIZATION,
    TargetDiagnostics,
    analyze,
)
from boxbrain.links import load_links  # noqa: E402
from boxbrain.onboarding import build_server as build_onboarding_server  # noqa: E402
from boxbrain.policy import (  # noqa: E402
    AUTHORIZATION_ASSERTION,
    PolicyError,
    validate_target,
)
from boxbrain.storage import Storage  # noqa: E402
from boxbrain.system import collect_status  # noqa: E402


class BoxBrainTests(unittest.TestCase):
    def test_status_has_required_sections(self) -> None:
        status = collect_status(0)
        self.assertEqual(status["status"], "ok")
        self.assertIn("memory", status)
        self.assertIn("storage", status)
        self.assertIn("network", status)

    def test_health_endpoint(self) -> None:
        server = build_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with urlopen(f"http://{host}:{port}/health", timeout=3) as response:
                payload = json.load(response)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["service"], "boxbrain")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_onboarding_health_and_scripts(self) -> None:
        server = build_onboarding_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with urlopen(f"http://{host}:{port}/health", timeout=3) as response:
                payload = json.load(response)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["service"], "boxbrain-onboarding")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_usb_onboarding_bind_is_explicitly_migrated(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = (root / "config" / "boxbrain.env").read_text(encoding="utf-8")
        installer = (root / "scripts" / "install.sh").read_text(encoding="utf-8")
        onboarding = (root / "src" / "boxbrain" / "onboarding.py").read_text(
            encoding="utf-8"
        )

        expected = "BOXBRAIN_ONBOARDING_BIND=10.12.194.1"
        self.assertIn(expected, config)
        self.assertIn("ensure_env_setting BOXBRAIN_ONBOARDING_BIND 10.12.194.1", installer)
        self.assertIn('"BOXBRAIN_ONBOARDING_BIND", "10.12.194.1"', onboarding)

    def test_links_ignore_bad_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            links = Path(directory) / "links"
            links.mkdir()
            (links / "good.json").write_text(
                '{"address":"10.12.194.2","status":"connected"}',
                encoding="utf-8",
            )
            (links / "bad.json").write_text("{", encoding="utf-8")
            loaded = load_links(directory)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["address"], "10.12.194.2")

    def test_diagnostic_findings_prioritize_low_disk_space(self) -> None:
        payload = {
            "disks": [
                {
                    "name": "C:",
                    "size_bytes": 100_000,
                    "free_bytes": 4_000,
                }
            ],
            "memory_total_bytes": 100_000,
            "memory_free_bytes": 50_000,
            "device_error_count": 0,
            "pending_reboot": False,
            "network_adapters": [{"name": "USB Ethernet"}],
        }
        overall, findings, metrics = analyze(payload)
        self.assertEqual(overall, "attention")
        self.assertEqual(findings[0]["severity"], "high")
        self.assertEqual(metrics["lowest_disk_free_percent"], 4.0)

    def test_authorized_target_diagnostic_writes_report(self) -> None:
        class FakeDiagnostics(TargetDiagnostics):
            def _windows(self, address: str) -> dict[str, object]:
                return {
                    "family": "windows",
                    "hostname": "REPAIR-PC",
                    "os_name": "Windows",
                    "os_version": "test",
                    "disks": [
                        {
                            "name": "C:",
                            "size_bytes": 100_000,
                            "free_bytes": 40_000,
                        }
                    ],
                    "memory_total_bytes": 100_000,
                    "memory_free_bytes": 40_000,
                    "device_error_count": 0,
                    "pending_reboot": False,
                    "network_adapters": [{"name": "USB Ethernet"}],
                }

        with tempfile.TemporaryDirectory() as directory:
            links = Path(directory) / "links"
            links.mkdir()
            link_path = links / "10-12-194-2.json"
            link_path.write_text(
                json.dumps(
                    {
                        "address": "10.12.194.2",
                        "hostname": "REPAIR-PC",
                        "platform": "Microsoft Windows",
                        "status": "connected",
                        "transport": "usb-ethernet-ssh",
                    }
                ),
                encoding="utf-8",
            )
            diagnostics = FakeDiagnostics(directory)
            report = diagnostics.diagnose(
                "10.12.194.2",
                DIAGNOSTIC_AUTHORIZATION,
            )
            self.assertEqual(report["mode"], "read-only")
            self.assertEqual(report["summary"]["overall"], "healthy")
            latest = diagnostics.latest_report("10.12.194.2")
            self.assertEqual(latest["target"]["hostname"], "REPAIR-PC")
            updated_link = json.loads(link_path.read_text(encoding="utf-8"))
            self.assertEqual(updated_link["diagnostics"]["status"], "completed")

    def test_edge_agent_prioritizes_optimization_without_auto_execution(self) -> None:
        links = [
            {
                "address": "10.12.194.4",
                "hostname": "WORKSTATION",
                "diagnostics": {
                    "status": "completed",
                    "findings": [
                        {
                            "severity": "high",
                            "title": "D: is critically low on space",
                            "detail": "Only 2.4% of the disk is free.",
                            "recommendation": "Review and safely reclaim storage.",
                        }
                    ],
                },
            }
        ]
        items = recommendations(links)
        self.assertEqual(items[0]["domain"], "optimization")
        self.assertEqual(items[0]["priority"], "urgent")
        self.assertTrue(items[0]["requires_approval"])
        self.assertEqual(items[0]["execution"], "operator-approved")

    def test_edge_agent_policy_disables_destructive_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "links").mkdir()
            state = agent_state(directory)
            self.assertEqual(state["name"], "BoxBrain Kali Pi Edge Agent")
            self.assertEqual(state["role"], "edge-agent")
            self.assertEqual(state["operating_mode"], "advisory")
            self.assertEqual(state["policy"]["change"], "explicit-approval-required")
            self.assertEqual(state["policy"]["destructive_actions"], "disabled")
            capability_ids = {item["id"] for item in state["capabilities"]}
            self.assertIn("optimization-planning", capability_ids)
            self.assertIn("ai-reasoning", capability_ids)

    def test_policy_accepts_connected_private_scope(self) -> None:
        target = validate_target(
            "192.168.137.0/24",
            AUTHORIZATION_ASSERTION,
            [ipaddress.ip_network("192.168.137.0/24")],
        )
        self.assertEqual(str(target), "192.168.137.0/24")

    def test_policy_rejects_public_or_unconnected_scope(self) -> None:
        connected = [ipaddress.ip_network("192.168.137.0/24")]
        with self.assertRaises(PolicyError):
            validate_target("8.8.8.8", AUTHORIZATION_ASSERTION, connected)
        with self.assertRaises(PolicyError):
            validate_target("192.168.50.0/24", AUTHORIZATION_ASSERTION, connected)
        with self.assertRaises(PolicyError):
            validate_target("192.168.137.0/24", "", connected)

    def test_storage_job_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(directory)
            storage.initialize()
            job_id = storage.create_job(
                "192.168.137.0/24",
                "discovery",
                AUTHORIZATION_ASSERTION,
            )
            asset_id = storage.save_asset(
                job_id,
                "192.168.137.1",
                "gateway",
                None,
                None,
            )
            storage.save_service(
                job_id,
                asset_id,
                80,
                "tcp",
                "open",
                "http",
                None,
                None,
            )
            storage.update_job(job_id, status="completed")
            report = storage.build_report(job_id)
            self.assertEqual(report["job"]["status"], "completed")
            self.assertEqual(len(report["assets"]), 1)
            self.assertEqual(len(report["services"]), 1)


if __name__ == "__main__":
    unittest.main()
