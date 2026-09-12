from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "aurum_web_surface.py"
SPEC = importlib.util.spec_from_file_location("aurum_web_surface_test", MODULE_PATH)
assert SPEC and SPEC.loader
surface = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = surface
SPEC.loader.exec_module(surface)


class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class AurumWebSurfaceTests(unittest.TestCase):
    def test_boot_readiness_uses_lightweight_health_endpoint(self) -> None:
        with patch.object(surface.urllib.request, "urlopen", return_value=Response()) as urlopen:
            self.assertTrue(surface._server_ready("http://127.0.0.1:8765/"))

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8765/api/health")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 3)

    def test_boot_readiness_fails_closed_on_probe_error(self) -> None:
        with patch.object(surface.urllib.request, "urlopen", side_effect=OSError("fixture")):
            self.assertFalse(surface._server_ready("http://127.0.0.1:8765/"))


if __name__ == "__main__":
    unittest.main()
