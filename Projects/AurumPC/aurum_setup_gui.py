#!/usr/bin/env python3
"""Dedicated native graphical setup for the Aurum live USB.

This surface intentionally has no dependency on the installed Hopper receipt,
the Hopper dashboard, a browser, or a TCP port.  It is available only while
booted from Aurum live media.  Device paths and destructive confirmation codes
remain private to InstallCoordinator.
"""
from __future__ import annotations

import concurrent.futures
import os
from pathlib import Path
import time
from typing import Any, Callable

from aurum_install_flow import InstallCoordinator, InstallError
from aurum_network import connect_wifi, network_status, scan_networks


LIVE_MEDIUM = Path("/run/live/medium")
BG = (8, 12, 18)
PANEL = (18, 25, 34)
PANEL_SELECTED = (33, 48, 61)
TEXT = (238, 242, 246)
MUTED = (155, 169, 181)
GOLD = (244, 188, 63)
GREEN = (73, 204, 135)
RED = (239, 91, 91)
BLUE = (71, 156, 224)


def _friendly_reason(value: object) -> str:
    reason = str(value or "")
    known = {
        "no-unmounted-internal-disk-found": "No safe internal drive is available.",
        "installer-runs-only-from-aurum-live-media": "Setup is available only from the Aurum USB.",
        "installer-interface-restarted": "Setup restarted. It is safe to choose the operation again.",
        "no-wifi-interface": "No Wi-Fi adapter was found. Ethernet can still be used.",
        "credentials-required": "Choose a Wi-Fi network and enter its password.",
        "wifi-connected-no-internet": "Wi-Fi connected, but the internet is not reachable yet.",
        "association-start-failed": "The Wi-Fi adapter could not join that network.",
        "scan-failed": "Wi-Fi scanning failed. Try again or use Ethernet.",
    }
    if reason in known:
        return known[reason]
    if "verification" in reason.lower():
        return "Verification did not complete. No automatic retry will run."
    if "filesystem" in reason.lower():
        return "The existing Aurum filesystem could not be repaired safely."
    return "Setup could not complete safely. You can go back and try again."


def _drive_label(target: dict[str, Any]) -> str:
    model = str(target.get("model") or "Internal drive")
    size = target.get("size_gib")
    return f"{model}  ·  {size} GiB" if isinstance(size, (int, float)) else model


