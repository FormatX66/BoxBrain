#!/usr/bin/env python3
"""Native full-screen Echo Rally for Hopper.

This is the physical-display proof for Aurum Arcade 001. It uses SDL through
pygame so Hopper can render and read local keyboard/pointer input without a web
browser or shell. A tiny read-only proof endpoint exposes only machine/display/
input readiness; it accepts no commands and has no host-control API.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import socket
import threading
import time
from array import array
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

SCHEMA = "aurum.echo.native.v2"
PROOF_SCHEMA = "aurum.hopper.echo-proof.v1"
MACHINE = "Hopper"
GAME = "Echo Rally"
LOGICAL_W = 960
LOGICAL_H = 540
WIN_SCORE = 7
PROOF_PORT = 8767
EXPECTED_SERIAL = "BTTE934116YM512B-1"
EXPECTED_SIZE_BYTES = 512110190592
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_RUN = Path("/run/aurum")
EVENT_RE = re.compile(r"\bevent\d+\b")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _tone(pygame, frequency: float, seconds: float = 0.035, volume: float = 0.18):
    if not pygame.mixer.get_init():
        return None
    rate = 22050
    count = max(1, int(rate * seconds))
    samples = array("h")
    amplitude = int(32767 * max(0.0, min(volume, 1.0)))
    for index in range(count):
        samples.append(int(amplitude * math.sin(2.0 * math.pi * frequency * index / rate)))
    try:
        return pygame.mixer.Sound(buffer=samples.tobytes())
    except Exception:
        return None


def _input_nodes() -> dict[str, list[str]]:
    keyboard: set[str] = set()
    pointer: set[str] = set()
    try:
        text = Path("/proc/bus/input/devices").read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    for block in text.split("\n\n"):
        handlers = ""
        for line in block.splitlines():
            if line.startswith("H: Handlers="):
                handlers = line.partition("=")[2]
                break
        if not handlers:
            continue
        events = EVENT_RE.findall(handlers)
        tokens = handlers.split()
        if "kbd" in tokens:
            keyboard.update(f"/dev/input/{name}" for name in events)
        if any(token.startswith("mouse") for token in tokens):
            pointer.update(f"/dev/input/{name}" for name in events)
    return {"keyboard": sorted(keyboard), "pointer": sorted(pointer)}


def _open_input_targets(pid: int) -> set[str]:
    targets: set[str] = set()
    try:
        entries = list(Path(f"/proc/{pid}/fd").iterdir())
    except OSError:
        return targets
    for entry in entries:
        try:
            target = os.readlink(entry)
        except OSError:
            continue
        if target.startswith("/dev/input/event"):
            targets.add(target)
    return targets


def _cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def _x_server_pids() -> list[int]:
    found: list[int] = []
    try:
        entries = list(Path("/proc").iterdir())
    except OSError:
        return found
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        cmdline = _cmdline(pid)
        if "Xorg" in cmdline or cmdline.startswith("/usr/lib/xorg/Xorg ") or cmdline.startswith("Xorg "):
            found.append(pid)
    return found


def _input_proof(game_pid: int, display: Mapping[str, Any]) -> dict[str, Any]:
    nodes = _input_nodes()
    keyboard_nodes = set(nodes["keyboard"])
    pointer_nodes = set(nodes["pointer"])
    game_open = _open_input_targets(game_pid)
    mode = str(display.get("mode") or "")
    x_pids = _x_server_pids() if mode == "x11-vt2" else []
    x_open: set[str] = set()
    for pid in x_pids:
        x_open.update(_open_input_targets(pid))

    if mode == "kmsdrm-vt2":
        active_open = game_open
    elif mode == "x11-vt2":
        active_open = x_open
    else:
        active_open = game_open | x_open
    keyboard_open = sorted(keyboard_nodes & active_open)
    pointer_open = sorted(pointer_nodes & active_open)
    return {
        "mode": mode or None,
        "keyboard_device_count": len(keyboard_nodes),
        "pointer_device_count": len(pointer_nodes),
        "keyboard_path_available": bool(keyboard_open),
        "pointer_path_available": bool(pointer_open),
        "keyboard_open_nodes": keyboard_open,
        "pointer_open_nodes": pointer_open,
        "game_open_input_node_count": len(game_open),
        "x_server_pids": x_pids,
        "x_open_input_node_count": len(x_open),
    }


def _positive_resolution(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in value)
    )


def _proof_payload(state_dir: Path, live_receipt: Mapping[str, Any]) -> dict[str, Any]:
    install = _json_file(Path("/etc/aurum-installed.json"))
    identity = _json_file(state_dir / "machine-identity.json")
    display = _json_file(state_dir / "hopper-display.json")
    target = install.get("target") if isinstance(install.get("target"), dict) else {}
    exact_machine = bool(
        str(target.get("serial") or "") == EXPECTED_SERIAL
        and int(target.get("size_bytes") or 0) == EXPECTED_SIZE_BYTES
    )
    identity_ready = bool(
        identity.get("status") == "named"
        and identity.get("display_name") == MACHINE
        and identity.get("hostname") == "hopper"
    )
    display_ready = bool(
        display.get("authorized") is True
        and display.get("physical_display") is True
        and display.get("status") == "running"
        and display.get("machine") == MACHINE
    )
    process_running = "aurum_echo_native.py" in _cmdline(os.getpid())
    echo_ready = bool(
        live_receipt.get("status") == "running"
        and live_receipt.get("machine") == MACHINE
        and live_receipt.get("game") == GAME
        and live_receipt.get("fullscreen") is True
        and isinstance(live_receipt.get("video_driver"), str)
        and bool(str(live_receipt.get("video_driver") or "").strip())
        and _positive_resolution(live_receipt.get("physical_resolution"))
        and process_running
    )
    input_proof = _input_proof(os.getpid(), display)
    ready = bool(
        exact_machine
        and identity_ready
        and display_ready
        and echo_ready
        and input_proof["keyboard_path_available"]
        and input_proof["pointer_path_available"]
    )
    return {
        "schema": PROOF_SCHEMA,
        "ready": ready,
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "machine": {
            "authorized_exact_hopper": exact_machine,
            "expected_serial": EXPECTED_SERIAL,
            "expected_size_bytes": EXPECTED_SIZE_BYTES,
            "display_name": identity.get("display_name"),
            "configured_hostname": identity.get("hostname"),
            "runtime_hostname": socket.gethostname(),
            "identity_receipt_ready": identity_ready,
        },
        "display": {
            "ready": display_ready,
            "status": display.get("status"),
            "mode": display.get("mode"),
            "physical_display": display.get("physical_display") is True,
        },
        "echo": {
            "ready": echo_ready,
            "status": live_receipt.get("status"),
            "game": live_receipt.get("game"),
            "pid": os.getpid(),
            "process_running": process_running,
            "fullscreen": live_receipt.get("fullscreen") is True,
            "video_driver": live_receipt.get("video_driver"),
            "physical_resolution": live_receipt.get("physical_resolution"),
            "started_at": live_receipt.get("started_at"),
            "frames_presented": live_receipt.get("frames_presented"),
        },
        "input": input_proof,
        "boundary": {
            "read_only": True,
            "post_supported": False,
            "host_actuation": False,
            "logs_exposed": False,
            "credential_data_exposed": False,
        },
    }


class _ProofServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], state_dir: Path, live_receipt: dict[str, Any]) -> None:
        super().__init__(address, _ProofHandler)
        self.state_dir = state_dir
        self.live_receipt = live_receipt
        self.receipt_lock = threading.Lock()


class _ProofHandler(BaseHTTPRequestHandler):
    server: _ProofServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if urlsplit(self.path).path not in {"/", "/proof"}:
            self._json(HTTPStatus.NOT_FOUND, {"schema": PROOF_SCHEMA, "error": "not-found"})
            return
        with self.server.receipt_lock:
            receipt = dict(self.server.live_receipt)
        self._json(HTTPStatus.OK, _proof_payload(self.server.state_dir, receipt))

    def do_POST(self) -> None:  # noqa: N802
        self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"schema": PROOF_SCHEMA, "error": "read-only"})


def _start_proof_server(state_dir: Path, receipt: dict[str, Any]) -> tuple[_ProofServer | None, str | None]:
    try:
        server = _ProofServer(("0.0.0.0", PROOF_PORT), state_dir, receipt)
    except OSError as exc:
        return None, f"{type(exc).__name__}:{exc}"
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.4}, daemon=True)
    thread.start()
    return server, None


def run_game(state_dir: Path, run_dir: Path) -> int:
    pid_path = run_dir / "echo-native.pid"
    receipt_path = state_dir / "echo-native.json"
    run_dir.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    proof_server: _ProofServer | None = None
    receipt: dict[str, Any] = {}
    try:
        import pygame

        try:
            pygame.mixer.pre_init(22050, -16, 1, 256)
        except Exception:
            pass
        pygame.display.init()
        pygame.font.init()
        try:
            pygame.mixer.init()
        except Exception:
            pass

        info = pygame.display.Info()
        width = int(info.current_w or 1280)
        height = int(info.current_h or 720)
        screen = pygame.display.set_mode((width, height), pygame.FULLSCREEN | pygame.DOUBLEBUF)
        pygame.display.set_caption("Echo Rally — Hopper")
        logical = pygame.Surface((LOGICAL_W, LOGICAL_H)).convert()
        clock = pygame.time.Clock()
        font_big = pygame.font.Font(None, 70)
        font_mid = pygame.font.Font(None, 34)
        font_small = pygame.font.Font(None, 22)
        video_driver = pygame.display.get_driver()

        receipt = {
            "schema": SCHEMA,
            "status": "running",
            "machine": MACHINE,
            "game": GAME,
            "pid": os.getpid(),
            "started_at": started_at,
            "video_driver": video_driver,
            "physical_resolution": [width, height],
            "logical_resolution": [LOGICAL_W, LOGICAL_H],
            "fullscreen": True,
            "frames_presented": 0,
            "network_listener": False,
            "proof_listener": None,
            "host_actuation_api": False,
            "controls": "W/S or pointer; 1 solo; 2 two-player; arrows right; P pause; Enter reset; Esc exit",
        }
        proof_server, proof_error = _start_proof_server(state_dir, receipt)
        if proof_server is not None:
            receipt["network_listener"] = True
            receipt["proof_listener"] = {"host": "0.0.0.0", "port": PROOF_PORT, "read_only": True}
        elif proof_error:
            receipt["proof_listener"] = {"status": "unavailable", "detail": proof_error}
        _atomic_json(receipt_path, receipt)

        bg = (7, 9, 14)
        panel = (11, 15, 23)
        ink = (247, 241, 223)
        muted = (142, 150, 167)
        gold = (245, 196, 81)
        echo = (119, 215, 211)
        line = (72, 65, 44)
        red = (235, 108, 108)

        paddle_w, paddle_h, margin = 16.0, 112.0, 34.0
        left = {"x": margin, "y": LOGICAL_H / 2 - paddle_h / 2, "v": 0.0}
        right = {"x": LOGICAL_W - margin - paddle_w, "y": LOGICAL_H / 2 - paddle_h / 2, "v": 0.0}
        ball = {"x": LOGICAL_W / 2, "y": LOGICAL_H / 2, "r": 9.0, "vx": 390.0, "vy": 120.0}
        wells: list[dict[str, float]] = []
        trail: list[dict[str, float]] = []
        score_l = score_r = 0
        rally = 0
        mode = 1
        paused = False
        pointer_active_until = 0.0
        frame_counter = 0
        last_receipt_update = time.monotonic()

        hit_sound = _tone(pygame, 310)
        echo_sound = _tone(pygame, 620, 0.055, 0.14)
        score_sound = _tone(pygame, 820, 0.08, 0.16)
        lose_sound = _tone(pygame, 130, 0.12, 0.16)

        def play(sound) -> None:
            try:
                if sound is not None:
                    sound.play()
            except Exception:
                pass

        def reset_ball(direction: int | None = None) -> None:
            nonlocal rally
            if direction is None:
                direction = -1 if random.random() < 0.5 else 1
            angle = random.uniform(-0.35, 0.35)
            speed = 380.0
            ball["x"] = LOGICAL_W / 2
            ball["y"] = LOGICAL_H / 2
            ball["vx"] = math.cos(angle) * speed * direction
            ball["vy"] = math.sin(angle) * speed
            rally = 0
            trail.clear()

        def reset_game() -> None:
            nonlocal score_l, score_r, paused
            score_l = score_r = 0
            wells.clear()
            paused = False
            reset_ball()

        def add_well(x: float, y: float, now: float) -> None:
            wells.append({"x": x, "y": y, "born": now, "life": 3.6})
            if len(wells) > 4:
                del wells[0]
            play(echo_sound)

        def paddle_hit(paddle: dict[str, float], side: int, now: float) -> None:
            nonlocal rally
            center = paddle["y"] + paddle_h / 2
            offset = max(-1.0, min(1.0, (ball["y"] - center) / (paddle_h / 2)))
            speed = min(760.0, math.hypot(ball["vx"], ball["vy"]) * 1.045 + 8.0)
            angle = offset * 1.02
            ball["vx"] = math.cos(angle) * speed * side
            ball["vy"] = math.sin(angle) * speed
            rally += 1
            if rally % 4 == 0:
                add_well(ball["x"], ball["y"], now)
            play(hit_sound)

        reset_ball()
        running = True
        while running:
            dt = min(clock.tick(120) / 1000.0, 0.035)
            now = time.monotonic()
            keys = pygame.key.get_pressed()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_1:
                        mode = 1
                    elif event.key == pygame.K_2:
                        mode = 2
                    elif event.key == pygame.K_p:
                        paused = not paused
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        reset_game()
                elif event.type == pygame.MOUSEMOTION:
                    pointer_active_until = now + 1.2
                    py = event.pos[1] * LOGICAL_H / max(height, 1)
                    left["y"] = max(12.0, min(LOGICAL_H - paddle_h - 12.0, py - paddle_h / 2))

            if not paused:
                speed = 500.0
                if now >= pointer_active_until:
                    left["v"] = ((1.0 if keys[pygame.K_s] else 0.0) - (1.0 if keys[pygame.K_w] else 0.0)) * speed
                    left["y"] = max(12.0, min(LOGICAL_H - paddle_h - 12.0, left["y"] + left["v"] * dt))
                if mode == 2:
                    right["v"] = ((1.0 if keys[pygame.K_DOWN] else 0.0) - (1.0 if keys[pygame.K_UP] else 0.0)) * speed
                else:
                    target = ball["y"] - paddle_h / 2
                    right["v"] = max(-390.0, min(390.0, (target - right["y"]) * 5.1))
                right["y"] = max(12.0, min(LOGICAL_H - paddle_h - 12.0, right["y"] + right["v"] * dt))

                wells[:] = [well for well in wells if now - well["born"] < well["life"]]
                for well in wells:
                    dx = well["x"] - ball["x"]
                    dy = well["y"] - ball["y"]
                    distance2 = dx * dx + dy * dy + 4000.0
                    force = 62000.0 / distance2
                    ball["vx"] += dx * force * dt
                    ball["vy"] += dy * force * dt

                ball["x"] += ball["vx"] * dt
                ball["y"] += ball["vy"] * dt
                if ball["y"] - ball["r"] < 10 and ball["vy"] < 0:
                    ball["y"] = 10 + ball["r"]
                    ball["vy"] *= -1
                if ball["y"] + ball["r"] > LOGICAL_H - 10 and ball["vy"] > 0:
                    ball["y"] = LOGICAL_H - 10 - ball["r"]
                    ball["vy"] *= -1

                if ball["vx"] < 0 and ball["x"] - ball["r"] <= left["x"] + paddle_w and ball["x"] > left["x"] and left["y"] - 8 <= ball["y"] <= left["y"] + paddle_h + 8:
                    ball["x"] = left["x"] + paddle_w + ball["r"]
                    paddle_hit(left, 1, now)
                if ball["vx"] > 0 and ball["x"] + ball["r"] >= right["x"] and ball["x"] < right["x"] + paddle_w and right["y"] - 8 <= ball["y"] <= right["y"] + paddle_h + 8:
                    ball["x"] = right["x"] - ball["r"]
                    paddle_hit(right, -1, now)

                if ball["x"] < -30:
                    score_r += 1
                    play(lose_sound)
                    if score_r >= WIN_SCORE:
                        paused = True
                    else:
                        reset_ball(1)
                elif ball["x"] > LOGICAL_W + 30:
                    score_l += 1
                    play(score_sound)
                    if score_l >= WIN_SCORE:
                        paused = True
                    else:
                        reset_ball(-1)

                trail.append({"x": ball["x"], "y": ball["y"], "t": now})
                trail[:] = [point for point in trail if now - point["t"] < 0.52]

            logical.fill(bg)
            pygame.draw.rect(logical, panel, (8, 8, LOGICAL_W - 16, LOGICAL_H - 16), border_radius=20)
            pygame.draw.rect(logical, line, (8, 8, LOGICAL_W - 16, LOGICAL_H - 16), 2, border_radius=20)
            for y in range(24, LOGICAL_H - 24, 30):
                pygame.draw.rect(logical, (55, 53, 45), (LOGICAL_W // 2 - 2, y, 4, 14), border_radius=2)

            for well in wells:
                age = max(0.0, now - well["born"])
                alpha = max(0.0, 1.0 - age / well["life"])
                radius = int(22 + age * 15)
                layer = pygame.Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
                center = radius + 4
                pygame.draw.circle(layer, (*echo, int(80 * alpha)), (center, center), radius, 3)
                pygame.draw.circle(layer, (*gold, int(32 * alpha)), (center, center), max(4, radius // 3), 2)
                logical.blit(layer, (int(well["x"] - center), int(well["y"] - center)))

            for point in trail:
                age = max(0.0, now - point["t"])
                fade = max(0.0, 1.0 - age / 0.52)
                radius = max(2, int(ball["r"] * fade))
                color = tuple(int(channel * fade) for channel in echo)
                pygame.draw.circle(logical, color, (int(point["x"]), int(point["y"])), radius)

            pygame.draw.rect(logical, gold, (int(left["x"]), int(left["y"]), int(paddle_w), int(paddle_h)), border_radius=7)
            pygame.draw.rect(logical, echo, (int(right["x"]), int(right["y"]), int(paddle_w), int(paddle_h)), border_radius=7)
            pygame.draw.circle(logical, ink, (int(ball["x"]), int(ball["y"])), int(ball["r"]))

            score = font_big.render(f"{score_l}   {score_r}", True, ink)
            logical.blit(score, score.get_rect(center=(LOGICAL_W // 2, 54)))
            title = font_mid.render("ECHO RALLY", True, gold)
            logical.blit(title, (26, 22))
            mode_text = font_small.render("SOLO" if mode == 1 else "TWO PLAYER", True, muted)
            logical.blit(mode_text, (LOGICAL_W - mode_text.get_width() - 26, 28))
            footer = font_small.render("W/S or pointer · 1 solo · 2 two-player · P pause · Enter reset · Esc exit", True, muted)
            logical.blit(footer, footer.get_rect(center=(LOGICAL_W // 2, LOGICAL_H - 25)))
            twist = font_small.render("Every fourth return leaves an echo well. Your old rally bends the next one.", True, echo)
            logical.blit(twist, twist.get_rect(center=(LOGICAL_W // 2, LOGICAL_H - 49)))

            if score_l >= WIN_SCORE or score_r >= WIN_SCORE:
                winner = "LEFT WINS" if score_l > score_r else "RIGHT WINS"
                banner = font_big.render(winner, True, gold if score_l > score_r else echo)
                logical.blit(banner, banner.get_rect(center=(LOGICAL_W // 2, LOGICAL_H // 2 - 24)))
                hint = font_mid.render("Press Enter for another rally", True, ink)
                logical.blit(hint, hint.get_rect(center=(LOGICAL_W // 2, LOGICAL_H // 2 + 38)))
            elif paused:
                banner = font_big.render("PAUSED", True, red)
                logical.blit(banner, banner.get_rect(center=(LOGICAL_W // 2, LOGICAL_H // 2)))

            frame = pygame.transform.smoothscale(logical, (width, height))
            screen.blit(frame, (0, 0))
            pygame.display.flip()
            frame_counter += 1

            if now - last_receipt_update >= 2.0:
                receipt["frames_presented"] = frame_counter
                receipt["heartbeat_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                _atomic_json(receipt_path, receipt)
                if proof_server is not None:
                    with proof_server.receipt_lock:
                        proof_server.live_receipt.clear()
                        proof_server.live_receipt.update(receipt)
                last_receipt_update = now

        receipt["status"] = "stopped"
        receipt["stopped_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _atomic_json(receipt_path, receipt)
        pygame.quit()
        return 0
    except Exception as exc:
        _atomic_json(
            receipt_path,
            {
                "schema": SCHEMA,
                "status": "failed",
                "machine": MACHINE,
                "game": GAME,
                "pid": os.getpid(),
                "started_at": started_at,
                "detail": f"{type(exc).__name__}:{exc}",
                "sdl_video_driver_requested": os.environ.get("SDL_VIDEODRIVER"),
            },
        )
        return 1
    finally:
        if proof_server is not None:
            try:
                proof_server.shutdown()
                proof_server.server_close()
            except Exception:
                pass
        try:
            if pid_path.read_text(encoding="utf-8").strip() == str(os.getpid()):
                pid_path.unlink(missing_ok=True)
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Echo Rally physical display proof")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    args = parser.parse_args()
    return run_game(args.state_dir, args.run_dir)


if __name__ == "__main__":
    raise SystemExit(main())
