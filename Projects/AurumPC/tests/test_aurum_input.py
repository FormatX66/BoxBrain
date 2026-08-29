from __future__ import annotations

import concurrent.futures
import tempfile
import unittest
from pathlib import Path

from Projects.AurumPC.aurum_input import (
    apply_pointer_wake_policy,
    classify_device,
    gui_event_proof,
    input_devices,
    parse_libinput_devices,
    record_gui_event,
)
from unittest.mock import patch


class AurumInputTests(unittest.TestCase):
    def test_pointer_classification_covers_hopper_input_paths(self) -> None:
        self.assertEqual(classify_device("ELAN ClickPad", rel=(), abs_axes=(1,)), "touchpad")
        self.assertEqual(classify_device("USB Optical Mouse", rel=(1,), abs_axes=()), "mouse")
        self.assertEqual(classify_device("Generic HID", rel=(3,), abs_axes=()), "relative-pointer")
        self.assertEqual(classify_device("Generic HID", rel=(), abs_axes=(3,)), "absolute-pointer")
        self.assertEqual(
            classify_device(
                "AT Translated Set 2 keyboard",
                rel=(),
                abs_axes=(),
                key_bits=(1, 2, 3),
            ),
            "keyboard",
        )

    def test_libinput_parser_binds_capabilities_to_exact_event_node(self) -> None:
        parsed = parse_libinput_devices(
            """Device:           SynPS/2 Synaptics TouchPad
Kernel:           /dev/input/event4
Group:            7
Seat:             seat0, default
Capabilities:     pointer gesture

Device:           AT Translated Set 2 keyboard
Kernel:           /dev/input/event1
Group:            6
Seat:             seat0, default
Capabilities:     keyboard
"""
        )
        self.assertEqual(parsed["/dev/input/event4"]["name"], "SynPS/2 Synaptics TouchPad")
        self.assertEqual(parsed["/dev/input/event4"]["capabilities"], ["pointer", "gesture"])
        self.assertEqual(parsed["/dev/input/event1"]["capabilities"], ["keyboard"])

    def test_wake_policy_changes_only_nearest_pointer_power_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sys_input = root / "sys" / "class" / "input"
            dev_input = root / "dev" / "input"
            device = sys_input / "event0" / "device"
            (device / "capabilities").mkdir(parents=True)
            dev_input.mkdir(parents=True)
            (dev_input / "event0").write_bytes(b"")
            (device / "name").write_text("ELAN Touchpad\n", encoding="utf-8")
            (device / "capabilities" / "rel").write_text("0\n", encoding="utf-8")
            (device / "capabilities" / "abs").write_text("3\n", encoding="utf-8")
            (device / "power").mkdir()
            (device / "power" / "control").write_text("auto\n", encoding="ascii")
            (device / "power" / "wakeup").write_text("disabled\n", encoding="ascii")
            driver_target = root / "drivers" / "psmouse"
            driver_target.mkdir(parents=True)
            (device / "driver").symlink_to(driver_target, target_is_directory=True)
            (sys_input / "power").mkdir()
            (sys_input / "power" / "control").write_text("auto\n", encoding="ascii")

            devices = input_devices(sys_input=sys_input, dev_input=dev_input)
            result = apply_pointer_wake_policy(devices)

            self.assertEqual(devices[0]["kernel_driver"], "psmouse")
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["managed_pointer_count"], 1)
            self.assertEqual((device / "power" / "control").read_text(encoding="ascii").strip(), "on")
            self.assertEqual((device / "power" / "wakeup").read_text(encoding="ascii").strip(), "enabled")
            self.assertEqual((sys_input / "power" / "control").read_text(encoding="ascii").strip(), "auto")

    def test_gui_input_proof_requires_keyboard_and_pointer_on_current_boot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch(
            "Projects.AurumPC.aurum_input._boot_id", return_value="boot-1"
        ):
            state = Path(temporary)
            first = record_gui_event("keyboard", state_dir=state)
            self.assertFalse(first["ready"])
            complete = record_gui_event("pointer", state_dir=state)
            self.assertTrue(complete["ready"])
            self.assertEqual(complete["keyboard"]["event_count"], 1)
            self.assertEqual(complete["pointer"]["event_count"], 1)
            self.assertTrue(gui_event_proof(state_dir=state)["same_boot"])

        with tempfile.TemporaryDirectory() as temporary, patch(
            "Projects.AurumPC.aurum_input._boot_id", return_value="boot-2"
        ):
            state = Path(temporary)
            (state / "gui-input-proof.json").write_text(
                '{"schema":"aurum.gui-input-proof.v1","boot_id":"old","keyboard":{"event_count":1,"last_at":"now"},"pointer":{"event_count":1,"last_at":"now"}}',
                encoding="utf-8",
            )
            self.assertFalse(gui_event_proof(state_dir=state)["ready"])

    def test_concurrent_gui_events_preserve_both_proof_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch(
            "Projects.AurumPC.aurum_input._boot_id", return_value="boot-race"
        ):
            state = Path(temporary)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                results = list(
                    executor.map(
                        lambda kind: record_gui_event(kind, state_dir=state),
                        ("keyboard", "pointer"),
                    )
                )

            self.assertEqual(len(results), 2)
            proof = gui_event_proof(state_dir=state)
            self.assertTrue(proof["ready"])
            self.assertEqual(proof["keyboard"]["event_count"], 1)
            self.assertEqual(proof["pointer"]["event_count"], 1)


if __name__ == "__main__":
    unittest.main()
