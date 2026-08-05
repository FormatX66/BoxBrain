"""Bounded USB HID keyboard and mouse broker for the BoxBrain Pi."""

from __future__ import annotations

from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import select
import socket
import socketserver
import stat
import threading
import time
from typing import Any, Callable


DEFAULT_SOCKET = Path("/run/boxbrain-hid-kvm/control.sock")
DEFAULT_KEYBOARD = Path("/dev/hidg0")
DEFAULT_MOUSE = Path("/dev/hidg1")
DEFAULT_AUDIT = Path("/var/lib/boxbrain/hid-kvm/audit.jsonl")
MAX_REQUEST_BYTES = 8192
MAX_TEXT_CHARACTERS = 256
IDLE_RELEASE_SECONDS = 2.0
_HAS_UNIX_SERVER = hasattr(socketserver, "ThreadingUnixStreamServer")
_HidKvmServerBase = getattr(
    socketserver,
    "ThreadingUnixStreamServer",
    socketserver.ThreadingTCPServer,
)


class HidKvmError(RuntimeError):
    """A bounded HID operation could not be completed."""


_MODIFIERS = {
    "ControlLeft": 0x01,
    "ShiftLeft": 0x02,
    "AltLeft": 0x04,
    "MetaLeft": 0x08,
    "ControlRight": 0x10,
    "ShiftRight": 0x20,
    "AltRight": 0x40,
    "MetaRight": 0x80,
}

