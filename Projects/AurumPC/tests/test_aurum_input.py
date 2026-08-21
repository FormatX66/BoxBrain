from __future__ import annotations

import unittest

from Projects.AurumPC.aurum_input import classify_device


class AurumInputTests(unittest.TestCase):
    def test_touchpad_name_wins(self) -> None:
        self.assertEqual(
            classify_device("ELAN Touchpad", rel=(), abs_axes=(1,)),
            "touchpad",
        )

    def test_mouse_name_wins(self) -> None:
        self.assertEqual(
            classify_device("USB Optical Mouse", rel=(1,), abs_axes=()),
            "mouse",
        )

    def test_relative_pointer_is_detected_from_capabilities(self) -> None:
        self.assertEqual(
            classify_device("Generic HID", rel=(3,), abs_axes=()),
            "relative-pointer",
        )

    def test_absolute_pointer_is_detected_from_capabilities(self) -> None:
        self.assertEqual(
            classify_device("Generic HID", rel=(), abs_axes=(3,)),
            "absolute-pointer",
        )


if __name__ == "__main__":
    unittest.main()
