from __future__ import annotations

import http.client
import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path


CODELATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODELATION / "seed"))

import aurum_gui


class AurumGuiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "mind").mkdir(parents=True)
        shutil.copy2(
            CODELATION / "mind" / "bootstrap_mind.json",
            self.root / "mind" / "bootstrap_mind.json",
        )

        def reasoner(messages: list[dict], model: str, api_key: str) -> tuple[str, str]:
            self.assertEqual(api_key, "test-secret-key")
            self.assertTrue(messages)
            self.assertEqual(model, "gpt-5-mini")
            return "Bounded GUI reply.", "test-request-id"

        self.server = aurum_gui.create_server(
            "127.0.0.1",
            0,
            self.root,
            reasoner=reasoner,
        )
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        request_headers = {"Host": f"127.0.0.1:{self.port}"}
        request_headers.update(headers or {})
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        payload = response.read()
        status = response.status
        result_headers = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        return status, result_headers, payload

    def test_shell_preserves_landmarks_and_security_headers(self) -> None:
        status, headers, body = self.request("GET", "/")

        self.assertEqual(status, 200)
        page = body.decode("utf-8")
        for label in ("Home", "Back", "Search", "Settings", "Notices", "Spaces", "Safe"):
            self.assertIn(label, page)
        self.assertIn("Proof View", page)
        self.assertIn("API key · memory only", page)
        self.assertIn("default-src 'none'", headers["content-security-policy"])
        self.assertEqual(headers["x-frame-options"], "DENY")
        self.assertEqual(headers["cache-control"], "no-store, max-age=0")

    def test_status_is_dialogue_only_and_returns_no_user_content(self) -> None:
        status, _, body = self.request("GET", "/api/status")

        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["console"]["identity"], "BBPI4/Aurum")
        self.assertTrue(payload["interface"]["safe_layout_available"])
        self.assertTrue(payload["proof_view"]["present"])
        self.assertFalse(payload["proof_view"]["user_content_returned"])
        self.assertTrue(payload["authority"]["dialogue_only"])
        self.assertFalse(payload["authority"]["host_actuation"])
        self.assertFalse(payload["authority"]["api_key_persisted"])

    def test_dialogue_request_requires_origin_and_csrf_and_never_persists_key(self) -> None:
        body = json.dumps(
            {"prompt": "private prompt text", "api_key": "test-secret-key"}
        ).encode("utf-8")
        common_headers = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{self.port}",
        }
        rejected, _, _ = self.request(
            "POST",
            "/api/ask",
            body=body,
            headers=common_headers,
        )
        self.assertEqual(rejected, 403)

        accepted, _, response_body = self.request(
            "POST",
            "/api/ask",
            body=body,
            headers={
                **common_headers,
                "X-Aurum-CSRF": self.server.csrf_token,
            },
        )

        self.assertEqual(accepted, 200)
        payload = json.loads(response_body)
        self.assertEqual(payload["response"], "Bounded GUI reply.")
        self.assertFalse(payload["host_actuation"])
        self.assertFalse(payload["api_key_persisted"])
        written = "\n".join(
            path.read_text(encoding="utf-8")
            for path in self.root.rglob("*")
            if path.is_file()
        )
        self.assertNotIn("test-secret-key", written)
        self.assertNotIn("private prompt text", written)

    def test_non_loopback_bind_and_host_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "loopback"):
            aurum_gui.create_server("0.0.0.0", 8765, self.root)

        status, _, _ = self.request(
            "GET",
            "/api/status",
            headers={"Host": "example.invalid"},
        )
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