_KEYS: dict[str, int] = {
    **{f"Key{letter}": 0x04 + index for index, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")},
    **{f"Digit{digit}": 0x1E + index for index, digit in enumerate("123456789")},
    "Digit0": 0x27,
    "Enter": 0x28,
    "Escape": 0x29,
    "Backspace": 0x2A,
    "Tab": 0x2B,
    "Space": 0x2C,
    "Minus": 0x2D,
    "Equal": 0x2E,
    "BracketLeft": 0x2F,
    "BracketRight": 0x30,
    "Backslash": 0x31,
    "Semicolon": 0x33,
    "Quote": 0x34,
    "Backquote": 0x35,
    "Comma": 0x36,
    "Period": 0x37,
    "Slash": 0x38,
    "CapsLock": 0x39,
    **{f"F{number}": 0x39 + number for number in range(1, 13)},
    "PrintScreen": 0x46,
    "ScrollLock": 0x47,
    "Pause": 0x48,
    "Insert": 0x49,
    "Home": 0x4A,
    "PageUp": 0x4B,
    "Delete": 0x4C,
    "End": 0x4D,
    "PageDown": 0x4E,
    "ArrowRight": 0x4F,
    "ArrowLeft": 0x50,
    "ArrowDown": 0x51,
    "ArrowUp": 0x52,
    "NumLock": 0x53,
    "NumpadDivide": 0x54,
    "NumpadMultiply": 0x55,
    "NumpadSubtract": 0x56,
    "NumpadAdd": 0x57,
    "NumpadEnter": 0x58,
    **{f"Numpad{digit}": usage for digit, usage in zip("1234567890", range(0x59, 0x63))},
    "NumpadDecimal": 0x63,
    "ContextMenu": 0x65,
}


def _build_text_map() -> dict[str, tuple[int, int]]:
    result: dict[str, tuple[int, int]] = {" ": (0, _KEYS["Space"])}
    for letter in "abcdefghijklmnopqrstuvwxyz":
        usage = _KEYS[f"Key{letter.upper()}"]
        result[letter] = (0, usage)
        result[letter.upper()] = (0x02, usage)
    for digit in "0123456789":
        result[digit] = (0, _KEYS[f"Digit{digit}"])
    punctuation = {
        "-": (0, "Minus"), "_": (0x02, "Minus"),
        "=": (0, "Equal"), "+": (0x02, "Equal"),
        "[": (0, "BracketLeft"), "{": (0x02, "BracketLeft"),
        "]": (0, "BracketRight"), "}": (0x02, "BracketRight"),
        "\\": (0, "Backslash"), "|": (0x02, "Backslash"),
        ";": (0, "Semicolon"), ":": (0x02, "Semicolon"),
        "'": (0, "Quote"), '"': (0x02, "Quote"),
        "`": (0, "Backquote"), "~": (0x02, "Backquote"),
        ",": (0, "Comma"), "<": (0x02, "Comma"),
        ".": (0, "Period"), ">": (0x02, "Period"),
        "/": (0, "Slash"), "?": (0x02, "Slash"),
    }
    result.update({character: (modifier, _KEYS[code]) for character, (modifier, code) in punctuation.items()})
    for digit, symbol in zip("1234567890", "!@#$%^&*()"):
        result[symbol] = (0x02, _KEYS[f"Digit{digit}"])
    result["\n"] = (0, _KEYS["Enter"])
    result["\t"] = (0, _KEYS["Tab"])
    return result


_TEXT_KEYS = _build_text_map()


def _is_character_device(path: Path) -> bool:
    try:
        return stat.S_ISCHR(path.stat().st_mode)
    except OSError:
        return False


def _write_hid(path: Path, report: bytes) -> None:
    try:
        handle = os.open(path, os.O_WRONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
    except OSError as error:
        raise HidKvmError(f"The HID device {path} could not be opened.") from error
    try:
        deadline = time.monotonic() + 1.0
        while True:
            try:
                written = os.write(handle, report)
                break
            except BlockingIOError as error:
                if error.errno not in {errno.EAGAIN, errno.EWOULDBLOCK}:
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise HidKvmError(f"The HID device {path} stayed busy.") from error
                select.select([], [handle], [], remaining)
        if written != len(report):
            raise HidKvmError(f"The HID device {path} accepted an incomplete report.")
    except OSError as error:
        raise HidKvmError(f"The HID device {path} rejected a report.") from error
    finally:
        os.close(handle)


def _bounded_int(value: object, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise HidKvmError(f"{name} must be an integer from {minimum} through {maximum}.")
    return value


class HidKvmState:
    """Owns pressed-key state and emits exact boot-protocol HID reports."""

    def __init__(
        self,
        keyboard: Path = DEFAULT_KEYBOARD,
        mouse: Path = DEFAULT_MOUSE,
        audit: Path = DEFAULT_AUDIT,
        writer: Callable[[Path, bytes], None] = _write_hid,
    ) -> None:
        self.keyboard = keyboard
        self.mouse = mouse
        self.audit = audit
        self.writer = writer
        self.modifiers = 0
        self.keys: set[int] = set()
        self.buttons = 0
        self.last_activity = time.monotonic()
        self.lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        with self.lock:
            return {
                "schema_version": 1,
                "keyboard_ready": _is_character_device(self.keyboard),
                "mouse_ready": _is_character_device(self.mouse),
                "pressed_key_count": len(self.keys),
                "modifier_mask": self.modifiers,
                "button_mask": self.buttons,
                "idle_release_seconds": IDLE_RELEASE_SECONDS,
            }

    def _audit(self, action: str, **details: object) -> None:
        record = {
            "schema_version": 1,
            "at": datetime.now(timezone.utc).isoformat(),
            "action": action,
            **details,
        }
        self.audit.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        handle = os.open(self.audit, flags, 0o600)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(handle, 0o600)
            os.write(handle, json.dumps(record, separators=(",", ":"), sort_keys=True).encode() + b"\n")
        finally:
            os.close(handle)

    def _keyboard_report(self) -> bytes:
        keys = sorted(self.keys)
        return bytes([self.modifiers, 0, *keys, *([0] * (6 - len(keys)))])

    def _release(self, reason: str) -> None:
        self.modifiers = 0
        self.keys.clear()
        self.buttons = 0
        self.writer(self.keyboard, b"\0" * 8)
        self.writer(self.mouse, b"\0" * 4)
        self.last_activity = time.monotonic()
        self._audit("release", reason=reason)

    def release_if_idle(self, now: float | None = None) -> bool:
        with self.lock:
            current = time.monotonic() if now is None else now
            if not (self.keys or self.modifiers or self.buttons):
                return False
            if current - self.last_activity < IDLE_RELEASE_SECONDS:
                return False
            self._release("watchdog")
            return True

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        if action == "status":
            return {"ok": True, "status": self.status()}
        with self.lock:
            if action == "release":
                self._release("operator")
                return {"ok": True, "released": True}
            if action == "key":
                code = request.get("code")
                down = request.get("down")
                if not isinstance(code, str) or type(down) is not bool:
                    raise HidKvmError("A key request requires a browser code and Boolean down state.")
                if code in _MODIFIERS:
                    if down:
                        self.modifiers |= _MODIFIERS[code]
                    else:
                        self.modifiers &= ~_MODIFIERS[code]
                elif code in _KEYS:
                    usage = _KEYS[code]
                    if down and usage not in self.keys and len(self.keys) >= 6:
                        raise HidKvmError("The USB keyboard supports at most six simultaneous keys.")
                    self.keys.add(usage) if down else self.keys.discard(usage)
                else:
                    raise HidKvmError("That keyboard code is not allowlisted.")
                self.writer(self.keyboard, self._keyboard_report())
                self.last_activity = time.monotonic()
                self._audit("key", code=code, down=down)
                return {"ok": True, "pressed_key_count": len(self.keys)}
            if action == "pointer":
                dx = _bounded_int(request.get("dx", 0), "dx", -127, 127)
                dy = _bounded_int(request.get("dy", 0), "dy", -127, 127)
                wheel = _bounded_int(request.get("wheel", 0), "wheel", -127, 127)
                buttons = _bounded_int(request.get("buttons", 0), "buttons", 0, 7)
                self.buttons = buttons
                self.writer(self.mouse, bytes([buttons, dx & 0xFF, dy & 0xFF, wheel & 0xFF]))
                self.last_activity = time.monotonic()
                self._audit("pointer", dx=dx, dy=dy, wheel=wheel, buttons=buttons)
                return {"ok": True, "button_mask": buttons}
            if action == "text":
                text = request.get("text")
                if not isinstance(text, str) or not 1 <= len(text) <= MAX_TEXT_CHARACTERS:
                    raise HidKvmError(f"Text must contain 1-{MAX_TEXT_CHARACTERS} characters.")
                try:
                    reports = [_TEXT_KEYS[character] for character in text]
                except KeyError as error:
                    raise HidKvmError("Text contains a character unsupported by the US keyboard map.") from error
                self._release("text-start")
                for modifier, usage in reports:
                    self.writer(self.keyboard, bytes([modifier, 0, usage, 0, 0, 0, 0, 0]))
                    self.writer(self.keyboard, b"\0" * 8)
                self.last_activity = time.monotonic()
                self._audit("text", character_count=len(text), raw_text_logged=False)
                return {"ok": True, "character_count": len(text)}
        raise HidKvmError("Unsupported HID KVM action.")


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            response = {"ok": False, "error": "request_too_large"}
        else:
            try:
                request = json.loads(raw.decode("utf-8"))
                if not isinstance(request, dict):
                    raise HidKvmError("A HID KVM request must be a JSON object.")
                response = self.server.state.handle(request)  # type: ignore[attr-defined]
            except (UnicodeError, json.JSONDecodeError, HidKvmError, OSError) as error:
                response = {"ok": False, "error": str(error)[:500]}
        self.wfile.write(json.dumps(response, separators=(",", ":")).encode() + b"\n")


class HidKvmServer(_HidKvmServerBase):  # type: ignore[misc,valid-type]
    daemon_threads = True

    def __init__(self, path: Path, state: HidKvmState, group: str = "boxbrain") -> None:
        import grp

        if not _HAS_UNIX_SERVER:
            raise RuntimeError("The HID KVM broker requires Unix-domain socket support.")
        self.path = path
        self.state = state
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        path.unlink(missing_ok=True)
        super().__init__(str(path), _Handler)
        os.chmod(path, 0o660)
        os.chown(path, 0, grp.getgrnam(group).gr_gid)

    def server_close(self) -> None:
        try:
            self.state.handle({"action": "release"})
        finally:
            super().server_close()
            self.path.unlink(missing_ok=True)


class HidKvmClient:
    def __init__(self, path: Path = DEFAULT_SOCKET, timeout: float = 2.0) -> None:
        self.path = path
        self.timeout = timeout

    def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload, separators=(",", ":")).encode() + b"\n"
        if len(data) > MAX_REQUEST_BYTES:
            raise HidKvmError("The HID KVM request is too large.")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout)
                connection.connect(str(self.path))
                connection.sendall(data)
                response = b""
                while not response.endswith(b"\n") and len(response) <= MAX_REQUEST_BYTES:
                    chunk = connection.recv(4096)
                    if not chunk:
                        break
                    response += chunk
        except OSError as error:
            raise HidKvmError("The HID KVM broker is unavailable.") from error
        try:
            decoded = json.loads(response.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise HidKvmError("The HID KVM broker returned an invalid response.") from error
        if not isinstance(decoded, dict) or decoded.get("ok") is not True:
            raise HidKvmError(str(decoded.get("error", "The HID KVM request failed."))[:500])
        return decoded


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("The HID KVM broker must run as root.")
    state = HidKvmState()
    server = HidKvmServer(DEFAULT_SOCKET, state)
    stop = threading.Event()

    def watchdog() -> None:
        while not stop.wait(0.25):
            try:
                state.release_if_idle()
            except (HidKvmError, OSError):
                pass

    watcher = threading.Thread(target=watchdog, name="hid-kvm-watchdog", daemon=True)
    watcher.start()
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        watcher.join(timeout=2)


if __name__ == "__main__":
    main()
