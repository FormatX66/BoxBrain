#!/usr/bin/env python3
"""Native full-screen Echo Rally for Hopper.

This is the physical-display proof for Aurum Arcade 001. It uses SDL through
pygame so Hopper can render and read local keyboard/pointer input without a web
browser, network listener, shell, or host-control API.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from array import array
from pathlib import Path
from typing import Any

SCHEMA = "aurum.echo.native.v1"
MACHINE = "Hopper"
GAME = "Echo Rally"
LOGICAL_W = 960
LOGICAL_H = 540
WIN_SCORE = 7
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_RUN = Path("/run/aurum")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


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


def run_game(state_dir: Path, run_dir: Path) -> int:
    pid_path = run_dir / "echo-native.pid"
    receipt_path = state_dir / "echo-native.json"
    run_dir.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
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
            "network_listener": False,
            "host_actuation_api": False,
            "controls": "W/S or pointer; 1 solo; 2 two-player; arrows right; P pause; Enter reset; Esc exit",
        }
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
