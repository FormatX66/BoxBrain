from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boxbrain.hid_kvm import HidKvmError, HidKvmState  # noqa: E402
from boxbrain.console_gateway import build_gateway  # noqa: E402
from boxbrain.server import build_server  # noqa: E402


class HidKvmTests(unittest.TestCase):
    def test_keyboard_pointer_text_and_watchdog_emit_bounded_reports(self) -> None:
        writes: list[tuple[Path, bytes]] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = HidKvmState(
                keyboard=root / "hidg0",
                mouse=root / "hidg1",
                audit=root / "hid-kvm.jsonl",
                writer=lambda path, report: writes.append((path, report)),
            )

            state.handle({"action": "key", "code": "ControlLeft", "down": True})
            state.handle({"action": "key", "code": "KeyA", "down": True})
            self.assertEqual(writes[-1][1], bytes([1, 0, 4, 0, 0, 0, 0, 0]))
            state.handle(
                {"action": "pointer", "dx": -4, "dy": 9, "wheel": -1, "buttons": 1}
            )
            self.assertEqual(writes[-1][1], bytes([1, 252, 9, 255]))
            state.handle({"action": "text", "text": "Aa!"})
            self.assertEqual(writes[-1][1], b"\0" * 8)
            result = state.handle({"action": "character", "character": "r"})
            self.assertTrue(result["acknowledged"])
            self.assertEqual(writes[-2][1], bytes([0, 0, 0x15, 0, 0, 0, 0, 0]))
            self.assertEqual(writes[-1][1], b"\0" * 8)
            audit = (root / "hid-kvm.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("Aa!", audit)
            self.assertIn('"character_count":3', audit)
            self.assertNotIn('"character":"r"', audit)
            self.assertIn('"acknowledged":true', audit)

            state.handle({"action": "key", "code": "KeyB", "down": True})
            self.assertTrue(state.release_if_idle(state.last_activity + 3))
            self.assertEqual(writes[-2][1], b"\0" * 8)
            self.assertEqual(writes[-1][1], b"\0" * 4)

    def test_rejects_unknown_keys_large_text_and_out_of_range_pointer(self) -> None:
        state = HidKvmState(writer=lambda _path, _report: None)
        with self.assertRaises(HidKvmError):
            state.handle({"action": "key", "code": "Power", "down": True})
        with self.assertRaises(HidKvmError):
            state.handle({"action": "text", "text": "x" * 257})
        with self.assertRaises(HidKvmError):
            state.handle({"action": "character", "character": "ab"})
        with self.assertRaises(HidKvmError):
            state.handle({"action": "pointer", "dx": 128, "dy": 0, "wheel": 0, "buttons": 0})

    def test_local_http_surface_requires_csrf_for_input(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.requests: list[dict[str, object]] = []

            def request(self, payload: dict[str, object]) -> dict[str, object]:
                self.requests.append(payload)
                if payload.get("action") == "status":
                    return {
                        "ok": True,
                        "status": {"keyboard_ready": True, "mouse_ready": True},
                    }
                return {"ok": True}

        fake = FakeClient()
        server = build_server(
            "127.0.0.1",
            0,
            hid_kvm_client=fake,  # type: ignore[arg-type]
            hid_kvm_csrf_token="test-csrf-token",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            with urlopen(f"http://{host}:{port}/kvm", timeout=3) as response:
                page = response.read().decode("utf-8")
            self.assertIn("Morris PC", page)
            self.assertIn("test-csrf-token", page)
            self.assertIn("Ctrl+Alt+Delete", page)
            self.assertIn("action:'character'", page)
            self.assertIn("Acknowledged single-character typing", page)

            with urlopen(
                f"http://{host}:{port}/api/v1/hid-kvm/status", timeout=3
            ) as response:
                status = json.load(response)
            self.assertTrue(status["status"]["keyboard_ready"])

            body = json.dumps({"action": "release"}).encode("utf-8")
            rejected = Request(
                f"http://{host}:{port}/api/v1/hid-kvm/input",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as error:
                urlopen(rejected, timeout=3)
            self.assertEqual(error.exception.code, 403)

            accepted = Request(
                f"http://{host}:{port}/api/v1/hid-kvm/input",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-BoxBrain-CSRF": "test-csrf-token",
                },
                method="POST",
            )
            with urlopen(accepted, timeout=3) as response:
                self.assertTrue(json.load(response)["ok"])
            self.assertIn({"action": "release"}, fake.requests)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_console_gateway_serves_novnc_files_and_proxies_kvm(self) -> None:
        class FakeClient:
            def request(self, payload: dict[str, object]) -> dict[str, object]:
                if payload.get("action") == "status":
                    return {
                        "ok": True,
                        "status": {"keyboard_ready": True, "mouse_ready": True},
                    }
                return {"ok": True, "released": True}

        backend = build_server(
            "127.0.0.1",
            0,
            hid_kvm_client=FakeClient(),  # type: ignore[arg-type]
            hid_kvm_csrf_token="gateway-token",
        )
        backend_thread = threading.Thread(target=backend.serve_forever, daemon=True)
        backend_thread.start()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("console-ready", encoding="utf-8")
            gateway = build_gateway(
                "127.0.0.1",
                0,
                root,
                "127.0.0.1",
                backend.server_address[1],
            )
            gateway_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
            gateway_thread.start()
            host, port = gateway.server_address
            try:
                with urlopen(f"http://{host}:{port}/index.html", timeout=3) as response:
                    self.assertEqual(response.read(), b"console-ready")
                with urlopen(f"http://{host}:{port}/kvm", timeout=3) as response:
                    page = response.read().decode("utf-8")
                self.assertIn("Morris PC", page)
                body = json.dumps({"action": "release"}).encode("utf-8")
                request = Request(
                    f"http://{host}:{port}/api/v1/hid-kvm/input",
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-BoxBrain-CSRF": "gateway-token",
                    },
                    method="POST",
                )
                with urlopen(request, timeout=3) as response:
                    self.assertTrue(json.load(response)["released"])
            finally:
                gateway.shutdown()
                gateway.server_close()
                gateway_thread.join(timeout=3)
        backend.shutdown()
        backend.server_close()
        backend_thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
