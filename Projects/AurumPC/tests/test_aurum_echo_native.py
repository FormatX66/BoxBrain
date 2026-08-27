from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "aurum_echo_native.py"
SPEC = importlib.util.spec_from_file_location("aurum_echo_native", MODULE_PATH)
assert SPEC and SPEC.loader
echo_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = echo_module
SPEC.loader.exec_module(echo_module)


class EchoPhysicalProofTests(unittest.TestCase):
    def _json_side_effect(self, path: Path):
        path = Path(path)
        if path == Path("/etc/aurum-installed.json"):
            return {
                "target": {
                    "serial": echo_module.EXPECTED_SERIAL,
                    "size_bytes": echo_module.EXPECTED_SIZE_BYTES,
                }
            }
        if path.name == "machine-identity.json":
            return {"status": "named", "display_name": "Hopper", "hostname": "hopper"}
        if path.name == "hopper-display.json":
            return {
                "authorized": True,
                "status": "running",
                "machine": "Hopper",
                "mode": "kmsdrm-vt2",
                "physical_display": True,
            }
        return {}

    def test_ready_requires_exact_machine_display_game_and_both_input_paths(self) -> None:
        live = {
            "status": "running",
            "machine": "Hopper",
            "game": "Echo Rally",
            "fullscreen": True,
            "video_driver": "kmsdrm",
            "physical_resolution": [1920, 1080],
            "started_at": "2026-08-20T01:00:00Z",
            "frames_presented": 120,
            "pointer_motion": {
                "event_count": 2,
                "last_at": "2026-08-27T10:30:00Z",
                "position": [640, 360],
                "delta": [4, -2],
            },
        }
        with (
            patch.object(echo_module, "_json_file", side_effect=self._json_side_effect),
            patch.object(echo_module, "_cmdline", return_value="python3 /opt/aurum/aurum_echo_native.py"),
            patch.object(
                echo_module,
                "_input_proof",
                return_value={
                    "mode": "kmsdrm-vt2",
                    "keyboard_device_count": 1,
                    "pointer_device_count": 1,
                    "keyboard_path_available": True,
                    "pointer_path_available": True,
                    "keyboard_open_nodes": ["/dev/input/event1"],
                    "pointer_open_nodes": ["/dev/input/event2"],
                    "game_open_input_node_count": 2,
                    "x_server_pids": [],
                    "x_open_input_node_count": 0,
                },
            ),
        ):
            proof = echo_module._proof_payload(Path("/state"), live)
        self.assertTrue(proof["ready"])
        self.assertTrue(proof["machine"]["authorized_exact_hopper"])
        self.assertTrue(proof["display"]["physical_display"])
        self.assertEqual(proof["echo"]["video_driver"], "kmsdrm")
        self.assertEqual(proof["echo"]["physical_resolution"], [1920, 1080])

    def test_ready_is_false_when_pointer_path_is_open_but_motion_is_unobserved(self) -> None:
        live = {
            "status": "running",
            "machine": "Hopper",
            "game": "Echo Rally",
            "fullscreen": True,
            "video_driver": "kmsdrm",
            "physical_resolution": [1920, 1080],
            "frames_presented": 10,
        }
        with (
            patch.object(echo_module, "_json_file", side_effect=self._json_side_effect),
            patch.object(echo_module, "_cmdline", return_value="python3 /opt/aurum/aurum_echo_native.py"),
            patch.object(
                echo_module,
                "_input_proof",
                return_value={
                    "mode": "kmsdrm-vt2",
                    "keyboard_device_count": 1,
                    "pointer_device_count": 1,
                    "keyboard_path_available": True,
                    "pointer_path_available": True,
                    "keyboard_open_nodes": ["/dev/input/event1"],
                    "pointer_open_nodes": ["/dev/input/event2"],
                    "game_open_input_node_count": 2,
                    "x_server_pids": [],
                    "x_open_input_node_count": 0,
                },
            ),
        ):
            proof = echo_module._proof_payload(Path("/state"), live)
        self.assertFalse(proof["ready"])
        self.assertTrue(proof["input"]["pointer_path_available"])
        self.assertFalse(proof["input"]["pointer_motion"]["motion_observed"])
        self.assertFalse(proof["input"]["pointer_motion"]["ready"])

    def test_ready_is_false_when_pointer_path_is_not_open(self) -> None:
        live = {
            "status": "running",
            "machine": "Hopper",
            "game": "Echo Rally",
            "fullscreen": True,
            "video_driver": "x11",
            "physical_resolution": [1920, 1080],
            "frames_presented": 10,
        }
        with (
            patch.object(echo_module, "_json_file", side_effect=self._json_side_effect),
            patch.object(echo_module, "_cmdline", return_value="python3 /opt/aurum/aurum_echo_native.py"),
            patch.object(
                echo_module,
                "_input_proof",
                return_value={
                    "mode": "x11-vt2",
                    "keyboard_device_count": 1,
                    "pointer_device_count": 1,
                    "keyboard_path_available": True,
                    "pointer_path_available": False,
                    "keyboard_open_nodes": ["/dev/input/event1"],
                    "pointer_open_nodes": [],
                    "game_open_input_node_count": 0,
                    "x_server_pids": [321],
                    "x_open_input_node_count": 1,
                },
            ),
        ):
            proof = echo_module._proof_payload(Path("/state"), live)
        self.assertFalse(proof["ready"])


if __name__ == "__main__":
    unittest.main()
