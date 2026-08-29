from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "aurum_core_share.py"
SPEC = importlib.util.spec_from_file_location("aurum_core_share_test", MODULE_PATH)
assert SPEC and SPEC.loader
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core
SPEC.loader.exec_module(core)


class AurumCoreShareTests(unittest.TestCase):
    def test_open_core_port_does_not_collide_with_hopper_gui(self) -> None:
        gui_source = (ROOT / "aurum_gui_runtime.py").read_text(encoding="utf-8")
        self.assertEqual(core.DEFAULT_PORT, 8767)
        self.assertIn("DEFAULT_PORT = 8765", gui_source)
        self.assertNotEqual(core.DEFAULT_PORT, 8765)

    def test_catalog_is_open_but_exports_no_files_or_slush(self) -> None:
        catalog = core.catalog()
        self.assertFalse(catalog["authentication_required"])
        self.assertEqual(catalog["actions"], ["status", "seed-sync"])
        self.assertTrue(catalog["fast_forward_only"])
        self.assertFalse(catalog["arbitrary_command"])
        self.assertFalse(catalog["file_serving"])
        self.assertFalse(catalog["directory_listing"])
        self.assertFalse(catalog["personal_slush"]["exported"])
        self.assertFalse(catalog["personal_slush"]["readable_by_core_share"])

    def test_seed_sync_is_fixed_to_clean_forward_trunk_and_returns_sanitized_state(self) -> None:
        class Workspace:
            def __init__(self, **_kwargs):
                pass

            def git_sync(self, *, authorize_network: bool):
                self.authorized = authorize_network
                return {
                    "status": "fast-forwarded",
                    "repository": core.REPOSITORY,
                    "branch": core.BRANCH,
                    "head": "a" * 40,
                    "dirty": False,
                    "checkpoint": "private-detail-must-not-escape",
                }

        class RuntimeUpdater:
            def __init__(self, **_kwargs):
                pass

            def apply(self):
                return {
                    "status": "updated",
                    "changed": ["aurum_core_share.py"],
                    "system_changed": ["etc/systemd/system/aurum-core-share.service"],
                    "secret_profile_fingerprint": "must-not-escape",
                    "generation": {
                        "become_next_seed": True,
                        "prove": {"wifi": {"status": "passed", "fingerprint": "must-not-escape"}},
                    },
                }

        def load(filename: str, _prefix: str):
            if filename == "aurum_network.py":
                return SimpleNamespace(ensure_online=lambda **_kwargs: {"online": True, "ssid": "private"})
            if filename == "aurum_workspace.py":
                return SimpleNamespace(AurumWorkspace=Workspace)
            if filename == "aurum_runtime_update.py":
                return SimpleNamespace(RuntimeUpdater=RuntimeUpdater)
            raise AssertionError(filename)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(core.os, "geteuid", return_value=0, create=True),
                patch.object(core, "DEFAULT_RUN", root / "run"),
                patch.object(core, "DEFAULT_WORKSPACE", root / "workspace"),
                patch.object(core, "DEFAULT_RUNTIME", root / "runtime"),
                patch.object(core, "_load_module", side_effect=load),
            ):
                receipt = core.seed_sync(state_dir=root / "state")
        encoded = json.dumps(receipt, sort_keys=True)
        self.assertEqual(receipt["result"]["status"], "verified")
        self.assertEqual(receipt["result"]["git"]["head"], "a" * 40)
        self.assertTrue(receipt["result"]["fast_forward_only"])
        self.assertFalse(receipt["result"]["personal_slush_accessed"])
        self.assertFalse(receipt["result"]["personal_data_exported"])
        self.assertNotIn("private-detail", encoded)
        self.assertNotIn("must-not-escape", encoded)
        self.assertNotIn("ssid", encoded.lower())

    def test_http_surface_has_only_status_and_empty_seed_sync(self) -> None:
        server = core.CoreShareServer(("127.0.0.1", 0), core.CoreShareHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with patch.object(core, "status", return_value={"schema": core.SCHEMA, "status": "ready"}):
                with urllib.request.urlopen(base + "/status", timeout=5) as response:
                    payload = json.loads(response.read())
                self.assertEqual(payload["status"], "ready")
                self.assertEqual(response.headers["Access-Control-Allow-Origin"], "*")
            with patch.object(core, "seed_sync", return_value={"schema": core.RECEIPT_SCHEMA, "result": {"status": "verified"}}):
                request = urllib.request.Request(base + "/seed-sync", data=b"", method="POST")
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read())
                self.assertEqual(payload["result"]["status"], "verified")
            for path in ("/files", "/slush", "/shell"):
                with self.subTest(path=path):
                    try:
                        urllib.request.urlopen(base + path, timeout=5)
                    except urllib.error.HTTPError as error:
                        self.assertEqual(error.code, 404)
                        error.close()
                    else:
                        self.fail(f"open core unexpectedly served {path}")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_boot_units_auto_sync_open_core_and_hide_personal_namespaces(self) -> None:
        auto_sync = (ROOT / "runtime-assets/etc/systemd/system/aurum-auto-sync.service").read_text(encoding="utf-8")
        core_share = (ROOT / "runtime-assets/etc/systemd/system/aurum-core-share.service").read_text(encoding="utf-8")
        self.assertIn("After=network-online.target aurum-network-bootstrap.service", auto_sync)
        self.assertIn("aurum_core_share.py seed-sync", auto_sync)
        self.assertIn("Restart=on-failure", auto_sync)
        self.assertIn("aurum_core_share.py serve --bind 0.0.0.0 --port 8767", core_share)
        self.assertNotIn("Authentication", core_share)
        for unit in (auto_sync, core_share):
            self.assertIn("ProtectHome=yes", unit)
            self.assertIn("InaccessiblePaths=-/var/lib/aurum/slush", unit)


if __name__ == "__main__":
    unittest.main()
