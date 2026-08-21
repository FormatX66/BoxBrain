#!/usr/bin/env python3
"""Aurum Gen1 physical desktop for Hopper.

A polished, machine-first presentation surface. It renders verified local state,
keeps tty1 available for recovery, and never exposes arbitrary host actuation.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

SCHEMA = "aurum.desktop.v2"
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_RUN = Path(os.environ.get("AURUM_RUN_DIR", "/run/aurum"))
DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
DEFAULT_RUNTIME = Path(os.environ.get("AURUM_RUNTIME_ROOT", "/opt/aurum"))
STOP_REQUESTED = False


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _text(path: Path, default: str = "—") -> str:
    try:
        value = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default
    return value or default


def _git_head(workspace: Path) -> str:
    raw = _text(workspace / ".git" / "HEAD", "")
    if raw.startswith("ref: "):
        return _text(workspace / ".git" / raw[5:].strip(), "unknown")
    return raw or "unknown"


def _git_branch(workspace: Path) -> str:
    raw = _text(workspace / ".git" / "HEAD", "")
    if raw.startswith("ref: refs/heads/"):
        return raw.removeprefix("ref: refs/heads/").strip()
    return "detached"


def _online() -> bool:
    try:
        lines = Path("/proc/net/route").read_text(encoding="utf-8", errors="replace").splitlines()[1:]
    except OSError:
        return False
    for line in lines:
        fields = line.split()
        if len(fields) < 4 or fields[1] != "00000000":
            continue
        try:
            flags = int(fields[3], 16)
        except ValueError:
            continue
        if flags & 0x1:
            return True
    return False


def _load_traits(workspace: Path, runtime_root: Path) -> dict[str, Any]:
    for path in (
        runtime_root / "aurum_traits.py",
        workspace / "Projects" / "AurumPC" / "aurum_traits.py",
        Path(__file__).with_name("aurum_traits.py"),
    ):
        if not path.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"aurum_traits_{time.time_ns()}", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            result = module.summary()
            if isinstance(result, dict):
                return result
        except Exception:
            continue
    return {"total": 0, "foundation_ready": 0, "planned": 0, "traits": []}


def collect_snapshot(
    *,
    state_dir: Path = DEFAULT_STATE,
    workspace: Path = DEFAULT_WORKSPACE,
    runtime_root: Path = DEFAULT_RUNTIME,
    input_state: Path = Path("/run/aurum-input-status.json"),
) -> dict[str, Any]:
    runtime = _json_file(state_dir / "runtime-update.json")
    identity = _json_file(state_dir / "machine-identity.json")
    autonomy = _json_file(state_dir / "autonomy.json")
    driver = _json_file(state_dir / "driver-lab" / "latest-cycle.json")
    input_status = _json_file(input_state)
    wake = input_status.get("wake_policy") if isinstance(input_status.get("wake_policy"), dict) else {}
    libinput = input_status.get("libinput") if isinstance(input_status.get("libinput"), dict) else {}
    chain = _json_file(runtime_root / "codelation" / "autobuild" / "native_chain_state.json")
    traits = _load_traits(workspace, runtime_root)
    head = _git_head(workspace)
    touchpads = list(input_status.get("touchpads") or [])
    pointers = list(input_status.get("pointers") or [])
    trackpad_ok = bool(
        touchpads
        and all(bool(item.get("present")) and bool(item.get("readable")) for item in touchpads)
        and (bool(libinput.get("xorg_driver")) or input_status.get("status") == "ready")
    )
    return {
        "machine": identity.get("display_name") or "Hopper",
        "hostname": identity.get("hostname") or _text(Path("/etc/hostname"), "hopper"),
        "online": _online(),
        "head": head,
        "head_short": head[:12] if head != "unknown" else "unknown",
        "branch": _git_branch(workspace),
        "runtime_schema": runtime.get("schema") or "unknown",
        "runtime_status": runtime.get("status") or "current",
        "autonomy_status": autonomy.get("status") or "ready",
        "driver_status": driver.get("status") or "ready",
        "driver_devices": int(driver.get("devices_modeled") or len(driver.get("devices") or [])),
        "input_status": input_status.get("status") or "unknown",
        "pointer_devices": len(pointers),
        "touchpad_devices": len(touchpads),
        "trackpad_ok": trackpad_ok,
        "libinput_xorg": bool(libinput.get("xorg_driver")),
        "wake_status": wake.get("status") or "unknown",
        "completed_generations": chain.get("completed_generations"),
        "next_gap": chain.get("next_gap") or "continuous observation",
        "traits": list(traits.get("traits") or []),
        "traits_total": int(traits.get("total") or 0),
        "traits_ready": int(traits.get("foundation_ready") or 0),
        "traits_planned": int(traits.get("planned") or 0),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _signal_handler(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def _fit(value: object, limit: int = 52) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _render() -> int:
    try:
        import pygame
    except Exception as exc:
        _atomic_json(DEFAULT_STATE / "desktop-ui.json", {
            "schema": SCHEMA,
            "status": "failed",
            "detail": f"pygame-unavailable:{type(exc).__name__}:{exc}",
        })
        return 1

    pygame.init()
    pygame.font.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    width, height = screen.get_size()
    pygame.display.set_caption("Aurum — Hopper")
    scale = min(width / 1440.0, height / 900.0)

    def font(size: int, bold: bool = False):
        return pygame.font.SysFont("DejaVu Sans", max(12, int(size * scale)), bold=bold)

    f_micro = font(11)
    f_small = font(14)
    f_body = font(18)
    f_card = font(24, True)
    f_title = font(43, True)
    f_hero = font(58, True)

    BG = (7, 9, 14)
    RAIL = (10, 12, 18)
    PANEL = (16, 20, 28)
    PANEL_HI = (21, 26, 36)
    LINE = (54, 58, 70)
    GOLD = (236, 190, 78)
    GOLD2 = (255, 224, 147)
    TEXT = (244, 242, 236)
    MUTED = (145, 153, 170)
    GOOD = (112, 218, 161)
    WARN = (236, 190, 78)
    BAD = (247, 128, 136)
    CYAN = (104, 204, 217)

    def text(value: object, x: int, y: int, face=f_body, color=TEXT):
        screen.blit(face.render(str(value), True, color), (x, y))

    def rounded(rect, fill, radius=18, border=None, width_px=1):
        pygame.draw.rect(screen, fill, rect, border_radius=max(5, int(radius * scale)))
        if border:
            pygame.draw.rect(screen, border, rect, width=max(1, int(width_px * scale)), border_radius=max(5, int(radius * scale)))

    def logo(cx: int, cy: int, radius: int, with_word=False):
        leaf_w = max(8, int(radius * 0.55))
        leaf_h = max(14, int(radius * 1.0))
        for i in range(7):
            angle = (math.tau * i / 7.0) - math.pi / 2
            lx = cx + int(math.cos(angle) * radius * 0.62)
            ly = cy + int(math.sin(angle) * radius * 0.62)
            leaf = pygame.Surface((leaf_w, leaf_h), pygame.SRCALPHA)
            pygame.draw.ellipse(leaf, GOLD, leaf.get_rect())
            leaf = pygame.transform.rotate(leaf, -math.degrees(angle) - 90)
            screen.blit(leaf, leaf.get_rect(center=(lx, ly)))
        pygame.draw.circle(screen, GOLD2, (cx, cy), max(3, int(radius * 0.16)))
        if with_word:
            word = font(22, True).render("AURUM", True, GOLD2)
            screen.blit(word, (cx - word.get_width() // 2, cy + int(radius * 1.05)))

    def status_dot(x: int, y: int, color):
        pygame.draw.circle(screen, color, (x, y), max(4, int(5 * scale)))

    snapshot = collect_snapshot()

    # Branded loading/splash phase on the actual graphical surface.
    stages = [
        ("Machine", True),
        ("Input", snapshot["touchpad_devices"] > 0 or snapshot["pointer_devices"] > 0),
        ("Network", snapshot["online"]),
        ("Runtime", snapshot["runtime_status"] in {"current", "updated", "ready"}),
        ("Desktop", True),
    ]
    splash_start = time.monotonic()
    while time.monotonic() - splash_start < 1.8 and not STOP_REQUESTED:
        elapsed = time.monotonic() - splash_start
        screen.fill(BG)
        logo(width // 2, int(height * 0.34), int(64 * scale), with_word=True)
        text("Waking Hopper", width // 2 - int(112 * scale), int(height * 0.51), f_card, TEXT)
        text("Aurum Gen1", width // 2 - int(58 * scale), int(height * 0.56), f_small, MUTED)
        base_x = width // 2 - int(180 * scale)
        y = int(height * 0.64)
        for idx, (name, ok) in enumerate(stages):
            active = elapsed >= idx * 0.22
            color = GOOD if active and ok else WARN if active else LINE
            status_dot(base_x + idx * int(90 * scale), y, color)
            label = f_micro.render(name, True, MUTED)
            screen.blit(label, (base_x + idx * int(90 * scale) - label.get_width() // 2, y + int(14 * scale)))
        pygame.display.flip()
        pygame.event.pump()
        time.sleep(0.03)

    _atomic_json(DEFAULT_STATE / "desktop-ui.json", {
        "schema": SCHEMA,
        "status": "running",
        "pid": os.getpid(),
        "surface": "physical",
        "machine": "Hopper",
        "host_actuation": False,
        "video_driver": os.environ.get("SDL_VIDEODRIVER", "auto"),
        "resolution": [width, height],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })

    rail_w = int(172 * scale)
    margin = int(34 * scale)
    gap = int(18 * scale)
    tabs = ["Home", "Traits", "Build", "Hardware", "Field", "Settings"]
    selected = 0
    last_refresh = 0.0
    clock = pygame.time.Clock()

    def card(rect, label, value, note, color=GOLD):
        rounded(rect, PANEL, 18, LINE)
        status_dot(rect.x + int(22 * scale), rect.y + int(24 * scale), color)
        text(label.upper(), rect.x + int(38 * scale), rect.y + int(13 * scale), f_micro, MUTED)
        text(_fit(value, 28), rect.x + int(20 * scale), rect.y + int(48 * scale), f_card, TEXT)
        text(_fit(note, 50), rect.x + int(20 * scale), rect.bottom - int(31 * scale), f_small, MUTED)

    def draw_home(x: int, y: int, w: int, h: int):
        hero_h = int(124 * scale)
        hero = pygame.Rect(x, y, w, hero_h)
        rounded(hero, PANEL_HI, 22, LINE)
        text("GENERATION ONE", hero.x + int(26 * scale), hero.y + int(22 * scale), f_micro, GOLD)
        text("Hopper is alive.", hero.x + int(26 * scale), hero.y + int(43 * scale), f_title, TEXT)
        sub = "Physical desktop online · machine state flowing through Aurum"
        text(sub, hero.x + int(28 * scale), hero.bottom - int(32 * scale), f_small, MUTED)
        logo(hero.right - int(78 * scale), hero.centery, int(35 * scale))

        start_y = hero.bottom + gap
        cols = 2 if w < int(1000 * scale) else 3
        cw = (w - gap * (cols - 1)) // cols
        ch = int(145 * scale)
        items = [
            ("Generation", "Gen1", f"head {snapshot['head_short']}", GOOD),
            ("Traits", f"{snapshot['traits_ready']} ready", f"{snapshot['traits_total']} registered · {snapshot['traits_planned']} to materialize", GOOD if snapshot["traits_ready"] else WARN),
            ("Runtime", snapshot["runtime_status"], snapshot["runtime_schema"], GOOD),
            ("Network", "Online" if snapshot["online"] else "Offline", snapshot["hostname"], GOOD if snapshot["online"] else BAD),
            ("Trackpad", "Ready" if snapshot["trackpad_ok"] else "Needs repair", f"{snapshot['touchpad_devices']} touchpad · Xorg libinput {'ready' if snapshot['libinput_xorg'] else 'missing'}", GOOD if snapshot["trackpad_ok"] else BAD),
            ("Drivers", snapshot["driver_status"], f"{snapshot['driver_devices']} modeled devices", CYAN),
        ]
        for i, item in enumerate(items):
            row, col = divmod(i, cols)
            rect = pygame.Rect(x + col * (cw + gap), start_y + row * (ch + gap), cw, ch)
            card(rect, *item)

    def draw_traits(x: int, y: int, w: int, h: int):
        traits = list(snapshot.get("traits") or [])
        text("Stable capabilities, adaptive implementation.", x, y, f_small, MUTED)
        cols = 3 if w > int(940 * scale) else 2
        cw = (w - gap * (cols - 1)) // cols
        ch = int(124 * scale)
        sy = y + int(42 * scale)
        if not traits:
            card(pygame.Rect(x, sy, cw, ch), "Traits", "Materializing", "Aurum is still building the human surface", WARN)
            return
        for i, trait in enumerate(traits):
            row, col = divmod(i, cols)
            stage = str(trait.get("stage") or "planned")
            color = GOOD if stage == "foundation-ready" else WARN
            card(
                pygame.Rect(x + col * (cw + gap), sy + row * (ch + gap), cw, ch),
                str(trait.get("id") or "TR8"),
                str(trait.get("name") or "Trait"),
                "foundation ready" if stage == "foundation-ready" else "materialization lane",
                color,
            )

    def draw_detail(x: int, y: int, w: int, h: int, tab: str):
        box = pygame.Rect(x, y, w, h)
        rounded(box, PANEL, 22, LINE)
        text(tab, box.x + int(28 * scale), box.y + int(24 * scale), f_card, GOLD2)
        if tab == "Build":
            rows = [
                ("Branch", snapshot["branch"]),
                ("Head", snapshot["head"]),
                ("Runtime", f"{snapshot['runtime_status']} · {snapshot['runtime_schema']}"),
                ("Autonomy", snapshot["autonomy_status"]),
                ("Completed generations", snapshot["completed_generations"] or "adaptive"),
                ("Next frontier", snapshot["next_gap"]),
            ]
        elif tab == "Hardware":
            rows = [
                ("Machine", snapshot["machine"]),
                ("Display", f"{width} × {height} fullscreen"),
                ("Pointer devices", snapshot["pointer_devices"]),
                ("Touchpads", snapshot["touchpad_devices"]),
                ("Trackpad", "ready" if snapshot["trackpad_ok"] else "repair needed"),
                ("Xorg libinput", "ready" if snapshot["libinput_xorg"] else "missing"),
                ("Wake policy", snapshot["wake_status"]),
                ("Modeled devices", snapshot["driver_devices"]),
            ]
        elif tab == "Field":
            rows = [
                ("Driver lane", snapshot["driver_status"]),
                ("Observed devices", snapshot["driver_devices"]),
                ("Next gap", snapshot["next_gap"]),
                ("Source identity", snapshot["head_short"]),
                ("Mode", "continuous adaptive generation"),
            ]
        else:
            rows = [
                ("Aurum desktop", "Gen1 native physical presentation"),
                ("Refresh", "F5 or click Refresh"),
                ("Recovery console", "Ctrl+Alt+F1"),
                ("Return to desktop", "Ctrl+Alt+F2"),
                ("Host authority", "bounded; no arbitrary shell"),
            ]
        ry = box.y + int(82 * scale)
        for label, value in rows:
            text(label, box.x + int(30 * scale), ry, f_small, MUTED)
            text(_fit(value, 72), box.x + int(245 * scale), ry - int(4 * scale), f_body, TEXT)
            pygame.draw.line(screen, LINE, (box.x + int(28 * scale), ry + int(29 * scale)), (box.right - int(28 * scale), ry + int(29 * scale)))
            ry += int(56 * scale)

    while not STOP_REQUESTED:
        now = time.monotonic()
        if now - last_refresh >= 4.0:
            snapshot = collect_snapshot()
            last_refresh = now

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                STOP_REQUESTED = True
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F5:
                    snapshot = collect_snapshot(); last_refresh = now
                elif event.key == pygame.K_F12:
                    STOP_REQUESTED = True
                elif pygame.K_1 <= event.key <= pygame.K_6:
                    selected = event.key - pygame.K_1
                elif event.key in (pygame.K_LEFT, pygame.K_UP):
                    selected = (selected - 1) % len(tabs)
                elif event.key in (pygame.K_RIGHT, pygame.K_DOWN):
                    selected = (selected + 1) % len(tabs)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                for i in range(len(tabs)):
                    rect = pygame.Rect(int(13 * scale), int((126 + i * 62) * scale), rail_w - int(26 * scale), int(48 * scale))
                    if rect.collidepoint(mx, my):
                        selected = i
                refresh = pygame.Rect(width - int(152 * scale), height - int(54 * scale), int(118 * scale), int(34 * scale))
                if refresh.collidepoint(mx, my):
                    snapshot = collect_snapshot(); last_refresh = now
            elif event.type == pygame.MOUSEWHEEL:
                selected = (selected - event.y) % len(tabs)

        screen.fill(BG)
        pygame.draw.circle(screen, (24, 21, 15), (width - int(100 * scale), int(30 * scale)), int(250 * scale))
        pygame.draw.rect(screen, RAIL, pygame.Rect(0, 0, rail_w, height))
        pygame.draw.line(screen, LINE, (rail_w, 0), (rail_w, height))

        logo(int(50 * scale), int(48 * scale), int(26 * scale))
        text("AURUM", int(92 * scale), int(28 * scale), f_small, GOLD2)
        text("GEN1", int(92 * scale), int(49 * scale), f_micro, MUTED)

        for i, name in enumerate(tabs):
            rect = pygame.Rect(int(13 * scale), int((126 + i * 62) * scale), rail_w - int(26 * scale), int(48 * scale))
            if i == selected:
                rounded(rect, (30, 27, 22), 14, GOLD)
            text(str(i + 1), rect.x + int(11 * scale), rect.y + int(15 * scale), f_micro, GOLD if i == selected else MUTED)
            text(name, rect.x + int(32 * scale), rect.y + int(12 * scale), f_small, GOLD2 if i == selected else MUTED)

        cx = rail_w + margin
        cw = width - cx - margin
        text("AURUM · HOPPER", cx, int(22 * scale), f_small, GOLD)
        text(tabs[selected], cx, int(43 * scale), f_title, TEXT)

        online_color = GOOD if snapshot["online"] else BAD
        chip = pygame.Rect(width - int(188 * scale), int(31 * scale), int(154 * scale), int(37 * scale))
        rounded(chip, (17, 30, 27) if snapshot["online"] else (38, 22, 24), 18, online_color)
        status_dot(chip.x + int(20 * scale), chip.centery, online_color)
        text("ONLINE" if snapshot["online"] else "OFFLINE", chip.x + int(38 * scale), chip.y + int(9 * scale), f_small, online_color)

        content_y = int(112 * scale)
        content_h = height - content_y - int(74 * scale)
        if selected == 0:
            draw_home(cx, content_y, cw, content_h)
        elif selected == 1:
            draw_traits(cx, content_y, cw, content_h)
        else:
            draw_detail(cx, content_y, cw, content_h, tabs[selected])

        footer_y = height - int(45 * scale)
        pygame.draw.line(screen, LINE, (cx, footer_y - int(11 * scale)), (width - margin, footer_y - int(11 * scale)))
        input_text = "Trackpad ready" if snapshot["trackpad_ok"] else "Trackpad repair needed"
        input_color = GOOD if snapshot["trackpad_ok"] else BAD
        status_dot(cx + int(5 * scale), footer_y + int(3 * scale), input_color)
        text(input_text, cx + int(20 * scale), footer_y - int(5 * scale), f_small, input_color)
        text("Ctrl+Alt+F1 recovery", cx + int(190 * scale), footer_y - int(5 * scale), f_small, MUTED)
        refresh = pygame.Rect(width - int(152 * scale), height - int(54 * scale), int(118 * scale), int(34 * scale))
        rounded(refresh, PANEL_HI, 14, LINE)
        text("Refresh  F5", refresh.x + int(18 * scale), refresh.y + int(8 * scale), f_small, GOLD2)

        pygame.display.flip()
        clock.tick(30)

    _atomic_json(DEFAULT_STATE / "desktop-ui.json", {
        "schema": SCHEMA,
        "status": "stopped",
        "machine": "Hopper",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    pygame.quit()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Aurum Gen1 Hopper desktop")
    parser.add_argument("command", nargs="?", default="run", choices=("run",))
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    args = parser.parse_args()
    global DEFAULT_STATE, DEFAULT_RUN
    DEFAULT_STATE = args.state_dir
    DEFAULT_RUN = args.run_dir
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    return _render()


if __name__ == "__main__":
    raise SystemExit(main())
