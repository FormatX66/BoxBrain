from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import urlparse


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boxbrain.operator_console import OperatorConsole  # noqa: E402


JOB_ID = "abcdef0123456789"


def assessment_report() -> dict[str, object]:
    return {
        "job": {
            "id": JOB_ID,
            "target": "192.168.0.10",
            "profile": "discovery",
            "status": "completed",
            "created_at": "2026-08-10T00:00:00Z",
            "started_at": "2026-08-10T00:00:01Z",
            "finished_at": "2026-08-10T00:00:02Z",
        },
        "assets": [
            {
                "ip_address": "192.168.0.10",
                "hostname": "test-host",
                "vendor": "Example",
                "state": "up",
            }
        ],
        "services": [
            {
                "ip_address": "192.168.0.10",
                "port": 22,
                "protocol": "tcp",
                "name": "ssh",
                "product": "OpenSSH",
                "version": "9",
            }
        ],
        "findings": [],
        "events": [{"created_at": "2026-08-10T00:00:01Z", "message": "Scan started"}],
    }


class _Storage:
    def __init__(self) -> None:
        self.requested_job_id: str | None = None

    def build_report(self, job_id: str) -> dict[str, object]:
        self.requested_job_id = job_id
        if job_id != JOB_ID:
            raise KeyError(job_id)
        return assessment_report()


class _Handler:
    def __init__(self) -> None:
        self.body = b""
        self.content_type = ""
        self.status = 0

    def _send(
        self,
        body: bytes,
        content_type: str,
        status: int = 200,
        **_headers: object,
    ) -> None:
        self.body = body
        self.content_type = content_type
        self.status = status


class OperatorConsoleAssessmentTests(unittest.TestCase):
    def test_completed_job_links_to_preserved_results_page(self) -> None:
        row = OperatorConsole._job_row(
            {
                "id": JOB_ID,
                "target": "192.168.0.10",
                "profile": "discovery",
                "status": "completed",
                "created_at": "2026-08-10T00:00:00Z",
            }
        )

        self.assertIn(f'href="/assessments/{JOB_ID}"', row)
        self.assertIn("View results", row)

    def test_running_job_does_not_offer_incomplete_results(self) -> None:
        row = OperatorConsole._job_row(
            {"id": JOB_ID, "target": "192.168.0.10", "status": "running"}
        )

        self.assertNotIn("View results", row)

    def test_assessment_routes_return_html_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as state_directory:
            storage = _Storage()
            console = OperatorConsole(state_directory, storage=storage)

            json_handler = _Handler()
            handled = console.handle_get(
                json_handler,
                urlparse(f"/api/v1/operator/assessments/{JOB_ID.upper()}"),
                lambda: {},
            )

            self.assertTrue(handled)
            self.assertEqual(json_handler.status, 200)
            self.assertEqual(json_handler.content_type, "application/json; charset=utf-8")
            self.assertEqual(json.loads(json_handler.body)["job"]["id"], JOB_ID)
            self.assertEqual(storage.requested_job_id, JOB_ID)

            html_handler = _Handler()
            handled = console.handle_get(
                html_handler,
                urlparse(f"/assessments/{JOB_ID}"),
                lambda: {},
            )

            self.assertTrue(handled)
            self.assertEqual(html_handler.status, 200)
            page = html_handler.body.decode("utf-8")
            self.assertIn("Port scan results", page)
            self.assertIn("192.168.0.10", page)
            self.assertIn(f"/api/v1/operator/assessments/{JOB_ID}", page)


if __name__ == "__main__":
    unittest.main()
