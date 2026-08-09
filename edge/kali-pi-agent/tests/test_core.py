from __future__ import annotations

import json
import ipaddress
import io
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boxbrain.server import build_server  # noqa: E402
from boxbrain.agent import agent_state, recommendations  # noqa: E402
from boxbrain.control import ControlServer  # noqa: E402
from boxbrain.diagnostics import (  # noqa: E402
    DIAGNOSTIC_AUTHORIZATION,
    TargetDiagnostics,
    analyze,
)
from boxbrain.enrollment import (  # noqa: E402
    LINK_AUTHORIZATION,
    TargetEnrollmentError,
    enroll_target,
)
from boxbrain import __version__, link_monitor  # noqa: E402
from boxbrain.links import load_links  # noqa: E402
from boxbrain.onboarding import build_server as build_onboarding_server  # noqa: E402
from boxbrain.policy import (  # noqa: E402
    AUTHORIZATION_ASSERTION,
    PolicyError,
    validate_target,
)
from boxbrain.storage import Storage  # noqa: E402
from boxbrain.system import collect_status  # noqa: E402
from boxbrain.wifi import (  # noqa: E402
    WIFI_PROVISION_AUTHORIZATION,
    WifiProvisionError,
    provision_current_wifi,
)


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
            self.assertEqual(payload["version"], __version__)
            self.assertEqual(
                payload["version"],
                (Path(__file__).resolve().parents[1] / "VERSION")
                .read_text(encoding="utf-8")
                .strip(),
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_status_endpoint_includes_bounded_connection_map(self) -> None:
        server = build_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with urlopen(
                f"http://{host}:{port}/api/v1/status",
                timeout=3,
            ) as response:
                payload = json.load(response)
            connection_map = payload["connection_map"]
            self.assertEqual(connection_map["schema_version"], 1)
            self.assertEqual(
                {item["id"] for item in connection_map["transports"]},
                {"usb", "ethernet", "wifi", "bluetooth", "near-field"},
            )
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
            with urlopen(f"http://{host}:{port}/", timeout=3) as response:
                page = response.read().decode("utf-8")
            self.assertIn("USB-C + private-network onboarding", page)
            self.assertIn("boxbrainctl add-target", page)
            self.assertIn("windows-wifi-provision.ps1", page)
            self.assertIn("SSH over USB-C", page)
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
        windows_link = (root / "onboarding" / "windows-link.ps1").read_text(
            encoding="utf-8"
        )
        linux_link = (root / "onboarding" / "linux-link.sh").read_text(
            encoding="utf-8"
        )
        wifi_helper = (
            root / "onboarding" / "windows-wifi-provision.ps1"
        ).read_text(encoding="utf-8")

        expected = "BOXBRAIN_ONBOARDING_BIND=10.12.194.1"
        self.assertIn(expected, config)
        self.assertIn("ensure_env_setting BOXBRAIN_ONBOARDING_BIND 10.12.194.1", installer)
        self.assertIn('"BOXBRAIN_ONBOARDING_BIND", "10.12.194.1"', onboarding)
        self.assertIn("BoxBrainAddress = @('10.12.194.1')", windows_link)
        self.assertIn(
            "$remoteAddresses = @(\n    @(\n        foreach",
            windows_link,
        )
        self.assertIn(
            "    ) | Sort-Object -Unique\n)\nif ($remoteAddresses.Count -eq 0)",
            windows_link,
        )
        self.assertNotIn("192.168.137.0/24", windows_link)
        self.assertIn("BOXBRAIN_AGENT_ADDRESS", linux_link)
        self.assertIn("PiAddress = '10.12.194.1'", wifi_helper)
        self.assertIn("RedirectStandardInput = $true", wifi_helper)
        self.assertIn("StrictHostKeyChecking=yes", wifi_helper)
        self.assertIn("sudo -n /usr/local/bin/boxbrainctl", wifi_helper)
        authorization_check = wifi_helper.index("if (-not $Authorized)")
        credential_read = wifi_helper.index('key=clear')
        self.assertLess(authorization_check, credential_read)
        self.assertIn("No credential was read", wifi_helper)
        self.assertIn("$profileOutput = $null", wifi_helper)
        self.assertIn("$keyMatch = $null", wifi_helper)
        self.assertIn("$passphrase = $null", wifi_helper)
        self.assertNotIn("Write-Output $passphrase", wifi_helper)
        self.assertNotIn("Write-Host $passphrase", wifi_helper)
        self.assertNotIn('$passphrase, $PiUser', wifi_helper)
        diagnostic_source = (
            root / "src" / "boxbrain" / "diagnostics.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Wait-Job -Job $deviceJob -Timeout 15", diagnostic_source)
        self.assertIn("device_error_check = $deviceErrorCheck", diagnostic_source)
        self.assertNotIn("key=clear", diagnostic_source)
        self.assertIn("build_windows_wlan_powershell", diagnostic_source)

    def test_wifi_provision_keeps_passphrase_out_of_argv_and_result(self) -> None:
        secret = "test-only-passphrase"
        payload = json.dumps(
            {
                "schema_version": 1,
                "source": "windows-current-profile",
                "transport": "usb-c-ssh",
                "ssid": "Authorized-Lab",
                "passphrase": secret,
            }
        )
        calls: list[tuple[list[str], dict[str, object]]] = []

        def runner(arguments: list[str], **kwargs: object) -> object:
            calls.append((arguments, kwargs))
            if "connect" in arguments:
                return unittest.mock.Mock(returncode=0, stdout="", stderr="")
            return unittest.mock.Mock(
                returncode=0,
                stdout="100 (connected)\nBoxBrain-USB-test\n",
                stderr="",
            )

        with patch("boxbrain.wifi.shutil.which", return_value="/usr/bin/nmcli"):
            result = provision_current_wifi(
                io.StringIO(payload),
                WIFI_PROVISION_AUTHORIZATION,
                runner=runner,
                effective_uid=0,
            )

        self.assertEqual(calls[0][1]["input"], f"{secret}\n")
        self.assertNotIn(secret, " ".join(calls[0][0]))
        self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(result["credential_transport"], "usb-c-ssh-stdin")
        self.assertFalse(result["credential_logged"])

    def test_wifi_provision_requires_root_and_usb_transport(self) -> None:
        payload = json.dumps(
            {
                "schema_version": 1,
                "source": "windows-current-profile",
                "transport": "usb-c-ssh",
                "ssid": "Authorized-Lab",
                "passphrase": "test-only-passphrase",
            }
        )
        with self.assertRaises(WifiProvisionError):
            provision_current_wifi(
                io.StringIO(payload),
                WIFI_PROVISION_AUTHORIZATION,
                effective_uid=1000,
            )

        wrong_transport = json.loads(payload)
        wrong_transport["transport"] = "network-ssh"
        with (
            patch("boxbrain.wifi.shutil.which", return_value="/usr/bin/nmcli"),
            self.assertRaises(WifiProvisionError),
        ):
            provision_current_wifi(
                io.StringIO(json.dumps(wrong_transport)),
                WIFI_PROVISION_AUTHORIZATION,
                effective_uid=0,
            )

    def test_windows_wlan_diagnostic_metadata_is_included_without_credentials(self) -> None:
        payload = {
            "disks": [],
            "network_adapters": [{"name": "USB Ethernet"}],
            "windows_wlan": {
                "credential_material_included": False,
                "diagnostics": {
                    "interface_count": 1,
                    "profile_count": 1,
                    "findings": [
                        {
                            "severity": "low",
                            "title": "Windows WLAN signal is weak",
                            "recommendation": "Use Ethernet for repair operations.",
                        }
                    ],
                },
            },
        }
        overall, findings, metrics = analyze(payload)
        self.assertEqual(overall, "review")
        self.assertEqual(findings[0]["severity"], "low")
        self.assertIn("WLAN signal", findings[0]["title"])
        self.assertEqual(metrics["windows_wlan_interface_count"], 1)
        self.assertEqual(metrics["windows_wlan_profile_count"], 1)

    def test_upgrade_backups_are_private_and_rollback_guarded(self) -> None:
        root = Path(__file__).resolve().parents[1]
        upgrade = (root / "scripts" / "upgrade.sh").read_text(encoding="utf-8")

        self.assertIn("umask 077", upgrade)
        self.assertIn('install -d -o root -g root -m 0700 "$backup_directory"', upgrade)
        self.assertIn('chmod 0600 "$backup"', upgrade)
        self.assertIn("--exclude=var/lib/boxbrain/rescue-images", upgrade)
        self.assertIn("--exclude=var/lib/boxbrain/drive/rescue-media", upgrade)
        self.assertIn('tar -tzf "$backup"', upgrade)
        self.assertIn("systemctl stop", upgrade)
        self.assertIn("trap 'rollback $?' EXIT", upgrade)
        self.assertIn("rm -rf /opt/boxbrain", upgrade)
        self.assertIn('sh "$project_dir/scripts/install.sh"', upgrade)
        self.assertLess(upgrade.index("systemctl stop"), upgrade.index("tar -czf"))
        self.assertLess(upgrade.index("tar -tzf"), upgrade.index("trap 'rollback $?'"))

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

    def test_explicit_network_ssh_enrollment_is_verified_and_saved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            identity = state / "identity" / "target_ed25519"
            identity.parent.mkdir()
            identity.write_text("test-only", encoding="utf-8")
            verified = {
                "address": "192.168.50.23",
                "hostname": "AUTHORIZED-PC",
                "platform": "Windows",
                "user": "boxbrain-link",
                "transport": "network-ssh",
                "interface": "wlan0",
                "status": "connected",
            }
            route_result = unittest.mock.Mock(
                returncode=0,
                stdout='[{"dev":"wlan0"}]',
            )
            with (
                patch.object(link_monitor, "STATE_DIRECTORY", state),
                patch.object(link_monitor, "LINKS_DIRECTORY", state / "links"),
                patch.object(link_monitor, "IDENTITY_FILE", identity),
                patch("boxbrain.enrollment.subprocess.run", return_value=route_result),
                patch("boxbrain.enrollment.link_monitor.probe", return_value=verified),
            ):
                saved = enroll_target(
                    "192.168.50.23",
                    "network-ssh",
                    LINK_AUTHORIZATION,
                )

            self.assertEqual(saved["transport"], "network-ssh")
            self.assertEqual(saved["interface"], "wlan0")
            self.assertEqual(saved["enrollment"], "explicit")
            self.assertIn("authorized_at", saved)
            persisted = load_links(directory)
            self.assertEqual(persisted[0]["hostname"], "AUTHORIZED-PC")

    def test_network_enrollment_rejects_unauthorized_public_and_usb_routes(self) -> None:
        with self.assertRaises(TargetEnrollmentError):
            enroll_target("192.168.50.23", "network-ssh", "")
        with self.assertRaises(TargetEnrollmentError):
            enroll_target("8.8.8.8", "network-ssh", LINK_AUTHORIZATION)

        route_result = unittest.mock.Mock(
            returncode=0,
            stdout='[{"dev":"usb0"}]',
        )
        with patch("boxbrain.enrollment.subprocess.run", return_value=route_result):
            with self.assertRaises(TargetEnrollmentError):
                enroll_target(
                    "10.12.194.2",
                    "network-ssh",
                    LINK_AUTHORIZATION,
                )

    def test_control_socket_forwards_explicit_target_enrollment(self) -> None:
        request = {
            "action": "add_target",
            "address": "192.168.50.23",
            "transport": "network-ssh",
            "authorization": LINK_AUTHORIZATION,
        }
        enrolled = {
            "address": "192.168.50.23",
            "transport": "network-ssh",
            "status": "connected",
        }
        with patch(
            "boxbrain.control.enroll_target",
            return_value=enrolled,
        ) as enroll:
            response = ControlServer.dispatch(unittest.mock.Mock(), request)

        self.assertEqual(response, {"ok": True, "target": enrolled})
        enroll.assert_called_once_with(
            "192.168.50.23",
            "network-ssh",
            LINK_AUTHORIZATION,
        )

    def test_monitor_rechecks_registered_network_target_and_marks_it_offline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            links = state / "links"
            links.mkdir()
            identity = state / "identity" / "target_ed25519"
            identity.parent.mkdir()
            identity.write_text("test-only", encoding="utf-8")
            link_path = links / "192-168-50-23.json"
            link_path.write_text(
                json.dumps(
                    {
                        "address": "192.168.50.23",
                        "hostname": "AUTHORIZED-PC",
                        "transport": "network-ssh",
                        "interface": "wlan0",
                        "status": "connected",
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(link_monitor, "STATE_DIRECTORY", state),
                patch.object(link_monitor, "LINKS_DIRECTORY", links),
                patch.object(link_monitor, "IDENTITY_FILE", identity),
                patch.object(link_monitor, "neighbor_candidates", return_value=[]),
                patch.object(link_monitor, "probe", return_value=None) as probe_target,
            ):
                self.assertEqual(link_monitor.run_once(), 0)

            probe_target.assert_called_once_with(
                "192.168.50.23",
                transport="network-ssh",
                interface="wlan0",
            )
            updated = json.loads(link_path.read_text(encoding="utf-8"))
            self.assertEqual(updated["status"], "offline")
            self.assertIn("last_checked", updated)

    def test_monitor_rechecks_legacy_usb_target_and_marks_it_offline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            links = state / "links"
            links.mkdir()
            identity = state / "identity" / "target_ed25519"
            identity.parent.mkdir()
            identity.write_text("test-only", encoding="utf-8")
            link_path = links / "10-12-194-4.json"
            link_path.write_text(
                json.dumps(
                    {
                        "address": "10.12.194.4",
                        "hostname": "AUTHORIZED-USB-PC",
                        "transport": "usb-ethernet-ssh",
                        "status": "connected",
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(link_monitor, "STATE_DIRECTORY", state),
                patch.object(link_monitor, "LINKS_DIRECTORY", links),
                patch.object(link_monitor, "IDENTITY_FILE", identity),
                patch.object(link_monitor, "neighbor_candidates", return_value=[]),
                patch.object(link_monitor, "probe", return_value=None) as probe_target,
            ):
                self.assertEqual(link_monitor.run_once(), 0)

            probe_target.assert_called_once_with(
                "10.12.194.4",
                transport="usb-ethernet-ssh",
                interface="usb0",
            )
            updated = json.loads(link_path.read_text(encoding="utf-8"))
            self.assertEqual(updated["status"], "offline")
            self.assertIn("last_checked", updated)

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
