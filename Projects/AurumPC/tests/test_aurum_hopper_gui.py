from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "aurum_hopper_gui.py"
SPEC = importlib.util.spec_from_file_location("aurum_hopper_gui", MODULE_PATH)
assert SPEC and SPEC.loader
hopper = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = hopper
SPEC.loader.exec_module(hopper)

SEED_DIR = MODULE_PATH.parents[1] / "Codelation" / "seed"
SEED_GUI_PATH = SEED_DIR / "aurum_gui.py"
_seed_path_added = str(SEED_DIR) not in sys.path
if _seed_path_added:
    sys.path.insert(0, str(SEED_DIR))
_missing = object()
_saved_seed_modules = {
    name: sys.modules.get(name, _missing) for name in ("aurum_console", "aurum_dialogue")
}
try:
    for name in _saved_seed_modules:
        sys.modules.pop(name, None)
    GUI_SPEC = importlib.util.spec_from_file_location("aurum_hopper_gui_live_base", SEED_GUI_PATH)
    assert GUI_SPEC and GUI_SPEC.loader
    base_gui = importlib.util.module_from_spec(GUI_SPEC)
    sys.modules[GUI_SPEC.name] = base_gui
    GUI_SPEC.loader.exec_module(base_gui)
finally:
    for name, previous in _saved_seed_modules.items():
        if previous is _missing:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    if _seed_path_added:
        sys.path.remove(str(SEED_DIR))


