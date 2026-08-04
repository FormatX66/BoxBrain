"""Guarded USB-HID bootstrap for an authorized headless Windows console."""

from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
import hashlib
import ipaddress
import os
from pathlib import Path
import stat
import time
from typing import Callable

from boxbrain.link_monitor import probe, save_link


HEADLESS_LINK_AUTHORIZATION = "boxbrain.headless-windows-link.authorized.v1"
HEADLESS_LINK_CONFIRMATION = "CONNECT HEADLESS WINDOWS"
FIXED_ONBOARDING_URL = "http://10.12.194.1:8788/windows-link.ps1"
DEFAULT_SCRIPT_PATH = Path("/opt/boxbrain/onboarding/windows-link.ps1")
DEFAULT_HID_DEVICE = Path("/dev/hidg0")
DEFAULT_TARGET_ADDRESS = "10.12.194.2"

_MODIFIER_LEFT_CONTROL = 0x01
_MODIFIER_LEFT_SHIFT = 0x02
_MODIFIER_LEFT_ALT = 0x04
_MODIFIER_LEFT_GUI = 0x08
_KEY_ENTER = 0x28


class HeadlessLinkError(RuntimeError):
    """A guarded headless-link request could not be completed."""


@dataclass(frozen=True)
class KeyEvent:
    modifier: int
    keycode: int
    delay_after: float = 0.0


@dataclass(frozen=True)
class TextEvent:
    text: str
    delay_between: float = 0.004
    delay_after: float = 0.0


_CHARACTERS: dict[str, tuple[int, int]] = {
    " ": (0, 0x2C),
    "-": (0, 0x2D),
    ".": (0, 0x37),
    "/": (0, 0x38),
    "=": (0, 0x2E),
    "+": (_MODIFIER_LEFT_SHIFT, 0x2E),
}
for _offset, _character in enumerate("abcdefghijklmnopqrstuvwxyz"):
    _CHARACTERS[_character] = (0, 0x04 + _offset)
    _CHARACTERS[_character.upper()] = (_MODIFIER_LEFT_SHIFT, 0x04 + _offset)
for _offset, _character in enumerate("1234567890"):
    _CHARACTERS[_character] = (0, 0x1E + _offset)


def _sha256(path: Path) -> str:
    algorithm = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                algorithm.update(chunk)
    except OSError as error:
        raise HeadlessLinkError("The installed Windows link helper is unavailable.") from error
    return algorithm.hexdigest()


def _is_hid_device(path: Path) -> bool:
    try:
        return stat.S_ISCHR(path.stat().st_mode)
    except OSError:
        return False


def _validate_target(address: str) -> str:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as error:
        raise HeadlessLinkError("The USB target address is invalid.") from error
    if parsed.version != 4 or parsed not in ipaddress.ip_network("10.12.194.0/24"):
        raise HeadlessLinkError("The headless link is restricted to the USB gadget subnet.")
    if str(parsed) in {"10.12.194.0", "10.12.194.1", "10.12.194.255"}:
        raise HeadlessLinkError("The USB target address is not usable.")
    return str(parsed)


def build_bootstrap_command(script_sha256: str) -> str:
    """Return the fixed, credential-free PowerShell bootstrap command."""
    if len(script_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in script_sha256
    ):
        raise HeadlessLinkError("The Windows link helper SHA-256 is invalid.")
    script = (
        f"$u='{FIXED_ONBOARDING_URL}';"
        "$p=Join-Path $env:TEMP 'boxbrain-link.ps1';"
        "Invoke-WebRequest -UseBasicParsing -Uri $u -OutFile $p;"
        "if((Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash."
        f"ToLowerInvariant() -ne '{script_sha256}'){{"
        "Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue;exit 91};"
        "& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass "
        "-File $p -Authorized"
    )
    encoded = b64encode(script.encode("utf-16-le")).decode("ascii")
    return (
        "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass "
        f"-EncodedCommand {encoded}"
    )


def build_keystroke_plan(script_sha256: str) -> tuple[KeyEvent | TextEvent, ...]:
    """Build a fixed US-layout sequence for an unlocked Windows console."""
    command = build_bootstrap_command(script_sha256)
    return (
        KeyEvent(_MODIFIER_LEFT_GUI, _CHARACTERS["r"][1], 1.0),
        TextEvent("powershell.exe -NoLogo -NoProfile", delay_after=0.2),
        KeyEvent(_MODIFIER_LEFT_CONTROL | _MODIFIER_LEFT_SHIFT, _KEY_ENTER, 3.0),
        KeyEvent(_MODIFIER_LEFT_ALT, _CHARACTERS["y"][1], 4.0),
        TextEvent(command, delay_after=0.2),
        KeyEvent(0, _KEY_ENTER),
    )


