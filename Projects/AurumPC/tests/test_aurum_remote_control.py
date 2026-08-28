from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
REPOSITORY_ROOT = ROOT.parents[1]
MODULE_PATH = ROOT / "aurum_remote_control.py"
SPEC = importlib.util.spec_from_file_location("aurum_remote_control_test", MODULE_PATH)
assert SPEC and SPEC.loader
remote = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = remote
SPEC.loader.exec_module(remote)


def ed25519_public_key(comment: str = "test-controller") -> str:
    key_type = b"ssh-ed25519"
    key_bytes = bytes(range(32))
    blob = (
        len(key_type).to_bytes(4, "big")
        + key_type
        + len(key_bytes).to_bytes(4, "big")
        + key_bytes
    )
    return f"ssh-ed25519 {base64.b64encode(blob).decode('ascii')} {comment}"


class AurumRemoteControlTests(unittest.TestCase):
    def test_catalog_has_only_fixed_sync_and_loopback_desktop(self) -> None:
        catalog = remote.catalog()
        self.assertFalse(catalog["raw_shell"])
        self.assertFalse(catalog["arbitrary_command"])
        self.assertFalse(catalog["password_authentication"])
        self.assertEqual(catalog["remote_seed_sync"]["branch"], "aurum/trunk-v0.01")
        self.assertTrue(catalog["remote_seed_sync"]["fast_forward_only"])
        self.assertEqual(catalog["remote_desktop"]["listener"], "127.0.0.1")
        self.assertFalse(catalog["remote_desktop"]["direct_lan_listener"])
        self.assertIn("desktop-tunnel", catalog["commands"])

    def test_pairing_accepts_one_canonical_key_and_stores_no_private_key(self) -> None:
        key = ed25519_public_key()
        normalized, fingerprint = remote.normalize_public_key(key)
        self.assertEqual(normalized, key)
        self.assertTrue(fingerprint.startswith("SHA256:"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = remote.enroll_public_key(
                key,
                authorized_keys=root / "remote" / ".ssh" / "authorized_keys",
                state_dir=root / "state",
            )
            stored = (root / "remote" / ".ssh" / "authorized_keys").read_text(encoding="utf-8")
            self.assertEqual(stored, key + "\n")
            self.assertFalse(receipt["result"]["private_key_stored_on_hopper"])
            self.assertFalse(receipt["raw_shell"])

    def test_pairing_rejects_options_multiple_lines_and_non_ed25519(self) -> None:
        key = ed25519_public_key()
        for invalid in (
            "command=\"sh\" " + key,
            key + "\n" + key,
            key.replace("ssh-ed25519", "ssh-rsa", 1),
        ):
            with self.subTest(value=invalid[:30]):
                with self.assertRaises(remote.RemoteControlError):
                    remote.normalize_public_key(invalid)

    def test_desktop_process_is_loopback_only_and_browser_accessible(self) -> None:
        command = remote._desktop_command("/usr/bin/x11vnc")
        self.assertIn("-localhost", command)
        self.assertIn("-nopw", command)
        self.assertNotIn("-auth", command)
        self.assertNotIn("guess", command)
        self.assertNotIn("0.0.0.0", command)
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("127.0.0.1:{WEBSOCKET_PORT}", source)
        self.assertIn("--web={novnc_root}", source)
        self.assertIn("RuntimeMaxSec", source)
        self.assertIn("desktop-session-proof.json", source)
        self.assertIn('"aurum.remote-desktop-proof.v1"', source)

    def test_clean_stop_seals_current_boot_loopback_session_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            latest = state / "remote-control" / "latest.json"
            latest.parent.mkdir(parents=True)
            latest.write_text(
                json.dumps({
                    "operation": "desktop-start",
                    "boot_id": "boot-test",
                    "observed_at": "2026-08-28T00:00:00Z",
                    "result": {"status": "running", "loopback_only": True},
                }),
                encoding="utf-8",
            )
            completed = subprocess.CompletedProcess(["systemctl"], 0, "")
            with (
                patch.object(remote.os, "geteuid", return_value=0, create=True),
                patch.object(remote.shutil, "which", return_value="/usr/bin/systemctl"),
                patch.object(remote, "_run", return_value=completed),
                patch.object(remote, "_listener_addresses", return_value=[]),
                patch.object(remote, "_boot_id", return_value="boot-test"),
            ):
                receipt = remote.desktop_stop(state_dir=state)
            proof = json.loads(
                (state / "remote-control" / "desktop-session-proof.json").read_text(encoding="utf-8")
            )
        self.assertEqual(receipt["operation"], "desktop-stop")
        self.assertEqual(proof["status"], "passed")
        self.assertTrue(proof["loopback_only"])
        self.assertFalse(proof["direct_lan_listener"])
        self.assertFalse(proof["raw_shell"])

    def test_seed_sync_accepts_workspace_ready_projection_and_keeps_fixed_trunk(self) -> None:
        class Workspace:
            def __init__(self, **_kwargs):
                pass

            def git_sync(self, *, authorize_network: bool):
                self.authorized = authorize_network
                return {
                    "status": "ready",
                    "repository": "https://github.com/FormatX66/BoxBrain.git",
                    "branch": "aurum/trunk-v0.01",
                    "dirty": False,
                    "head": "a" * 40,
                }

        class RuntimeUpdater:
            def __init__(self, **_kwargs):
                pass

            def apply(self):
                return {"status": "updated", "generation": {"become_next_seed": True}}

        def load(filename: str, _prefix: str):
            if filename == "aurum_network.py":
                return SimpleNamespace(ensure_online=lambda **_kwargs: {"online": True})
            if filename == "aurum_workspace.py":
                return SimpleNamespace(AurumWorkspace=Workspace)
            if filename == "aurum_runtime_update.py":
                return SimpleNamespace(RuntimeUpdater=RuntimeUpdater)
            raise AssertionError(filename)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(remote.os, "geteuid", return_value=0, create=True),
                patch.object(remote, "DEFAULT_RUN", root / "run"),
                patch.object(remote, "DEFAULT_WORKSPACE", root / "workspace"),
                patch.object(remote, "DEFAULT_RUNTIME", root / "runtime"),
                patch.object(remote, "_load_module", side_effect=load),
            ):
                receipt = remote.seed_sync(state_dir=root / "state")
        self.assertEqual(receipt["result"]["status"], "verified")
        self.assertTrue(receipt["result"]["become_next_seed"])
        self.assertFalse(receipt["result"]["wifi_configuration_mutated"])
        self.assertFalse(receipt["result"]["raw_shell"])

    def test_remote_account_can_accept_keys_but_never_passwords(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        ssh_config = (ROOT / "runtime-assets/etc/ssh/sshd_config.d/60-aurum-remote.conf").read_text(encoding="utf-8")
        self.assertIn('[usermod, "--password", "AURUM-REMOTE-KEY-ONLY", REMOTE_USER]', source)
        self.assertNotIn('[passwd, "--lock", REMOTE_USER]', source)
        self.assertIn('[ssh_keygen, "-A"]', source)
        self.assertIn('Path("/run/sshd").mkdir', source)
        self.assertIn("PasswordAuthentication no", ssh_config)
        self.assertIn("KbdInteractiveAuthentication no", ssh_config)
        self.assertIn("AuthenticationMethods publickey", ssh_config)

    def test_forced_command_ssh_and_windows_launchers_preserve_boundary(self) -> None:
        command = (ROOT / "aurum_remote_command.py").read_text(encoding="utf-8")
        ssh_config = (ROOT / "runtime-assets/etc/ssh/sshd_config.d/60-aurum-remote.conf").read_text(encoding="utf-8")
        sudoers = (ROOT / "runtime-assets/etc/sudoers.d/aurum-remote").read_text(encoding="utf-8")
        self.assertIn("SSH_ORIGINAL_COMMAND", command)
        self.assertIn("EXACT_COMMANDS", command)
        self.assertNotIn("shell=True", command)
        for token in (
            "PasswordAuthentication no",
            "AllowUsers aurum-remote",
            "ForceCommand /usr/bin/python3 /opt/aurum/aurum_remote_command.py",
            "PermitTTY no",
            "AllowTcpForwarding local",
            "PermitOpen 127.0.0.1:5900 127.0.0.1:6080 127.0.0.1:8765",
            "GatewayPorts no",
        ):
            self.assertIn(token, ssh_config)
        for action in ("status", "seed-sync", "desktop-start", "desktop-stop"):
            self.assertIn(f"aurum_remote_control.py {action}", sudoers)
        for script_name in (
            "setup-aurum-hopper-remote.ps1",
            "invoke-aurum-hopper-seed-sync.ps1",
            "open-aurum-hopper-remote-desktop.ps1",
        ):
            source = (REPOSITORY_ROOT / "installer" / script_name).read_text(encoding="utf-8")
            self.assertIn("StrictHostKeyChecking=yes", source) if script_name != "setup-aurum-hopper-remote.ps1" else self.assertIn("ExpectedHostFingerprint", source)
            self.assertNotIn("StrictHostKeyChecking=no", source)
        desktop_launcher = (REPOSITORY_ROOT / "installer/open-aurum-hopper-remote-desktop.ps1").read_text(encoding="utf-8")
        self.assertIn("Invoke-WebRequest", desktop_launcher)
        self.assertIn("did not prove the browser Remote Desktop listener", desktop_launcher)

    def test_runtime_acceptance_requires_remote_and_gpt_panels(self) -> None:
        runtime_path = ROOT / "aurum_runtime_update.py"
        spec = importlib.util.spec_from_file_location("aurum_remote_runtime_test", runtime_path)
        assert spec and spec.loader
        runtime = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = runtime
        spec.loader.exec_module(runtime)
        with tempfile.TemporaryDirectory() as temporary:
            updater = runtime.RuntimeUpdater(
                target=ROOT,
                state_dir=Path(temporary),
                system_root=ROOT / "runtime-assets",
            )
            proof = updater._remote_control_proof()
        self.assertEqual(proof["status"], "passed", proof)
        self.assertTrue(proof["ssh_restricted"])
        self.assertTrue(proof["remote_panel"])
        self.assertTrue(proof["gpt_prompt_panel"])
        self.assertFalse(proof["raw_shell"])


if __name__ == "__main__":
    unittest.main()
