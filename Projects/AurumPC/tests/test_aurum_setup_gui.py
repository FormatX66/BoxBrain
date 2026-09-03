from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MODULE_PATH = Path(os.environ.get("AURUM_SETUP_UNDER_TEST", str(ROOT / "aurum_setup_gui.py")))
if str(MODULE_PATH.parent) not in sys.path:
    sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("aurum_setup_gui_test", MODULE_PATH)
assert SPEC and SPEC.loader
setup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = setup
SPEC.loader.exec_module(setup)


class SetupGuiContractTests(unittest.TestCase):
    def test_drive_label_contains_only_human_readable_identity(self) -> None:
        label = setup._drive_label(
            {"model": "Internal NVMe", "size_gib": 476.8, "target_id": "drive-secret"}
        )
        self.assertEqual(label, "Internal NVMe  ·  476.8 GiB")
        self.assertNotIn("drive-secret", label)

    def test_raw_errors_are_replaced_with_safe_graphical_guidance(self) -> None:
        message = setup._friendly_reason("OSError: [Errno 98] Address already in use")
        self.assertNotIn("Errno", message)
        self.assertIn("Setup", message)


class SetupInputTests(unittest.TestCase):
    def setUp(self) -> None:
        keys = [
            "K_TAB", "K_ESCAPE", "K_BACKSPACE", "K_RETURN", "K_KP_ENTER",
            "K_SPACE", "K_UP", "K_DOWN", "K_LEFT", "K_RIGHT", "KMOD_SHIFT",
            "KEYDOWN", "MOUSEBUTTONUP", "QUIT",
        ]
        self.pg = SimpleNamespace(**{key: index + 1 for index, key in enumerate(keys)})
        self.gui = setup.AurumSetupGui.__new__(setup.AurumSetupGui)
        self.gui.pg = self.pg
        self.gui.view = "setup"
        self.gui.focus_key = None
        self.gui.password_focus = False
        self.gui.password = ""
        self.gui.running = True
        self.gui.buttons = []

    def control(self, key: str, *, enabled: bool = True, action: object = None) -> object:
        rect = SimpleNamespace(collidepoint=lambda point: point == key)
        control = setup.SetupControl(key, rect, action or Mock(), enabled)
        self.gui.buttons.append(control)
        return control

    def press(self, key: str, **kwargs: object) -> bool:
        event = SimpleNamespace(type=self.pg.KEYDOWN, key=getattr(self.pg, key), unicode="", mod=0, repeat=False)
        event.__dict__.update(kwargs)
        return self.gui._key_event(event)

    def test_tab_and_shift_tab_skip_disabled_controls_and_wrap(self) -> None:
        self.control("drive")
        self.control("repair", enabled=False)
        self.control("install")
        self.gui._sync_focus()
        self.assertEqual(self.gui.focus_key, "drive")
        self.press("K_TAB")
        self.assertEqual(self.gui.focus_key, "install")
        self.press("K_TAB")
        self.assertEqual(self.gui.focus_key, "drive")
        self.press("K_TAB", mod=self.pg.KMOD_SHIFT)
        self.assertEqual(self.gui.focus_key, "install")

    def test_arrows_move_focus_without_selecting_a_drive(self) -> None:
        first = self.control("first")
        second = self.control("second")
        self.gui._sync_focus()
        self.press("K_DOWN")
        self.assertEqual(self.gui.focus_key, "second")
        first.action.assert_not_called()
        second.action.assert_not_called()
        self.press("K_LEFT")
        self.assertEqual(self.gui.focus_key, "first")
        self.press("K_RIGHT")
        self.press("K_UP")
        self.assertEqual(self.gui.focus_key, "first")

    def test_enter_keypad_enter_and_space_activate_only_focused_control(self) -> None:
        first = self.control("first")
        second = self.control("second")
        self.gui._focus("second")
        for key in ("K_RETURN", "K_KP_ENTER", "K_SPACE"):
            self.assertTrue(self.press(key))
        self.assertEqual(second.action.call_count, 3)
        first.action.assert_not_called()

    def test_held_activation_keys_and_disabled_controls_cannot_execute(self) -> None:
        action = self.control("erase")
        self.gui._focus("erase")
        for key in ("K_RETURN", "K_KP_ENTER", "K_SPACE"):
            self.press(key, repeat=True)
        action.action.assert_not_called()
        action.enabled = False
        self.press("K_RETURN")
        action.action.assert_not_called()

    def test_missing_or_removed_controls_have_safe_focus(self) -> None:
        self.gui._focus("removed")
        self.gui._sync_focus()
        self.assertIsNone(self.gui.focus_key)
        self.press("K_TAB")
        self.press("K_RETURN")
        self.control("Back")
        self.control("Erase")
        self.gui._sync_focus()
        self.assertEqual(self.gui.focus_key, "Back")

    def test_wifi_selection_focuses_typing_and_tab_leaves_password(self) -> None:
        self.gui.view = "wifi"
        self.control("wifi:Network")
        self.control("wifi-password")
        connect = self.control("Connect")
        self.gui._select_ssid("Network")
        self.assertEqual(self.gui.focus_key, "wifi-password")
        self.assertTrue(self.gui.password_focus)
        self.press("K_TAB")
        self.assertFalse(self.gui.password_focus)
        self.press("K_RETURN")
        connect.action.assert_called_once()

    def test_password_typing_space_backspace_and_enter(self) -> None:
        self.gui.view = "wifi"
        self.gui._focus("wifi-password")
        self.gui._connect = Mock()
        self.press("K_SPACE", unicode=" ")
        self.press("K_RIGHT", unicode="a")
        self.assertEqual(self.gui.password, " a")
        self.press("K_BACKSPACE")
        self.assertEqual(self.gui.password, " ")
        self.press("K_RETURN", repeat=True)
        self.gui._connect.assert_not_called()
        self.press("K_RETURN")
        self.gui._connect.assert_called_once()

    def test_escape_works_while_password_field_has_focus(self) -> None:
        self.gui.view = "wifi"
        self.gui.password = "private"
        self.gui._focus("wifi-password")
        self.assertTrue(self.press("K_ESCAPE"))
        self.assertEqual(self.gui.view, "setup")
        self.assertEqual(self.gui.password, "")
        self.assertFalse(self.gui.password_focus)

    def test_confirmation_starts_on_back_not_erase(self) -> None:
        self.gui.operation = "install"
        self.gui.screen = SimpleNamespace(get_height=lambda: 768)
        self.pg.Rect = lambda *args: args
        self.pg.draw = SimpleNamespace(rect=Mock())
        self.gui._header = lambda *args: (48, 190, 1024, 500)
        self.gui._selected = lambda: {"model": "Test", "size_gib": 128}
        self.gui._put = Mock()
        self.gui._wrap = Mock()
        self.gui._button = lambda label, rect, action, **kwargs: self.control(label, action=action)
        self.gui._begin = Mock()
        self.gui._focus("Erase & Install Fresh")
        self.gui._set_view("confirm")
        self.gui._render_confirm()
        self.gui._sync_focus()
        self.assertEqual(self.gui.focus_key, "Back")
        self.press("K_RETURN")
        self.assertEqual(self.gui.view, "setup")
        self.gui._begin.assert_not_called()

    def test_keyboard_batch_cannot_reactivate_previous_page_controls(self) -> None:
        action = Mock(side_effect=lambda: self.gui._set_view("confirm"))
        self.control("Install", action=action)
        self.gui._focus("Install")
        event = SimpleNamespace(type=self.pg.KEYDOWN, key=self.pg.K_RETURN, unicode="", mod=0, repeat=False)
        self.pg.event = SimpleNamespace(get=lambda: [event, event])
        self.gui._events()
        action.assert_called_once()
        self.assertEqual(self.gui.view, "confirm")
        self.assertIsNone(self.gui.focus_key)

    def test_trackpad_style_primary_click_uses_same_action_as_keyboard(self) -> None:
        first = self.control("first")
        second = self.control("second")
        event = SimpleNamespace(type=self.pg.MOUSEBUTTONUP, button=1, pos="second")
        self.pg.event = SimpleNamespace(get=lambda: [event])
        self.gui._events()
        self.assertEqual(self.gui.focus_key, "second")
        second.action.assert_called_once()
        first.action.assert_not_called()

    def test_double_click_cannot_activate_controls_from_previous_page(self) -> None:
        action = Mock(side_effect=lambda: self.gui._set_view("confirm"))
        self.control("Install", action=action)
        event = SimpleNamespace(type=self.pg.MOUSEBUTTONUP, button=1, pos="Install")
        self.pg.event = SimpleNamespace(get=lambda: [event, event])
        self.gui._events()
        action.assert_called_once()

    def test_live_setup_orders_input_bootstrap_and_bundles_libinput(self) -> None:
        service = (ROOT / "runtime-assets/etc/systemd/system/aurum-setup.service").read_text(encoding="utf-8")
        self.assertTrue(any(line.startswith("After=") and "aurum-input-bootstrap.service" in line for line in service.splitlines()))
        bootstrap = (ROOT / "runtime-assets/etc/systemd/system/aurum-input-bootstrap.service").read_text(encoding="utf-8")
        for module in ("i2c_hid_acpi", "hid_multitouch", "psmouse", "usbhid", "hid_generic", "atkbd"):
            self.assertIn(f"modprobe {module}", bootstrap)
        build = (ROOT / "build-iso.sh").read_text(encoding="utf-8")
        self.assertIn("xserver-xorg-input-libinput", build)
        config = (ROOT / "runtime-assets/etc/X11/xorg.conf.d/40-aurum-libinput.conf").read_text(encoding="utf-8")
        self.assertIn('MatchIsKeyboard "on"', config)
        self.assertIn('MatchIsTouchpad "on"', config)
        self.assertIn('Option "Tapping" "on"', config)