def _write_report(handle: int, modifier: int, keycode: int) -> None:
    report = bytes((modifier, 0, keycode, 0, 0, 0, 0, 0))
    try:
        written = os.write(handle, report)
    except OSError as error:
        raise HeadlessLinkError("The USB keyboard rejected a report.") from error
    if written != len(report):
        raise HeadlessLinkError("The USB keyboard accepted an incomplete report.")


def send_keystroke_plan(
    plan: tuple[KeyEvent | TextEvent, ...],
    device: Path = DEFAULT_HID_DEVICE,
    *,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    """Send only a prebuilt fixed plan to the configured HID keyboard."""
    try:
        flags = (
            os.O_WRONLY
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_BINARY", 0)
        )
        handle = os.open(device, flags)
    except OSError as error:
        raise HeadlessLinkError("The USB HID keyboard device could not be opened.") from error
    try:
        for event in plan:
            if isinstance(event, TextEvent):
                for character in event.text:
                    stroke = _CHARACTERS.get(character)
                    if stroke is None:
                        raise HeadlessLinkError(
                            "The fixed bootstrap command is not compatible with the US HID map."
                        )
                    _write_report(handle, *stroke)
                    _write_report(handle, 0, 0)
                    sleeper(event.delay_between)
                sleeper(event.delay_after)
                continue
            _write_report(handle, event.modifier, event.keycode)
            _write_report(handle, 0, 0)
            sleeper(event.delay_after)
    finally:
        try:
            _write_report(handle, 0, 0)
        finally:
            os.close(handle)


def preview_headless_windows_link(
    *,
    script_path: Path = DEFAULT_SCRIPT_PATH,
    hid_device: Path = DEFAULT_HID_DEVICE,
    target_address: str = DEFAULT_TARGET_ADDRESS,
    effective_uid: int | None = None,
) -> dict[str, object]:
    """Return readiness without sending a key or changing the target."""
    address = _validate_target(target_address)
    script_sha256 = _sha256(script_path)
    uid = os.geteuid() if effective_uid is None else effective_uid
    return {
        "schema_version": 1,
        "action": "preview",
        "changed": False,
        "target_address": address,
        "onboarding_url": FIXED_ONBOARDING_URL,
        "script_sha256": script_sha256,
        "hid_device": str(hid_device),
        "hid_ready": _is_hid_device(hid_device),
        "running_as_root": uid == 0,
        "requires": [
            "physically attached authorized Windows target",
            "unlocked interactive console",
            "US keyboard layout",
            "local administrator and UAC consent without credential entry",
            f"exact confirmation: {HEADLESS_LINK_CONFIRMATION}",
        ],
        "verification": "key-only SSH must succeed after injection",
        "credentials_typed": False,
    }


def execute_headless_windows_link(
    authorization: str,
    confirmation: str,
    *,
    script_path: Path = DEFAULT_SCRIPT_PATH,
    hid_device: Path = DEFAULT_HID_DEVICE,
    target_address: str = DEFAULT_TARGET_ADDRESS,
    timeout: int = 120,
    effective_uid: int | None = None,
    sender: Callable[[tuple[KeyEvent | TextEvent, ...], Path], None] | None = None,
    verifier: Callable[..., dict[str, object] | None] = probe,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Inject the fixed bootstrap and require an authenticated link proof."""
    if authorization != HEADLESS_LINK_AUTHORIZATION:
        raise HeadlessLinkError("Headless Windows link authorization is required.")
    if confirmation != HEADLESS_LINK_CONFIRMATION:
        raise HeadlessLinkError(
            f"Type the exact confirmation phrase: {HEADLESS_LINK_CONFIRMATION}"
        )
    uid = os.geteuid() if effective_uid is None else effective_uid
    if uid != 0:
        raise HeadlessLinkError("Headless USB keyboard deployment must run as root.")
    address = _validate_target(target_address)
    if not _is_hid_device(hid_device):
        raise HeadlessLinkError(
            "The USB HID keyboard is not configured. No keystrokes were sent."
        )
    if verifier(address, transport="usb-ethernet-ssh") is not None:
        raise HeadlessLinkError(
            "The target already has a verified BoxBrain link. "
            "No keystrokes were sent."
        )
    script_sha256 = _sha256(script_path)
    plan = build_keystroke_plan(script_sha256)
    resolved_sender = sender or send_keystroke_plan
    resolved_sender(plan, hid_device)

    deadline = time.monotonic() + max(1, min(timeout, 300))
    while time.monotonic() < deadline:
        link = verifier(address, transport="usb-ethernet-ssh")
        if link is not None:
            saved = save_link(link)
            return {
                "schema_version": 1,
                "action": "execute",
                "changed": True,
                "target_address": address,
                "status": "verified",
                "hostname": saved.get("hostname"),
                "transport": saved.get("transport"),
                "credentials_typed": False,
                "verification": "key-only SSH succeeded",
            }
        sleeper(2.0)
    raise HeadlessLinkError(
        "Keystrokes were sent, but key-only SSH was not verified. "
        "Do not assume deployment succeeded or retry blindly."
    )
