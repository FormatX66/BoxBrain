#!/usr/bin/env python3
"""Host-side controller for the Aurum early-boot KVM protocol."""
from __future__ import annotations

import argparse
import base64
import json
import socket
import ssl
import zlib
from pathlib import Path
from typing import Any, Mapping

from early_kvm import PROTOCOL_SCHEMA, canonical_json, message_mac


CONTROLLER_SCHEMA = "aurum-early-kvm-controller-v1"
MAX_RESPONSE_BYTES = 48 * 1024 * 1024
MAX_FRAME_RAW_BYTES = 32 * 1024 * 1024


class ControllerError(RuntimeError):
    pass


def load_controller(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ControllerError(f"controller configuration is unreadable: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != CONTROLLER_SCHEMA:
        raise ControllerError("controller configuration schema is invalid")
    raw_key = value.get("authority_key_hex")
    if not isinstance(raw_key, str) or len(raw_key) != 64:
        raise ControllerError("controller authority key is invalid")
    try:
        key = bytes.fromhex(raw_key)
    except ValueError as exc:
        raise ControllerError("controller authority key is invalid") from exc
    if len(key) != 32 or not any(key):
        raise ControllerError("controller authority key is invalid")
    target = str(value.get("target", ""))
    controller = str(value.get("controller", ""))
    if not target or not controller:
        raise ControllerError("controller target and identity are required")
    result = dict(value)
    result["_authority_key"] = key
    try:
        result["port"] = int(value.get("port", 19467))
        result["timeout_seconds"] = float(value.get("timeout_seconds", 8.0))
    except (TypeError, ValueError) as exc:
        raise ControllerError("controller port or timeout is invalid") from exc
    if not 1024 <= result["port"] <= 65535 or not 1.0 <= result["timeout_seconds"] <= 60.0:
        raise ControllerError("controller port or timeout is outside its bound")
    if value.get("transport") != "tls-pinned":
        raise ControllerError("controller transport must be tls-pinned")
    tls_ca = Path(str(value.get("tls_ca_path", "")))
    if not tls_ca.is_file():
        raise ControllerError("pinned early KVM certificate is unavailable")
    try:
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(tls_ca))
    except (OSError, ssl.SSLError) as exc:
        raise ControllerError(f"pinned early KVM certificate is invalid: {exc}") from exc
    context.check_hostname = False
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    result["_tls_context"] = context
    return result


def _receive(handle) -> dict[str, Any]:
    raw = handle.readline(MAX_RESPONSE_BYTES + 1)
    if not raw:
        raise ControllerError("early KVM connection closed")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ControllerError("early KVM response exceeds the client bound")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ControllerError("early KVM response is invalid") from exc
    if not isinstance(value, dict):
        raise ControllerError("early KVM response must be an object")
    if value.get("schema") != PROTOCOL_SCHEMA:
        raise ControllerError("early KVM response protocol schema changed")
    return value


class Session:
    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = config
        try:
            connection = socket.create_connection(
                (str(config["target"]), int(config["port"])),
                timeout=float(config["timeout_seconds"]),
            )
            context = config.get("_tls_context")
            self.socket = (
                context.wrap_socket(connection, server_hostname=str(config["target"]))
                if context is not None
                else connection
            )
        except OSError as exc:
            raise ControllerError(f"cannot connect to early KVM: {exc}") from exc
        self.socket.settimeout(float(config["timeout_seconds"]))
        self.reader = self.socket.makefile("rb")
        self.writer = self.socket.makefile("wb")
        challenge = _receive(self.reader)
        if challenge.get("schema") != PROTOCOL_SCHEMA or challenge.get("outcome") != "challenge":
            self.close()
            raise ControllerError(f"early KVM refused before authentication: {challenge.get('reason', 'unknown')}")
        client_nonce = __import__("secrets").token_hex(16)
        authentication = {
            "schema": PROTOCOL_SCHEMA,
            "op": "authenticate",
            "challenge": challenge["challenge"],
            "client_nonce": client_nonce,
            "controller": config["controller"],
        }
        authentication["mac"] = message_mac(config["_authority_key"], authentication)
        self._write(authentication)
        accepted = _receive(self.reader)
        if accepted.get("outcome") != "authenticated":
            self.close()
            raise ControllerError(f"early KVM authentication refused: {accepted.get('reason', 'unknown')}")
        self.session = str(accepted["session"])
        self.sequence = int(accepted["next_sequence"])

    def _write(self, value: Mapping[str, Any]) -> None:
        self.writer.write(canonical_json(value) + b"\n")
        self.writer.flush()

    def command(self, operation: str, **parameters: Any) -> dict[str, Any]:
        request = {
            "schema": PROTOCOL_SCHEMA,
            "session": self.session,
            "seq": self.sequence,
            "op": operation,
            **parameters,
        }
        request["mac"] = message_mac(self.config["_authority_key"], request)
        self._write(request)
        response = _receive(self.reader)
        if response.get("session") != self.session or response.get("seq") != self.sequence:
            raise ControllerError("early KVM response session or sequence changed")
        self.sequence += 1
        if response.get("outcome") not in {"succeeded", "waiting"}:
            raise ControllerError(f"early KVM command refused: {response.get('reason', 'unknown')}")
        return response

    def close(self) -> None:
        for name in ("reader", "writer"):
            handle = getattr(self, name, None)
            if handle is not None:
                try:
                    handle.close()
                except OSError:
                    pass
        sock = getattr(self, "socket", None)
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def save_frame(frame: Mapping[str, Any], destination: Path) -> dict[str, Any]:
    if not frame.get("available"):
        return dict(frame)
    if frame.get("encoding") != "zlib+base64":
        raise ControllerError("unsupported framebuffer encoding")
    try:
        compressed = base64.b64decode(str(frame["data"]), validate=True)
        decompressor = zlib.decompressobj()
        raw = decompressor.decompress(compressed, MAX_FRAME_RAW_BYTES + 1)
        if len(raw) > MAX_FRAME_RAW_BYTES or decompressor.unconsumed_tail or decompressor.unused_data or not decompressor.eof:
            raise ControllerError("framebuffer decompression exceeds the client bound")
    except (ValueError, zlib.error) as exc:
        raise ControllerError("framebuffer payload is invalid") from exc
    digest = __import__("hashlib").sha256(raw).hexdigest()
    if digest != frame.get("raw_sha256"):
        raise ControllerError("framebuffer hash verification failed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(raw)
    temporary.replace(destination)
    metadata = {name: value for name, value in frame.items() if name != "data"}
    metadata["path"] = str(destination.resolve())
    return metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control Aurum's authenticated early-boot KVM")
    parser.add_argument("--config", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    text = subparsers.add_parser("type")
    text.add_argument("text")
    key = subparsers.add_parser("key")
    key.add_argument("key")
    key.add_argument("value", choices=("press", "release"))
    mouse = subparsers.add_parser("mouse")
    mouse.add_argument("--dx", type=int, default=0)
    mouse.add_argument("--dy", type=int, default=0)
    mouse.add_argument("--wheel", type=int, default=0)
    mouse.add_argument("--left", choices=("press", "release"))
    mouse.add_argument("--right", choices=("press", "release"))
    mouse.add_argument("--middle", choices=("press", "release"))
    subparsers.add_parser("release-all")
    frame = subparsers.add_parser("frame")
    frame.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_controller(args.config)
        with Session(config) as session:
            if args.command == "status":
                result = session.command("status")
            elif args.command == "type":
                result = session.command("text", text=args.text)
            elif args.command == "key":
                result = session.command("key", key=args.key, value=1 if args.value == "press" else 0)
            elif args.command == "mouse":
                buttons = {
                    name: 1 if getattr(args, name) == "press" else 0
                    for name in ("left", "right", "middle")
                    if getattr(args, name) is not None
                }
                result = session.command("mouse", dx=args.dx, dy=args.dy, wheel=args.wheel, buttons=buttons)
            elif args.command == "release-all":
                result = session.command("release_all")
            else:
                response = session.command("frame")
                result = save_frame(response["frame"], args.output)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except ControllerError as exc:
        print(json.dumps({"schema": CONTROLLER_SCHEMA, "outcome": "refused", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