class SetupPygameEventTests(unittest.TestCase):
    """Real SDL event/render checks, using a fake installer and no host I/O."""

    @classmethod
    def setUpClass(cls) -> None:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
        os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
        try:
            import pygame
        except ImportError:
            raise unittest.SkipTest("pygame unavailable; the image pipeline requires these tests")
        cls.pg = pygame
        cls.pg.init()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.pg.quit()

    def setUp(self) -> None:
        self.coordinator = Mock()
        self.coordinator.status.return_value = {
            "status": "ready",
            "targets": [{"target_id": "safe-drive", "model": "Test internal drive", "size_gib": 128, "repair_available": True}],
        }
        with patch.object(setup.AurumSetupGui, "_submit_network"):
            self.gui = setup.AurumSetupGui(self.pg, self.coordinator)
        self.gui.screen = self.pg.display.set_mode((1366, 768), 0)
        self.pg.event.clear()
        self.gui._render()

    def tearDown(self) -> None:
        self.gui.executor.shutdown(wait=True, cancel_futures=True)

    def send_key(self, key: int, *, unicode: str = "", mod: int = 0, repeat: bool = False) -> None:
        self.pg.event.post(self.pg.event.Event(self.pg.KEYDOWN, key=key, unicode=unicode, mod=mod, repeat=repeat))
        self.gui._events()
        self.gui._render()

    def focus(self, key: str) -> None:
        for _ in range(len(self.gui.buttons) + 1):
            if self.gui.focus_key == key:
                return
            self.send_key(self.pg.K_TAB)
        self.fail(f"Keyboard cannot reach {key}")

    def test_keyboard_can_reach_confirmation_and_back_without_installing(self) -> None:
        self.focus("Erase & Install Fresh")
        self.send_key(self.pg.K_RETURN)
        self.assertEqual(self.gui.view, "confirm")
        self.assertEqual(self.gui.focus_key, "Back")
        self.send_key(self.pg.K_RETURN)
        self.assertEqual(self.gui.view, "setup")
        self.coordinator.start.assert_not_called()

    def test_explicit_keyboard_confirmation_calls_fake_installer_once(self) -> None:
        self.focus("Erase & Install Fresh")
        self.send_key(self.pg.K_SPACE)
        self.focus("Erase Drive & Install")
        self.send_key(self.pg.K_RETURN)
        self.coordinator.start.assert_called_once_with(confirmed=True, target_id="safe-drive", operation="install")

    def test_real_pointer_events_reach_repair_and_escape_returns(self) -> None:
        control = next(control for control in self.gui.buttons if control.key == "Repair Aurum")
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEMOTION, pos=control.rect.center, rel=(10, 10), buttons=(0, 0, 0)))
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONUP, pos=control.rect.center, button=1))
        self.gui._events()
        self.gui._render()
        self.assertEqual(self.gui.view, "confirm")
        self.assertEqual(self.gui.operation, "repair")
        self.send_key(self.pg.K_ESCAPE)
        self.assertEqual(self.gui.view, "setup")
        self.coordinator.start.assert_not_called()

    def test_keyboard_can_select_network_type_and_leave_wifi(self) -> None:
        with patch.object(self.gui, "_submit_network"):
            self.focus("Connect Wi-Fi")
            self.send_key(self.pg.K_RETURN)
        self.gui.ssids = ["Test network"]
        self.gui._render()
        self.focus("wifi:Test network")
        self.send_key(self.pg.K_RETURN)
        self.assertEqual(self.gui.focus_key, "wifi-password")
        self.send_key(self.pg.K_a, unicode="a")
        self.send_key(self.pg.K_SPACE, unicode=" ")
        self.send_key(self.pg.K_b, unicode="b")
        self.assertEqual(self.gui.password, "a b")
        self.send_key(self.pg.K_TAB)
        self.assertFalse(self.gui.password_focus)
        self.send_key(self.pg.K_ESCAPE)
        self.assertEqual(self.gui.view, "setup")
        self.assertEqual(self.gui.password, "")
        self.coordinator.start.assert_not_called()

    def test_controls_do_not_overlap_or_leave_fallback_displays(self) -> None:
        self.gui.status = {"status": "ready", "targets": [
            {"target_id": f"drive-{index}", "model": f"Test drive {index}", "size_gib": 128, "repair_available": True}
            for index in range(5)
        ]}
        self.gui.selected_target_id = "drive-0"
        self.gui.ssids = [f"Test network {index}" for index in range(10)]
        for size in ((800, 600), (1024, 768), (1366, 768), (1920, 1080)):
            # An explicit surface avoids the host display's fullscreen coercion.
            self.gui.screen = self.pg.Surface(size)
            for view in ("setup", "wifi", "confirm"):
                with self.subTest(size=size, view=view):
                    self.gui._set_view(view)
                    self.gui._render()
                    for index, control in enumerate(self.gui.buttons):
                        self.assertTrue(self.gui.screen.get_rect().contains(control.rect), control.key)
                        self.assertLessEqual(control.rect.bottom, size[1] - 36, control.key)
                        for other in self.gui.buttons[index + 1:]:
                            self.assertFalse(control.rect.colliderect(other.rect), f"{control.key} overlaps {other.key}")
        self.coordinator.start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
