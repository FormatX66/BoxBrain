from __future__ import annotations

import errno
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
import aurum_gui_context


class AurumGuiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "mind").mkdir(parents=True)
        shutil.copy2(
            CODELATION / "mind" / "bootstrap_mind.json",
            self.root / "mind" / "bootstrap_mind.json",
        )
        self.reasoner_calls: list[list[dict]] = []

        def reasoner(messages: list[dict], model: str, api_key: str) -> tuple[str, str]:
            self.reasoner_calls.append(messages)
            self.assertEqual(api_key, "test-secret-key")
            self.assertTrue(messages)
            self.assertEqual(model, "gpt-5-mini")
            return "Bounded GUI reply.", "test-request-id"

        self.reasoner = reasoner
        self._start_server()

    def _start_server(self) -> None:
        self.server = aurum_gui_context.create_server(
            "127.0.0.1",
            0,
            self.root,
            reasoner=self.reasoner,
        )
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def _stop_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def tearDown(self) -> None:
        self._stop_server()
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
        self.assertIn("consumeKeyBootstrap", page)
        self.assertIn("No dialogue request has been sent", page)
        self.assertIn("default-src 'none'", headers["content-security-policy"])
        self.assertEqual(headers["x-frame-options"], "DENY")
        self.assertEqual(headers["cache-control"], "no-store, max-age=0")

    def test_status_is_dialogue_only_and_returns_no_user_content(self) -> None:
        status, _, body = self.request("GET", "/api/status")

        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["console"]["identity"], "BBPI4/Aurum")
        self.assertTrue(payload["interface"]["safe_layout_available"])
        self.assertTrue(payload["interface"]["adaptation_lock_available"])
        self.assertEqual(payload["preferences"]["revision"], 0)
        self.assertFalse(payload["preferences"]["safe_layout"])
        self.assertFalse(payload["preferences"]["adaptation_locked"])
        self.assertTrue(payload["proof_view"]["present"])
        self.assertFalse(payload["proof_view"]["user_content_returned"])
        self.assertTrue(payload["authority"]["dialogue_only"])
        self.assertFalse(payload["authority"]["host_actuation"])
        self.assertFalse(payload["authority"]["api_key_persisted"])
        self.assertEqual(payload["key_bootstrap"]["schema"], "aurum.gui.key-bootstrap.v1")
        self.assertTrue(payload["key_bootstrap"]["memory_only"])
        self.assertFalse(payload["key_bootstrap"]["pending"])
        self.assertFalse(payload["key_bootstrap"]["api_key_returned"])
        self.assertTrue(payload["context"]["bounded_prior_turns"])
        self.assertFalse(payload["context"]["raw_context_persisted"])
        self.assertFalse(payload["context"]["semantic_context_lost"])

    def test_key_bootstrap_is_memory_only_consumed_once_and_content_free(self) -> None:
        secret = "sk-test-one-time-bootstrap-secret"
        headers = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{self.port}",
            "X-Aurum-CSRF": self.server.csrf_token,
        }
        stage_body = json.dumps({"action": "stage", "api_key": secret}).encode("utf-8")

        rejected, _, _ = self.request(
            "POST",
            "/api/key-bootstrap",
            body=stage_body,
            headers={"Content-Type": "application/json", "Origin": headers["Origin"]},
        )
        self.assertEqual(rejected, 403)

        staged_status, _, staged_body = self.request(
            "POST", "/api/key-bootstrap", body=stage_body, headers=headers
        )
        self.assertEqual(staged_status, 200)
        staged = json.loads(staged_body)
        self.assertTrue(staged["staged"])
        self.assertTrue(staged["memory_only"])
        self.assertFalse(staged["api_key_persisted"])
        self.assertNotIn("api_key", staged)

        status, _, status_body = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        status_payload = json.loads(status_body)
        self.assertTrue(status_payload["key_bootstrap"]["pending"])
        self.assertNotIn(secret, status_body.decode("utf-8"))

        consume_body = json.dumps({"action": "consume"}).encode("utf-8")
        consumed_status, _, consumed_body = self.request(
            "POST", "/api/key-bootstrap", body=consume_body, headers=headers
        )
        self.assertEqual(consumed_status, 200)
        consumed = json.loads(consumed_body)
        self.assertTrue(consumed["available"])
        self.assertEqual(consumed["api_key"], secret)
        self.assertFalse(consumed["api_key_persisted"])

        empty_status, _, empty_body = self.request(
            "POST", "/api/key-bootstrap", body=consume_body, headers=headers
        )
        self.assertEqual(empty_status, 200)
        empty = json.loads(empty_body)
        self.assertFalse(empty["available"])
        self.assertNotIn("api_key", empty)

        written = "\n".join(
            path.read_text(encoding="utf-8")
            for path in self.root.rglob("*")
            if path.is_file()
        )
        self.assertNotIn(secret, written)

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
        self.assertEqual(payload["context_sequence"], 1)
        self.assertTrue(payload["context_continuity"])
        self.assertFalse(payload["host_actuation"])
        self.assertFalse(payload["api_key_persisted"])
        written = "\n".join(
            path.read_text(encoding="utf-8")
            for path in self.root.rglob("*")
            if path.is_file()
        )
        self.assertNotIn("test-secret-key", written)
        self.assertNotIn("private prompt text", written)

    def test_gui_context_reaches_next_reasoning_call_and_restart_loss_is_visible(self) -> None:
        headers = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{self.port}",
            "X-Aurum-CSRF": self.server.csrf_token,
        }
        first_prompt = "context first private prompt"
        second_prompt = "context second private prompt"
        first_body = json.dumps(
            {"prompt": first_prompt, "api_key": "test-secret-key"}
        ).encode("utf-8")
        second_body = json.dumps(
            {"prompt": second_prompt, "api_key": "test-secret-key"}
        ).encode("utf-8")

        first_status, _, first_response = self.request(
            "POST", "/api/ask", body=first_body, headers=headers
        )
        second_status, _, second_response = self.request(
            "POST", "/api/ask", body=second_body, headers=headers
        )
        self.assertEqual(first_status, 200)
        self.assertEqual(second_status, 200)
        self.assertEqual(json.loads(first_response)["context_sequence"], 1)
        self.assertEqual(json.loads(second_response)["context_sequence"], 2)
        second_messages = json.dumps(self.reasoner_calls[-1])
        self.assertIn(first_prompt, second_messages)
        self.assertIn("Bounded GUI reply.", second_messages)
        self.assertIn(second_prompt, second_messages)

        written = "\n".join(
            path.read_text(encoding="utf-8")
            for path in self.root.rglob("*")
            if path.is_file()
        )
        self.assertNotIn(first_prompt, written)
        self.assertNotIn(second_prompt, written)
        self.assertNotIn("test-secret-key", written)

        self._stop_server()
        self._start_server()
        status, _, status_body = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(status_body)["context"]["semantic_context_lost"])

        restart_headers = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{self.port}",
            "X-Aurum-CSRF": self.server.csrf_token,
        }
        conflict, _, conflict_body = self.request(
            "POST", "/api/ask", body=second_body, headers=restart_headers
        )
        self.assertEqual(conflict, 409)
        conflict_payload = json.loads(conflict_body)
        self.assertTrue(conflict_payload["retry_starts_new_context"])
        self.assertEqual(conflict_payload["lost_sequence"], 2)

        retry, _, retry_body = self.request(
            "POST", "/api/ask", body=second_body, headers=restart_headers
        )
        self.assertEqual(retry, 200)
        self.assertEqual(json.loads(retry_body)["context_sequence"], 1)

    def test_preferences_are_revisioned_reversible_and_content_free(self) -> None:
        headers = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{self.port}",
            "X-Aurum-CSRF": self.server.csrf_token,
        }
        apply_body = json.dumps(
            {
                "expected_revision": 0,
                "safe_layout": True,
                "adaptation_locked": True,
            }
        ).encode("utf-8")
        applied_status, _, applied_body = self.request(
            "POST", "/api/preferences", body=apply_body, headers=headers
        )

        self.assertEqual(applied_status, 200)
        applied = json.loads(applied_body)
        self.assertEqual(applied["preferences"]["revision"], 1)
        self.assertTrue(applied["preferences"]["safe_layout"])
        self.assertTrue(applied["preferences"]["adaptation_locked"])
        self.assertFalse(applied["user_content_captured"])
        self.assertFalse(applied["host_actuation"])
        self.assertTrue(applied["rollback_available"])

        stale_status, _, _ = self.request(
            "POST", "/api/preferences", body=apply_body, headers=headers
        )
        self.assertEqual(stale_status, 409)

        rollback_body = json.dumps(
            {
                "expected_revision": 1,
                "safe_layout": False,
                "adaptation_locked": False,
            }
        ).encode("utf-8")
        rollback_status, _, response_body = self.request(
            "POST", "/api/preferences", body=rollback_body, headers=headers
        )
        self.assertEqual(rollback_status, 200)
        restored = json.loads(response_body)["preferences"]
        self.assertEqual(restored["revision"], 2)
        self.assertFalse(restored["safe_layout"])
        self.assertFalse(restored["adaptation_locked"])

        status, _, body = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        proof = json.loads(body)
        self.assertEqual(proof["proof_view"]["preference_evidence_count"], 2)
        self.assertFalse(proof["proof_view"]["user_content_returned"])

    def test_non_loopback_bind_and_host_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "loopback"):
            aurum_gui_context.create_server("0.0.0.0", 8765, self.root)

        status, _, _ = self.request(
            "GET",
            "/api/status",
            headers={"Host": "example.invalid"},
        )
        self.assertEqual(status, 400)

    def test_occupied_port_preserves_the_bind_error(self) -> None:
        with self.assertRaises(OSError) as raised:
            aurum_gui_context.create_server(
                "127.0.0.1",
                self.port,
                self.root,
                reasoner=self.reasoner,
            )
        self.assertEqual(raised.exception.errno, errno.EADDRINUSE)

        status, _, _ = self.request("GET", "/api/status")
        self.assertEqual(status, 200)

if __name__ == "__main__":
    unittest.main()
