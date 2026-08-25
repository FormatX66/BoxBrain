#!/usr/bin/env python3
"""Authenticated early-boot keyboard, mouse, and bounded framebuffer service.

The Raspberry Pi firmware still owns the immutable pre-kernel boot boundary.
This service starts in the earliest practical TinySeed userspace, before the
installer, and exposes only a controller-allowlisted, HMAC-authenticated input
surface.  HDMI capture remains the visual LKG when a Linux framebuffer is not
available.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socketserver
import ssl
import threading
import time
import zlib
from pathlib import Path
from typing import Any, Mapping


AUTHORITY_SCHEMA = "aurum-early-kvm-authority-v1"
PROTOCOL_SCHEMA = "aurum-early-kvm-v1"
DEFAULT_CONFIG = Path("/etc/aurum/early-kvm.json")
DEFAULT_RECEIPT = Path("/var/lib/aurum/evidence/early-kvm-events.jsonl")
MAX_REQUEST_BYTES = 64 * 1024
MAX_TEXT_LENGTH = 256


class EarlyKVMError(RuntimeError):
    pass


def canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def message_mac(key: bytes, value: Mapping[str, Any]) -> str:
    body = {name: item for name, item in value.items() if name != "mac"}
    return hmac.new(key, canonical_json(body), hashlib.sha256).hexdigest()


def _bounded_int(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise EarlyKVMError(f"{name} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise EarlyKVMError(f"{name} must be from {minimum} to {maximum}")
    return parsed


def load_authority(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EarlyKVMError(f"authority configuration is unreadable: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != AUTHORITY_SCHEMA:
        raise EarlyKVMError("authority configuration schema is invalid")
    if value.get("enabled") is not True:
        raise EarlyKVMError("early KVM authority is not enabled")
    raw_key = value.get("authority_key_hex")
    if not isinstance(raw_key, str) or len(raw_key) != 64:
        raise EarlyKVMError("authority_key_hex must contain 32 bytes")
    try:
        key = bytes.fromhex(raw_key)
    except ValueError as exc:
        raise EarlyKVMError("authority_key_hex is invalid") from exc
    if len(key) != 32 or not any(key):
        raise EarlyKVMError("authority key is invalid")

    raw_networks = value.get("allowed_controller_cidrs")
    if not isinstance(raw_networks, list) or not raw_networks:
        raise EarlyKVMError("at least one controller CIDR is required")
    networks = []
    for raw in raw_networks:
        try:
            network = ipaddress.ip_network(str(raw), strict=True)
        except ValueError as exc:
            raise EarlyKVMError(f"invalid controller CIDR: {raw}") from exc
        minimum_prefix = 24 if network.version == 4 else 64
        if network.prefixlen < minimum_prefix:
            raise EarlyKVMError(f"controller CIDR must be /{minimum_prefix} or narrower")
        networks.append(network)

    config = dict(value)
    config["_authority_key"] = key
    config["_controller_networks"] = networks
    config["listen"] = str(value.get("listen", "0.0.0.0"))
    config["port"] = _bounded_int(value.get("port", 19467), name="port", minimum=1024, maximum=65535)
    config["session_seconds"] = _bounded_int(
        value.get("session_seconds", 1800), name="session_seconds", minimum=30, maximum=7200
    )
    config["max_frame_bytes"] = _bounded_int(
        value.get("max_frame_bytes", 16 * 1024 * 1024),
        name="max_frame_bytes",
        minimum=1024,
        maximum=32 * 1024 * 1024,
    )
    config["allow_framebuffer"] = bool(value.get("allow_framebuffer", False))
    config["video_fallback"] = str(value.get("video_fallback", "hdmi-capture"))
    if value.get("transport") != "tls-pinned":
        raise EarlyKVMError("early KVM transport must be tls-pinned")
    certificate = Path(str(value.get("tls_cert_path", "")))
    private_key = Path(str(value.get("tls_key_path", "")))
    config["tls_cert_path"] = str(certificate)
    config["tls_key_path"] = str(private_key)
    return config


def public_status(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": PROTOCOL_SCHEMA,
        "enabled": True,
        "listen": config["listen"],
        "port": config["port"],
        "allowed_controller_cidrs": [str(item) for item in config["_controller_networks"]],
        "session_seconds": config["session_seconds"],
        "allow_framebuffer": config["allow_framebuffer"],
        "video_fallback": config["video_fallback"],
        "input_backend": "linux-uinput",
        "transport": "tls-pinned+hmac-sha256",
    }


def source_allowed(address: str, config: Mapping[str, Any]) -> bool:
    try:
        observed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(observed in network for network in config["_controller_networks"])


LETTER_KEYS = {chr(code): f"KEY_{chr(code).upper()}" for code in range(ord("a"), ord("z") + 1)}
DIGIT_KEYS = {str(number): f"KEY_{number}" for number in range(10)}
TEXT_KEYS: dict[str, tuple[str, bool]] = {
    **{value: (key, False) for value, key in LETTER_KEYS.items()},
    **{value.upper(): (key, True) for value, key in LETTER_KEYS.items()},
    **{value: (key, False) for value, key in DIGIT_KEYS.items()},
    " ": ("KEY_SPACE", False),
    "\n": ("KEY_ENTER", False),
    "\t": ("KEY_TAB", False),
    "-": ("KEY_MINUS", False),
    "_": ("KEY_MINUS", True),
    "=": ("KEY_EQUAL", False),
    "+": ("KEY_EQUAL", True),
    "[": ("KEY_LEFTBRACE", False),
    "{": ("KEY_LEFTBRACE", True),
    "]": ("KEY_RIGHTBRACE", False),
    "}": ("KEY_RIGHTBRACE", True),
    "\\": ("KEY_BACKSLASH", False),
    "|": ("KEY_BACKSLASH", True),
    ";": ("KEY_SEMICOLON", False),
    ":": ("KEY_SEMICOLON", True),
    "'": ("KEY_APOSTROPHE", False),
    '"': ("KEY_APOSTROPHE", True),
    "`": ("KEY_GRAVE", False),
    "~": ("KEY_GRAVE", True),
    ",": ("KEY_COMMA", False),
    "<": ("KEY_COMMA", True),
    ".": ("KEY_DOT", False),
    ">": ("KEY_DOT", True),
    "/": ("KEY_SLASH", False),
    "?": ("KEY_SLASH", True),
    "!": ("KEY_1", True),
    "@": ("KEY_2", True),
    "#": ("KEY_3", True),
    "$": ("KEY_4", True),
    "%": ("KEY_5", True),
    "^": ("KEY_6", True),
    "&": ("KEY_7", True),
    "*": ("KEY_8", True),
    "(": ("KEY_9", True),
    ")": ("KEY_0", True),
}

ALLOWED_KEY_NAMES = frozenset(
    set(LETTER_KEYS.values())
    | set(DIGIT_KEYS.values())
    | {key for key, _ in TEXT_KEYS.values()}
    | {
        "KEY_ENTER",
        "KEY_ESC",
        "KEY_TAB",
        "KEY_BACKSPACE",
        "KEY_DELETE",
        "KEY_INSERT",
        "KEY_HOME",
        "KEY_END",
        "KEY_PAGEUP",
        "KEY_PAGEDOWN",
        "KEY_UP",
        "KEY_DOWN",
        "KEY_LEFT",
        "KEY_RIGHT",
        "KEY_LEFTCTRL",
        "KEY_LEFTSHIFT",
        "KEY_LEFTALT",
        "KEY_RIGHTCTRL",
        "KEY_RIGHTSHIFT",
        "KEY_RIGHTALT",
        "KEY_F1",
        "KEY_F2",
        "KEY_F3",
        "KEY_F4",
        "KEY_F5",
        "KEY_F6",
        "KEY_F7",
        "KEY_F8",
        "KEY_F9",
        "KEY_F10",
        "KEY_F11",
        "KEY_F12",
    }
)


class InputBackend:
    def key(self, name: str, value: int) -> None:
        raise NotImplementedError

    def text(self, value: str) -> None:
        for character in value:
            if character not in TEXT_KEYS:
                raise EarlyKVMError(f"unsupported text character: U+{ord(character):04X}")
            key, shifted = TEXT_KEYS[character]
            if shifted:
                self.key("KEY_LEFTSHIFT", 1)
            self.key(key, 1)
            self.key(key, 0)
            if shifted:
                self.key("KEY_LEFTSHIFT", 0)

    def mouse(self, dx: int, dy: int, wheel: int, buttons: Mapping[str, int]) -> None:
        raise NotImplementedError

    def release_all(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        self.release_all()


class EvdevInputBackend(InputBackend):
    def __init__(self) -> None:
        try:
            import evdev  # type: ignore
        except ImportError as exc:
            raise EarlyKVMError("python3-evdev is required for the uinput backend") from exc
        self.evdev = evdev
        codes = evdev.ecodes
        key_codes = [getattr(codes, name) for name in sorted(ALLOWED_KEY_NAMES)]
        button_codes = [codes.BTN_LEFT, codes.BTN_RIGHT, codes.BTN_MIDDLE]
        capabilities = {
            codes.EV_KEY: key_codes + button_codes,
            codes.EV_REL: [codes.REL_X, codes.REL_Y, codes.REL_WHEEL],
        }
        try:
            self.device = evdev.UInput(capabilities, name="Aurum Early KVM", version=0x0001)
        except (OSError, PermissionError) as exc:
            raise EarlyKVMError(f"cannot create uinput device: {exc}") from exc
        self.pressed: set[int] = set()

    def _emit(self, event_type: int, code: int, value: int) -> None:
        self.device.write(event_type, code, value)
        self.device.syn()

    def key(self, name: str, value: int) -> None:
        if name not in ALLOWED_KEY_NAMES or value not in {0, 1}:
            raise EarlyKVMError("key event is outside the allowlist")
        code = int(getattr(self.evdev.ecodes, name))
        self._emit(self.evdev.ecodes.EV_KEY, code, value)
        if value:
            self.pressed.add(code)
        else:
            self.pressed.discard(code)

    def mouse(self, dx: int, dy: int, wheel: int, buttons: Mapping[str, int]) -> None:
        codes = self.evdev.ecodes
        for event_code, value in ((codes.REL_X, dx), (codes.REL_Y, dy), (codes.REL_WHEEL, wheel)):
            if value:
                self.device.write(codes.EV_REL, event_code, value)
        button_map = {"left": codes.BTN_LEFT, "right": codes.BTN_RIGHT, "middle": codes.BTN_MIDDLE}
        for name, value in buttons.items():
            if name not in button_map or value not in {0, 1}:
                raise EarlyKVMError("mouse button event is outside the allowlist")
            code = button_map[name]
            self.device.write(codes.EV_KEY, code, value)
            if value:
                self.pressed.add(code)
            else:
                self.pressed.discard(code)
        self.device.syn()

    def release_all(self) -> None:
        if not hasattr(self, "device"):
            return
        for code in tuple(self.pressed):
            self.device.write(self.evdev.ecodes.EV_KEY, code, 0)
        self.pressed.clear()
        self.device.syn()

    def close(self) -> None:
        self.release_all()
        self.device.close()


class FrameBuffer:
    def __init__(
        self,
        *,
        device: Path = Path("/dev/fb0"),
        sysfs: Path = Path("/sys/class/graphics/fb0"),
    ) -> None:
        self.device = device
        self.sysfs = sysfs

    def snapshot(self, config: Mapping[str, Any]) -> dict[str, Any]:
        fallback = str(config.get("video_fallback", "hdmi-capture"))
        if not config.get("allow_framebuffer"):
            return {"available": False, "reason": "framebuffer-export-disabled", "video_fallback": fallback}
        try:
            width_text, height_text = (self.sysfs / "virtual_size").read_text(encoding="ascii").strip().split(",", 1)
            width, height = int(width_text), int(height_text)
            bits = int((self.sysfs / "bits_per_pixel").read_text(encoding="ascii").strip())
        except (OSError, ValueError) as exc:
            return {"available": False, "reason": f"framebuffer-metadata-unavailable:{exc}", "video_fallback": fallback}
        expected = width * height * max(bits // 8, 1)
        maximum = int(config["max_frame_bytes"])
        if expected <= 0 or expected > maximum:
            return {"available": False, "reason": "framebuffer-size-outside-bound", "video_fallback": fallback}
        try:
            with self.device.open("rb", buffering=0) as handle:
                raw = handle.read(expected + 1)
        except OSError as exc:
            return {"available": False, "reason": f"framebuffer-read-unavailable:{exc}", "video_fallback": fallback}
        if len(raw) != expected:
            return {"available": False, "reason": "framebuffer-short-read", "video_fallback": fallback}
        compressed = zlib.compress(raw, level=3)
        return {
            "available": True,
            "width": width,
            "height": height,
            "bits_per_pixel": bits,
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "encoding": "zlib+base64",
            "data": base64.b64encode(compressed).decode("ascii"),
            "video_fallback": fallback,
        }


class ReceiptLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()

    def append(self, event: str, **data: Any) -> None:
        record = {
            "schema": "aurum-early-kvm-event-v1",
            "observed_at_unix": int(time.time()),
            "event": event,
            **data,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


class AurumKVMServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        config: Mapping[str, Any],
        backend: InputBackend,
        framebuffer: FrameBuffer,
        tls_context: ssl.SSLContext | None,
    ):
        self.config = config
        self.backend = backend
        self.framebuffer = framebuffer
        self.receipts = ReceiptLog(Path(str(config.get("receipt_path", DEFAULT_RECEIPT))))
        self.session_lock = threading.Lock()
        self.session_active = False
        self.tls_context = tls_context
        super().__init__(address, AurumKVMHandler)

    def get_request(self):
        connection, address = super().get_request()
        if self.tls_context is None:
            return connection, address
        try:
            secured = self.tls_context.wrap_socket(connection, server_side=True)
        except ssl.SSLError:
            connection.close()
            raise
        return secured, address

    def acquire_session(self) -> bool:
        with self.session_lock:
            if self.session_active:
                return False
            self.session_active = True
            return True

    def release_session(self) -> None:
        with self.session_lock:
            try:
                self.backend.release_all()
            finally:
                self.session_active = False


class AurumKVMHandler(socketserver.StreamRequestHandler):
    server: AurumKVMServer

    def _send(self, value: Mapping[str, Any]) -> None:
        self.wfile.write(canonical_json(value) + b"\n")
        self.wfile.flush()

    def _receive(self) -> dict[str, Any]:
        raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if not raw:
            raise EOFError
        if len(raw) > MAX_REQUEST_BYTES:
            raise EarlyKVMError("request exceeds the protocol bound")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise EarlyKVMError("request is not valid JSON") from exc
        if not isinstance(value, dict):
            raise EarlyKVMError("request must be one JSON object")
        return value

    def _authenticate(self, challenge: str) -> tuple[str, str] | None:
        try:
            request = self._receive()
        except (EOFError, EarlyKVMError):
            return None
        if request.get("op") != "authenticate" or request.get("challenge") != challenge:
            self._send({"schema": PROTOCOL_SCHEMA, "outcome": "refused", "reason": "authentication-contract"})
            return None
        controller = str(request.get("controller", ""))
        client_nonce = str(request.get("client_nonce", ""))
        supplied = str(request.get("mac", ""))
        if not controller or len(controller) > 100 or len(client_nonce) != 32:
            self._send({"schema": PROTOCOL_SCHEMA, "outcome": "refused", "reason": "authentication-fields"})
            return None
        expected = message_mac(self.server.config["_authority_key"], request)
        if not hmac.compare_digest(supplied, expected):
            self._send({"schema": PROTOCOL_SCHEMA, "outcome": "refused", "reason": "authentication-mac"})
            return None
        return controller, client_nonce

    def _dispatch(self, request: Mapping[str, Any]) -> dict[str, Any]:
        operation = str(request.get("op", ""))
        if operation == "status":
            return {"outcome": "succeeded", "status": public_status(self.server.config)}
        if operation == "release_all":
            self.server.backend.release_all()
            return {"outcome": "succeeded", "released": True}
        if operation == "key":
            name = str(request.get("key", ""))
            value = _bounded_int(request.get("value"), name="key value", minimum=0, maximum=1)
            if name not in ALLOWED_KEY_NAMES:
                raise EarlyKVMError("key is outside the allowlist")
            self.server.backend.key(name, value)
            return {"outcome": "succeeded", "key": name, "value": value}
        if operation == "text":
            value = request.get("text")
            if not isinstance(value, str) or not value or len(value) > MAX_TEXT_LENGTH:
                raise EarlyKVMError("text must be from 1 to 256 characters")
            self.server.backend.text(value)
            return {"outcome": "succeeded", "characters": len(value)}
        if operation == "mouse":
            dx = _bounded_int(request.get("dx", 0), name="mouse dx", minimum=-127, maximum=127)
            dy = _bounded_int(request.get("dy", 0), name="mouse dy", minimum=-127, maximum=127)
            wheel = _bounded_int(request.get("wheel", 0), name="mouse wheel", minimum=-10, maximum=10)
            buttons = request.get("buttons", {})
            if not isinstance(buttons, dict):
                raise EarlyKVMError("mouse buttons must be an object")
            normalized = {str(name): _bounded_int(value, name="mouse button", minimum=0, maximum=1) for name, value in buttons.items()}
            if set(normalized) - {"left", "right", "middle"}:
                raise EarlyKVMError("mouse button is outside the allowlist")
            self.server.backend.mouse(dx, dy, wheel, normalized)
            return {"outcome": "succeeded", "dx": dx, "dy": dy, "wheel": wheel, "buttons": normalized}
        if operation == "frame":
            return {"outcome": "succeeded", "frame": self.server.framebuffer.snapshot(self.server.config)}
        raise EarlyKVMError("operation is outside the allowlist")

    def handle(self) -> None:
        source = str(self.client_address[0])
        if not source_allowed(source, self.server.config):
            self._send({"schema": PROTOCOL_SCHEMA, "outcome": "refused", "reason": "controller-address"})
            self.server.receipts.append("connection-refused", source=source, reason="controller-address")
            return
        challenge = secrets.token_hex(32)
        self._send(
            {
                "schema": PROTOCOL_SCHEMA,
                "outcome": "challenge",
                "challenge": challenge,
                "boot_id": _boot_id(),
                "video_fallback": self.server.config["video_fallback"],
            }
        )
        authenticated = self._authenticate(challenge)
        if authenticated is None:
            self.server.receipts.append("authentication-refused", source=source)
            return
        controller, _ = authenticated
        if not self.server.acquire_session():
            self._send({"schema": PROTOCOL_SCHEMA, "outcome": "waiting", "reason": "controller-session-active"})
            return
        session = secrets.token_hex(16)
        sequence = 1
        deadline = time.monotonic() + int(self.server.config["session_seconds"])
        self.server.receipts.append("session-opened", source=source, controller=controller, session=session)
        try:
            self._send(
                {
                    "schema": PROTOCOL_SCHEMA,
                    "outcome": "authenticated",
                    "session": session,
                    "next_sequence": sequence,
                    "expires_in_seconds": self.server.config["session_seconds"],
                }
            )
            while time.monotonic() < deadline:
                try:
                    request = self._receive()
                except EOFError:
                    break
                except EarlyKVMError as exc:
                    self._send({"schema": PROTOCOL_SCHEMA, "outcome": "refused", "reason": str(exc)})
                    break
                supplied = str(request.get("mac", ""))
                expected = message_mac(self.server.config["_authority_key"], request)
                if request.get("session") != session or request.get("seq") != sequence or not hmac.compare_digest(supplied, expected):
                    self._send({"schema": PROTOCOL_SCHEMA, "outcome": "refused", "reason": "session-sequence-or-mac"})
                    self.server.receipts.append("command-refused", source=source, controller=controller)
                    break
                operation = str(request.get("op", ""))
                try:
                    result = self._dispatch(request)
                except EarlyKVMError as exc:
                    result = {"outcome": "refused", "reason": str(exc)}
                self.server.receipts.append(
                    "command",
                    source=source,
                    controller=controller,
                    session=session,
                    sequence=sequence,
                    operation=operation,
                    outcome=result["outcome"],
                )
                self._send({"schema": PROTOCOL_SCHEMA, "session": session, "seq": sequence, **result})
                sequence += 1
        finally:
            self.server.release_session()
            self.server.receipts.append("session-closed", source=source, controller=controller, session=session)


def _boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except OSError:
        return "unavailable"


def build_server(
    config: Mapping[str, Any],
    *,
    backend: InputBackend | None = None,
    framebuffer: FrameBuffer | None = None,
    tls: bool = True,
) -> AurumKVMServer:
    context = None
    if tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            context.load_cert_chain(str(config["tls_cert_path"]), str(config["tls_key_path"]))
        except (KeyError, OSError, ssl.SSLError) as exc:
            raise EarlyKVMError(f"cannot load early KVM TLS identity: {exc}") from exc
    return AurumKVMServer(
        (str(config["listen"]), int(config["port"])),
        config,
        backend or EvdevInputBackend(),
        framebuffer or FrameBuffer(),
        context,
    )


def serve(config_path: Path | str) -> int:
    config = load_authority(config_path)
    server = build_server(config)
    server.receipts.append("service-started", status=public_status(config))
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.shutdown()
        server.server_close()
        server.backend.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aurum authenticated early-boot KVM")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = load_authority(args.config)
        if args.status:
            print(json.dumps(public_status(config), indent=2, sort_keys=True))
            return 0
        return serve(args.config)
    except EarlyKVMError as exc:
        print(json.dumps({"schema": PROTOCOL_SCHEMA, "outcome": "refused", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