class AurumSetupGui:
    def __init__(self, pygame_module: Any, coordinator: InstallCoordinator | None = None) -> None:
        self.pg = pygame_module
        self.coordinator = coordinator or InstallCoordinator()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.screen = self.pg.display.set_mode((0, 0), self.pg.FULLSCREEN)
        self.pg.display.set_caption("Aurum Setup")
        self.pg.mouse.set_visible(True)
        self.clock = self.pg.time.Clock()
        self.view = "setup"
        self.running = True
        self.operation = "install"
        self.selected_target_id: str | None = None
        self.password = ""
        self.password_focus = False
        self.wifi_interface: str | None = None
        self.ssids: list[str] = []
        self.selected_ssid = ""
        self.network_message = "Checking connection…"
        self.network_online = False
        self.network_future: concurrent.futures.Future[dict[str, Any]] | None = None
        self.buttons: list[tuple[Any, Callable[[], None], bool]] = []
        self.last_status_refresh = 0.0
        self.status: dict[str, Any] = {}
        self._refresh_setup()
        self._submit_network(network_status)

    def _font(self, size: int, bold: bool = False) -> Any:
        return self.pg.font.SysFont("DejaVu Sans", size, bold=bold)

    def _text(self, text: str, size: int, color: tuple[int, int, int] = TEXT, bold: bool = False) -> Any:
        return self._font(size, bold).render(text, True, color)

    def _put(self, text: str, x: int, y: int, size: int, color: tuple[int, int, int] = TEXT, bold: bool = False) -> None:
        self.screen.blit(self._text(text, size, color, bold), (x, y))

    def _wrap(self, text: str, x: int, y: int, width: int, size: int, color: tuple[int, int, int] = TEXT) -> int:
        words = text.split()
        line = ""
        line_height = int(size * 1.35)
        for word in words:
            candidate = f"{line} {word}".strip()
            if self._font(size).size(candidate)[0] <= width:
                line = candidate
            else:
                self._put(line, x, y, size, color)
                y += line_height
                line = word
        if line:
            self._put(line, x, y, size, color)
            y += line_height
        return y

    def _button(
        self,
        label: str,
        rect: Any,
        action: Callable[[], None],
        *,
        enabled: bool = True,
        accent: tuple[int, int, int] = BLUE,
    ) -> None:
        color = accent if enabled else (59, 67, 75)
        self.pg.draw.rect(self.screen, color, rect, border_radius=10)
        rendered = self._text(label, 24, (4, 9, 13) if enabled else MUTED, True)
        self.screen.blit(rendered, rendered.get_rect(center=rect.center))
        self.buttons.append((rect, action, enabled))

    def _header(self, title: str, subtitle: str) -> tuple[int, int, int, int]:
        width, height = self.screen.get_size()
        self.screen.fill(BG)
        self._put("AURUM", 48, 32, 30, GOLD, True)
        network = "Internet connected" if self.network_online else "Offline"
        self._put(network, width - 260, 38, 19, GREEN if self.network_online else MUTED, True)
        self._put(title, 48, 92, 42, TEXT, True)
        self._put(subtitle, 50, 147, 21, MUTED)
        return 48, 190, width - 96, height - 230

    def _refresh_setup(self) -> None:
        self.status = self.coordinator.status()
        targets = self.status.get("targets")
        if not isinstance(targets, list):
            target = self.status.get("target")
            targets = [target] if isinstance(target, dict) else []
        ids = [str(item.get("target_id")) for item in targets if isinstance(item, dict)]
        if self.selected_target_id not in ids:
            self.selected_target_id = ids[0] if ids else None
        self.last_status_refresh = time.monotonic()

    def _targets(self) -> list[dict[str, Any]]:
        targets = self.status.get("targets")
        if isinstance(targets, list):
            return [item for item in targets if isinstance(item, dict)]
        target = self.status.get("target")
        return [target] if isinstance(target, dict) else []

    def _selected(self) -> dict[str, Any] | None:
        return next(
            (target for target in self._targets() if target.get("target_id") == self.selected_target_id),
            None,
        )

    def _select(self, target_id: str) -> None:
        self.selected_target_id = target_id

    def _choose_operation(self, operation: str) -> None:
        selected = self._selected()
        if not selected:
            return
        if operation == "repair" and selected.get("repair_available") is not True:
            return
        self.operation = operation
        self.view = "confirm"

    def _begin(self) -> None:
        try:
            self.coordinator.start(
                confirmed=True,
                target_id=self.selected_target_id,
                operation=self.operation,
            )
        except InstallError as exc:
            self.status = {"status": "failed", "reason": str(exc)}
        self.view = "progress"

    def _poweroff(self) -> None:
        try:
            self.coordinator.poweroff()
        except InstallError as exc:
            self.status = {"status": "failed", "reason": str(exc)}
            self.view = "progress"

    def _submit_network(self, function: Callable[..., dict[str, Any]], *args: Any) -> None:
        self.network_future = self.executor.submit(function, *args)

    def _open_wifi(self) -> None:
        self.view = "wifi"
        self.network_message = "Scanning for Wi-Fi networks…"
        self.ssids = []
        self._submit_network(scan_networks)

    def _connect(self) -> None:
        if not self.selected_ssid:
            self.network_message = "Choose a Wi-Fi network first."
            return
        self.password_focus = False
        self.network_message = f"Connecting to {self.selected_ssid}…"
        self._submit_network(connect_wifi, self.selected_ssid, self.password, self.wifi_interface)
        self.password = ""

    def _poll_network(self) -> None:
        future = self.network_future
        if future is None or not future.done():
            return
        self.network_future = None
        try:
            result = future.result()
        except Exception:
            self.network_message = "The network operation did not complete. Try again."
            return
        if isinstance(result.get("ssids"), list):
            self.ssids = [str(value) for value in result["ssids"][:10]]
            self.wifi_interface = str(result.get("interface") or "") or None
            self.network_message = (
                "Choose a network."
                if self.ssids
                else _friendly_reason(result.get("status"))
            )
            return
        self.network_online = bool(result.get("online"))
        if self.network_online:
            self.network_message = "Internet connected. Aurum can sync after installation."
        else:
            self.network_message = _friendly_reason(result.get("status"))

    def _render_setup(self) -> None:
        x, y, width, height = self._header(
            "Install or repair Aurum",
            "Choose an internal drive. The Aurum USB is protected and is never shown here.",
        )
        targets = self._targets()
        if not targets:
            self._put("No safe internal drive found", x, y + 12, 28, RED, True)
            self._wrap(_friendly_reason(self.status.get("reason")), x, y + 60, width, 21, MUTED)
        else:
            card_height = 86
            for index, target in enumerate(targets[:5]):
                top = y + index * (card_height + 12)
                rect = self.pg.Rect(x, top, width, card_height)
                selected = target.get("target_id") == self.selected_target_id
                self.pg.draw.rect(self.screen, PANEL_SELECTED if selected else PANEL, rect, border_radius=12)
                self.pg.draw.rect(self.screen, GOLD if selected else (58, 70, 82), rect, 3 if selected else 1, border_radius=12)
                self._put(_drive_label(target), x + 22, top + 16, 24, TEXT, True)
                note = "Existing Aurum can be repaired" if target.get("repair_available") else (
                    "Contains existing data" if target.get("contains_existing_data") else "Empty drive"
                )
                self._put(note, x + 22, top + 51, 17, GREEN if target.get("repair_available") else MUTED)
                self.buttons.append((rect, lambda value=str(target.get("target_id")): self._select(value), True))

        selected = self._selected()
        bottom = self.screen.get_height() - 100
        self._button("Connect Wi-Fi", self.pg.Rect(x, bottom, 210, 56), self._open_wifi, accent=GREEN)
        self._button(
            "Repair Aurum",
            self.pg.Rect(x + 230, bottom, 210, 56),
            lambda: self._choose_operation("repair"),
            enabled=bool(selected and selected.get("repair_available")),
            accent=GOLD,
        )
        self._button(
            "Erase & Install Fresh",
            self.pg.Rect(x + 460, bottom, 285, 56),
            lambda: self._choose_operation("install"),
            enabled=selected is not None,
            accent=RED,
        )
        self._button("Refresh Drives", self.pg.Rect(x + width - 195, bottom, 195, 56), self._refresh_setup)

    def _render_confirm(self) -> None:
        operation_title = "Repair Aurum" if self.operation == "repair" else "Fresh installation"
        x, y, width, _ = self._header(operation_title, "Review the selected drive before continuing.")
        selected = self._selected() or {}
        self.pg.draw.rect(self.screen, PANEL, self.pg.Rect(x, y, width, 190), border_radius=14)
        self._put(_drive_label(selected), x + 28, y + 28, 28, TEXT, True)
        if self.operation == "install":
            self._put("ALL DATA ON THIS DRIVE WILL BE ERASED", x + 28, y + 82, 25, RED, True)
            self._wrap(
                "The drive will be cleaned, partitioned, and given one verified Aurum boot entry. Other drives and the USB will not be changed.",
                x + 28, y + 125, width - 56, 19, MUTED,
            )
            action = "Erase Drive & Install"
            accent = RED
        else:
            self._put("Your personal files and partitions will not be erased", x + 28, y + 82, 23, GREEN, True)
            self._wrap(
                "Aurum will check its filesystem, refresh its runtime, and rebuild both UEFI and legacy boot paths.",
                x + 28, y + 125, width - 56, 19, MUTED,
            )
            action = "Start Repair"
            accent = GOLD
        bottom = self.screen.get_height() - 105
        self._button("Back", self.pg.Rect(x, bottom, 170, 58), lambda: setattr(self, "view", "setup"))
        self._button(action, self.pg.Rect(x + width - 330, bottom, 330, 58), self._begin, accent=accent)

    def _render_progress(self) -> None:
        self.status = self.coordinator.status() if self.status.get("status") not in {"failed"} else self.status
        state = str(self.status.get("status") or "running")
        complete = state in {"complete", "powering-off"}
        failed = state == "failed"
        title = "Aurum is ready" if complete else ("Setup stopped safely" if failed else "Setting up Aurum")
        subtitle = str(self.status.get("message") or "Please keep the PC connected to power.")
        x, y, width, _ = self._header(title, subtitle)
        progress = int(self.status.get("progress_percent") or 0)
        bar = self.pg.Rect(x, y + 45, width, 34)
        self.pg.draw.rect(self.screen, PANEL, bar, border_radius=10)
        if progress:
            fill = self.pg.Rect(bar.x, bar.y, max(12, int(bar.width * min(progress, 100) / 100)), bar.height)
            self.pg.draw.rect(self.screen, GREEN, fill, border_radius=10)
        phase = str(self.status.get("phase") or "preflight").replace("-", " ").title()
        self._put(f"{progress}%  ·  {phase}", x, y, 23, GREEN if complete else TEXT, True)
        if failed:
            self._wrap(_friendly_reason(self.status.get("reason")), x, y + 120, width, 23, RED)
            self._button("Back to Setup", self.pg.Rect(x, self.screen.get_height() - 105, 230, 58), self._back_after_failure)
        elif complete:
            self._put("Installation and boot files were verified.", x, y + 120, 25, GREEN, True)
            self._wrap("Shut down safely. When the PC is off, remove the Aurum USB and turn the PC on.", x, y + 165, width, 22, TEXT)
            self._button("Shut Down Safely", self.pg.Rect(x, self.screen.get_height() - 105, 285, 58), self._poweroff, accent=GREEN)

    def _back_after_failure(self) -> None:
        try:
            self.coordinator.reset()
        except InstallError:
            pass
        self.status = {}
        self.view = "setup"
        self._refresh_setup()

    def _render_wifi(self) -> None:
        x, y, width, _ = self._header("Connect to the internet", self.network_message)
        left_width = int(width * 0.54)
        for index, ssid in enumerate(self.ssids[:8]):
            top = y + index * 54
            rect = self.pg.Rect(x, top, left_width, 46)
            selected = ssid == self.selected_ssid
            self.pg.draw.rect(self.screen, PANEL_SELECTED if selected else PANEL, rect, border_radius=8)
            self.pg.draw.rect(self.screen, GOLD if selected else (55, 66, 76), rect, 2 if selected else 1, border_radius=8)
            self._put(ssid, x + 16, top + 11, 19, TEXT, selected)
            self.buttons.append((rect, lambda value=ssid: self._select_ssid(value), True))
        field_x = x + left_width + 36
        self._put("Wi-Fi password", field_x, y, 20, MUTED, True)
        field = self.pg.Rect(field_x, y + 34, width - left_width - 36, 54)
        self.pg.draw.rect(self.screen, PANEL_SELECTED if self.password_focus else PANEL, field, border_radius=8)
        self.pg.draw.rect(self.screen, GOLD if self.password_focus else (55, 66, 76), field, 2, border_radius=8)
        shown = "•" * len(self.password) if self.password else "Click here, then type"
        self._put(shown, field.x + 14, field.y + 15, 19, TEXT if self.password else MUTED)
        self.buttons.append((field, lambda: setattr(self, "password_focus", True), True))
        self._button("Scan Again", self.pg.Rect(field_x, y + 112, 180, 52), self._open_wifi)
        self._button("Connect", self.pg.Rect(field_x + 195, y + 112, 165, 52), self._connect, enabled=bool(self.selected_ssid), accent=GREEN)
        self._button("Back", self.pg.Rect(x, self.screen.get_height() - 105, 160, 58), lambda: setattr(self, "view", "setup"))

    def _select_ssid(self, ssid: str) -> None:
        self.selected_ssid = ssid
        self.password_focus = True

    def _render(self) -> None:
        self.buttons = []
        if self.view == "setup":
            self._render_setup()
        elif self.view == "confirm":
            self._render_confirm()
        elif self.view == "wifi":
            self._render_wifi()
        else:
            self._render_progress()
        self.pg.display.flip()

    def _events(self) -> None:
        for event in self.pg.event.get():
            if event.type == self.pg.QUIT:
                self.running = False
            elif event.type == self.pg.KEYDOWN:
                if self.view == "wifi" and self.password_focus:
                    if event.key == self.pg.K_BACKSPACE:
                        self.password = self.password[:-1]
                    elif event.key in {self.pg.K_RETURN, self.pg.K_KP_ENTER}:
                        self._connect()
                    elif event.unicode and event.unicode.isprintable() and len(self.password) < 128:
                        self.password += event.unicode
                elif event.key == self.pg.K_ESCAPE and self.view in {"wifi", "confirm"}:
                    self.view = "setup"
            elif event.type == self.pg.MOUSEBUTTONUP and event.button == 1:
                for rect, action, enabled in reversed(self.buttons):
                    if enabled and rect.collidepoint(event.pos):
                        action()
                        break

    def run(self) -> int:
        try:
            while self.running:
                self._poll_network()
                self._events()
                self._render()
                self.clock.tick(30)
        finally:
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.pg.quit()
        return 0


def main() -> int:
    if not LIVE_MEDIUM.is_dir() and os.environ.get("AURUM_SETUP_ALLOW_NONLIVE") != "1":
        return 2
    import pygame

    pygame.init()
    return AurumSetupGui(pygame).run()


if __name__ == "__main__":
    raise SystemExit(main())