class HopperGuiTests(unittest.TestCase):
    def test_html_projection_has_conversation_receipts_and_no_browser_key(self) -> None:
        page = hopper.PAGE
        self.assertIn("Aurum · Hopper", page)
        self.assertIn('class="chat-panel"', page)
        self.assertIn('id="messages"', page)
        self.assertIn("receipts visible", page)
        self.assertIn("tool_receipts", page)
        self.assertIn("Pygame fallback", page)
        self.assertIn("HTML5 living surface", page)
        self.assertIn("AinWeave · StateWeave · ComputeWeave", page)
        self.assertEqual(page.count("data-aurum-logo"), 5)
        self.assertIn("logo-crop--landscape", page)
        self.assertIn("aurum-seven-leaf-logo.jpeg", page)
        self.assertIn("prefers-reduced-motion", page)
        self.assertIn("--bg-end:#070b09", page)
        self.assertIn("applyAppearance", page)
        self.assertIn("tracked_source_modified", MODULE_PATH.read_text(encoding="utf-8"))
        self.assertNotIn('id="apiKey"', page)
        self.assertNotIn("bootstrapKey", page)
        self.assertNotIn("body.api_key", page)
        self.assertNotIn("/api/actuate", page)

    def test_html5_browser_is_bounded_and_has_landscape_controls(self) -> None:
        page = hopper.PAGE
        self.assertIn('data-nav="browser"', page)
        self.assertIn('id="web-browser"', page)
        self.assertIn('id="web-address"', page)
        self.assertIn('id="web-back"', page)
        self.assertIn('id="web-forward"', page)
        self.assertIn('id="web-reload"', page)
        self.assertIn('sandbox="allow-forms allow-scripts"', page)
        self.assertIn('referrerpolicy="no-referrer"', page)
        self.assertIn("normalizeWebTarget", page)
        self.assertIn("target.protocol!=='https:'", page)
        self.assertIn("privateWebHost", page)
        self.assertIn("No Aurum proxy", page)
        self.assertIn('frame_source_policy = "https:"', MODULE_PATH.read_text(encoding="utf-8"))
        self.assertNotIn("allow-same-origin", page)
        self.assertNotIn("allow-top-navigation", page)

    def test_server_source_rejects_browser_credential_bootstrap(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("RUNTIME_GUI_PATH", source)
        self.assertIn("RUNTIME_LOGO_PATH", source)
        self.assertLess(source.index("RUNTIME_GUI_PATH, GUI_PATH"), source.index("Aurum GUI source unavailable"))
        self.assertIn('request_path == "/api/key-bootstrap"', source)
        self.assertIn("machine-sealed runtime credential", source)
        self.assertIn('{"prompt", "model"}', source)
        self.assertNotIn('issubset({"prompt", "api_key", "model"})', source)

    def test_seven_leaf_mark_is_checksum_sealed_before_html5_projection(self) -> None:
        mark = MODULE_PATH.parents[1] / "Codelation" / "assets" / "identity" / "aurum-seven-leaf-logo-matrix.jpeg"
        payload = hopper._verified_logo_bytes(mark)
        self.assertIsNotNone(payload)
        self.assertEqual(hashlib.sha256(payload or b"").hexdigest(), hopper.LOGO_SHA256)
        self.assertIn('"scope": "aurum-native-seven-leaf"', MODULE_PATH.read_text(encoding="utf-8"))


class HopperGuiLiveRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.original_handler = base_gui.AurumGuiHandler
        base_gui.AurumGuiHandler = hopper._make_handler(base_gui)
        self.server = base_gui.create_server(
            "127.0.0.1",
            0,
            self.root,
            reasoner=lambda _prompt, _model: "unused",
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        base_gui.AurumGuiHandler = self.original_handler
        self.temporary.cleanup()

    def _request(
        self,
        path: str,
        *,
        payload: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object] | str]:
        request_headers = dict(headers or {})
        data = None
        method = "GET"
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            method = "POST"
            request_headers.setdefault("Content-Type", "application/json")
            request_headers.setdefault("Origin", self.base_url)
            request_headers.setdefault("X-Aurum-CSRF", self.server.csrf_token)
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers=request_headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                status = response.status
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            status = exc.code
            try:
                body = exc.read().decode("utf-8")
            finally:
                exc.close()
        try:
            return status, json.loads(body)
        except json.JSONDecodeError:
            return status, body

    @staticmethod
    def _healthy_module(filename: str, _prefix: str):
        if filename == "aurum_gpt_executor.py":
            return SimpleNamespace(
                status_snapshot=lambda: {
                    "machine": "Hopper",
                    "runtime": "ready",
                    "desktop_generation": "gen1-html",
                    "input": "ready",
                },
                execute_control=lambda action: {
                    "schema": "aurum.gpt-executor.gen1",
                    "status": "completed",
                    "action": action,
                    "verified": True,
                },
            )
        if filename == "aurum_gpt_trait.py":
            return SimpleNamespace(
                status=lambda: {
                    "status": "ready",
                    "function_tools": True,
                    "credential_source": "machine-sealed-runtime",
                },
                ask=lambda prompt, **_kwargs: {
                    "status": "completed",
                    "text": f"heard:{prompt}",
                    "tool_receipts": [],
                    "host_actuation": False,
                },
            )
        if filename == "aurum_network.py":
            return SimpleNamespace(network_status=lambda: {"online": True, "interface": "eth0"})
        if filename == "aurum_time.py":
            return SimpleNamespace(time_status=lambda: {"synchronized": True})
        return None

    def test_live_status_and_bounded_action_return_json_receipts(self) -> None:
        with patch.object(hopper, "_load_runtime_module", side_effect=self._healthy_module):
            status_code, status = self._request("/api/status")
            action_code, action = self._request("/api/action", payload={"action": "status"})

        self.assertEqual(status_code, 200)
        self.assertIsInstance(status, dict)
        self.assertEqual(status["hopper"]["telemetry"]["state"]["runtime"], "ready")
        self.assertEqual(action_code, 200)
        self.assertIsInstance(action, dict)
        self.assertTrue(action["result"]["verified"])
        self.assertFalse(action["result"].get("raw_shell", False))

    def test_live_status_survives_failing_status_modules(self) -> None:
        broken = SimpleNamespace(
            status_snapshot=lambda: (_ for _ in ()).throw(RuntimeError("snapshot-boom")),
            network_status=lambda: (_ for _ in ()).throw(RuntimeError("network-boom")),
            time_status=lambda: (_ for _ in ()).throw(RuntimeError("time-boom")),
            status=lambda: (_ for _ in ()).throw(RuntimeError("trait-boom")),
        )
        with patch.object(hopper, "_load_runtime_module", return_value=broken):
            code, payload = self._request("/api/status")

        self.assertEqual(code, 200)
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["hopper"]["telemetry"]["state"]["status"], "unavailable")
        self.assertEqual(payload["hopper"]["gpt"]["status"], "unavailable")

    def test_live_ask_turns_malformed_trait_output_into_json_failure(self) -> None:
        malformed_trait = SimpleNamespace(ask=lambda _prompt, **_kwargs: None)
        with patch.object(hopper, "_load_runtime_module", return_value=malformed_trait):
            code, payload = self._request("/api/ask", payload={"prompt": "hello"})

        self.assertEqual(code, 502)
        self.assertIsInstance(payload, dict)
        self.assertIn("GPT unavailable", payload["error"])

    def test_live_action_turns_unserializable_executor_output_into_json_failure(self) -> None:
        malformed_executor = SimpleNamespace(execute_control=lambda _action: {"bad": {"set-value"}})
        with patch.object(hopper, "_load_runtime_module", return_value=malformed_executor):
            code, payload = self._request("/api/action", payload={"action": "status"})

        self.assertEqual(code, 400)
        self.assertIsInstance(payload, dict)
        self.assertIn("bounded action failed", payload["error"])

    def test_live_ask_serializes_concurrent_model_calls(self) -> None:
        state_lock = threading.Lock()
        active = 0
        max_active = 0

        def ask(prompt: str, **_kwargs):
            nonlocal active, max_active
            with state_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.05)
            with state_lock:
                active -= 1
            return {
                "status": "completed",
                "text": prompt,
                "tool_receipts": [],
                "host_actuation": False,
            }

        trait = SimpleNamespace(ask=ask)
        with patch.object(hopper, "_load_runtime_module", return_value=trait):
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(
                    pool.map(
                        lambda prompt: self._request("/api/ask", payload={"prompt": prompt}),
                        ("one", "two"),
                    )
                )

        self.assertEqual([code for code, _payload in responses], [200, 200])
        self.assertEqual(max_active, 1)

    def test_live_post_requires_loopback_origin_and_csrf(self) -> None:
        with patch.object(hopper, "_load_runtime_module", side_effect=self._healthy_module):
            bad_origin_code, _ = self._request(
                "/api/action",
                payload={"action": "status"},
                headers={"Origin": "https://example.invalid"},
            )
            bad_csrf_code, _ = self._request(
                "/api/action",
                payload={"action": "status"},
                headers={"X-Aurum-CSRF": "wrong"},
            )

        self.assertEqual(bad_origin_code, 403)
        self.assertEqual(bad_csrf_code, 403)


if __name__ == "__main__":
    unittest.main()
