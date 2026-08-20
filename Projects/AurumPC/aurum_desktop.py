#!/usr/bin/env python3
"""Aurum's native physical desktop for Hopper.

The desktop is a presentation surface, not a shell. It renders local Aurum
state directly with pygame, keeps tty1 available as the recovery console, and
does not expose arbitrary host actuation. The physical launcher owns VT2.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path
from typing import Any

SCHEMA = "aurum.desktop.v1"
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
    head = workspace / ".git" / "HEAD"
    raw = _text(head, "")
    if not raw:
        return "unknown"
    if raw.startswith("ref: "):
        ref = raw[5:].strip()
        return _text(workspace / ".git" / ref, "unknown")
    return raw


def _online() -> bool:
    try:
        routes = Path("/proc/net/route").read_text(encoding="utf-8", errors="replace").splitlines()[1:]
    except OSError:
        return False
    for line in routes:
        fields = line.split()
        if len(fields) < 4 or fields[1] != "00000000":
            continue
        interface = fields[0]
        try:
            flags = int(fields[3], 16)
        except ValueError:
            continue
        if not (flags & 0x1):
            continue
        if _text(Path("/sys/class/net") / interface / "operstate", "down") in {"up", "unknown"}:
            return True
    return False


def collect_snapshot(
    *,
    state_dir: Path = DEFAULT_STATE,
    workspace: Path = DEFAULT_WORKSPACE,
    runtime_root: Path = DEFAULT_RUNTIME,
) -> dict[str, Any]:
    autonomy = _json_file(state_dir / "autonomy.json")
    runtime = _json_file(state_dir / "runtime-update.json")
    identity = _json_file(state_dir / "machine-identity.json")
    seed = _json_file(state_dir / "seed.json")
    if not seed and (state_dir / "seed.bin").is_file():
        seed = {"status": "seeded"}
    driver = _json_file(state_dir / "driver-lab" / "latest-cycle.json")
    chain = _json_file(runtime_root / "codelation" / "autobuild" / "native_chain_state.json")
    head = _git_head(workspace)
    return {
        "schema": SCHEMA,
        "machine": identity.get("display_name") or "Hopper",
        "hostname": identity.get("hostname") or _text(Path("/etc/hostname"), "hopper"),
        "online": _online(),
        "head": head,
        "head_short": head[:12] if head and head != "unknown" else "unknown",
        "branch": "aurum/trunk-v0.01",
        "runtime_schema": runtime.get("schema") or "unknown",
        "runtime_status": runtime.get("status") or "unknown",
        "autonomy_status": autonomy.get("status") or "unknown",
        "autonomy_unattended": bool(autonomy.get("unattended")),
        "seed_status": seed.get("status") or seed.get("state") or "unknown",
        "driver_status": driver.get("status") or "ready",
        "driver_devices": len(driver.get("devices") or driver.get("queue") or []),
        "completed_generations": chain.get("completed_generations"),
        "next_gap": chain.get("next_gap") or "continuous observation",
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


def _fit(text: object, limit: int) -> str:
    value = " ".join(str(text).split())
    return value if len(value) <= limit else value[: max(1, limit - 1)] + "…"


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
    if width < 800 or height < 480:
        raise RuntimeError(f"physical display too small: {width}x{height}")
    pygame.display.set_caption("Aurum — Hopper")

    scale = min(width / 1440.0, height / 900.0)

    def font(size: int, bold: bool = False):
        return pygame.font.SysFont("DejaVu Sans", max(12, int(size * scale)), bold=bold)

    f_small = font(15)
    f_body = font(19)
    f_card = font(25, True)
    f_title = font(48, True)
    f_mark = font(34, True)

    bg = (8, 10, 15)
    panel = (18, 22, 31)
    panel2 = (23, 28, 39)
    line = (66, 58, 39)
    gold = (245, 196, 81)
    gold_soft = (255, 230, 160)
    ink = (246, 242, 232)
    muted = (158, 165, 181)
    good = (121, 220, 167)
    warn = (245, 196, 81)
    danger = (255, 140, 140)

    rail_w = int(108 * scale)
    margin = int(34 * scale)
    gap = int(18 * scale)
    top_h = int(118 * scale)
    bottom_h = int(74 * scale)
    tab_names = ["Home", "Build", "Hardware", "Field", "Settings"]
    selected = 0
    last_refresh = 0.0
    snapshot = collect_snapshot()
    clock = pygame.time.Clock()

    def rounded(rect, color, radius=18, border=None):
        pygame.draw.rect(screen, color, rect, border_radius=max(4, int(radius * scale)))
        if border:
            pygame.draw.rect(screen, border, rect, width=max(1, int(scale)), border_radius=max(4, int(radius * scale)))

    def text(surface_text, pos, color=ink, face=f_body):
        screen.blit(face.render(str(surface_text), True, color), pos)

    def card(rect, title, value, note, status_color=gold):
        rounded(rect, panel, 18, line)
        x, y, w, h = rect
        pygame.draw.circle(screen, status_color, (x + int(22 * scale), y + int(24 * scale)), max(3, int(5 * scale)))
        text(title.upper(), (x + int(38 * scale), y + int(13 * scale)), muted, f_small)
        text(_fit(value, 28), (x + int(20 * scale), y + int(49 * scale)), ink, f_card)
        text(_fit(note, 44), (x + int(20 * scale), y + h - int(31 * scale)), muted, f_small)

    def draw_home(content):
        x, y, w, h = content
        cols = 3 if w > int(1000 * scale) else 2
        card_w = (w - gap * (cols - 1)) // cols
        card_h = int(154 * scale)
        cards = [
            ("Generation", "Gen1", f"head {snapshot['head_short']}", good),
            ("Autonomy", snapshot["autonomy_status"], "unattended" if snapshot["autonomy_unattended"] else "operator present", good if snapshot["autonomy_status"] == "cycle-complete" else warn),
            ("Runtime", snapshot["runtime_status"], snapshot["runtime_schema"], good if snapshot["runtime_status"] in {"current", "updated"} else warn),
            ("Network", "Online" if snapshot["online"] else "Offline", snapshot["hostname"], good if snapshot["online"] else danger),
            ("Seed", snapshot["seed_status"], "Codelation local seed", good if snapshot["seed_status"] in {"seeded", "ready"} else warn),
            ("Drivers", snapshot["driver_status"], f"{snapshot['driver_devices']} modeled/queued", good),
        ]
        for index, data in enumerate(cards):
            row, col = divmod(index, cols)
            rect = pygame.Rect(x + col * (card_w + gap), y + row * (card_h + gap), card_w, card_h)
            card(rect, *data)

    def draw_detail(content, tab):
        x, y, w, h = content
        rounded(pygame.Rect(x, y, w, h), panel, 22, line)
        text(tab, (x + int(28 * scale), y + int(24 * scale)), gold_soft, f_card)
        rows: list[tuple[str, object]] = []
        if tab == "Build":
            rows = [
                ("Branch", snapshot["branch"]),
                ("Current head", snapshot["head"]),
                ("Autonomy", snapshot["autonomy_status"]),
                ("Runtime", f"{snapshot['runtime_status']} · {snapshot['runtime_schema']}"),
                ("Completed native generations", snapshot["completed_generations"] if snapshot["completed_generations"] is not None else "adaptive"),
                ("Next frontier", snapshot["next_gap"]),
            ]
        elif tab == "Hardware":
            rows = [
                ("Machine", snapshot["machine"]),
                ("Hostname", snapshot["hostname"]),
                ("Display", f"{width} × {height} fullscreen"),
                ("Physical surface", "VT2 · pygame"),
                ("Recovery console", "Ctrl+Alt+F1"),
                ("Network", "online" if snapshot["online"] else "offline"),
            ]
        elif tab == "Field":
            rows = [
                ("Seed", snapshot["seed_status"]),
                ("Driver lane", snapshot["driver_status"]),
                ("Observed devices", snapshot["driver_devices"]),
                ("Next gap", snapshot["next_gap"]),
                ("Source identity", snapshot["head_short"]),
                ("Mode", "continuous adaptive generation"),
            ]
        else:
            rows = [
                ("Aurum desktop", "native physical presentation v1"),
                ("Refresh", "F5 or click Refresh"),
                ("Recovery console", "Ctrl+Alt+F1"),
                ("Return to desktop", "Ctrl+Alt+F2"),
                ("Exit desktop process", "F12"),
                ("Host authority", "bounded; no arbitrary shell"),
            ]
        ry = y + int(84 * scale)
        for label, value in rows:
            text(label, (x + int(30 * scale), ry), muted, f_small)
            text(_fit(value, 72), (x + int(250 * scale), ry - int(4 * scale)), ink, f_body)
            pygame.draw.line(screen, line, (x + int(28 * scale), ry + int(30 * scale)), (x + w - int(28 * scale), ry + int(30 * scale)))
            ry += int(58 * scale)

    while not STOP_REQUESTED:
        now = time.monotonic()
        if now - last_refresh >= 4.0:
            snapshot = collect_snapshot()
            last_refresh = now

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return 0
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F5:
                    snapshot = collect_snapshot()
                    last_refresh = now
                elif event.key == pygame.K_F12:
                    return 0
                elif pygame.K_1 <= event.key <= pygame.K_5:
                    selected = event.key - pygame.K_1
                elif event.key in (pygame.K_LEFT, pygame.K_UP):
                    selected = (selected - 1) % len(tab_names)
                elif event.key in (pygame.K_RIGHT, pygame.K_DOWN):
                    selected = (selected + 1) % len(tab_names)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                for i in range(len(tab_names)):
                    by = int((145 + i * 72) * scale)
                    rect = pygame.Rect(int(13 * scale), by, rail_w - int(26 * scale), int(54 * scale))
                    if rect.collidepoint(mx, my):
                        selected = i
                refresh_rect = pygame.Rect(width - int(150 * scale), height - int(58 * scale), int(118 * scale), int(38 * scale))
                if refresh_rect.collidepoint(mx, my):
                    snapshot = collect_snapshot()
                    last_refresh = now

        screen.fill(bg)
        pygame.draw.circle(screen, (28, 24, 16), (width - int(130 * scale), int(70 * scale)), int(220 * scale))

        pygame.draw.rect(screen, (10, 12, 18), pygame.Rect(0, 0, rail_w, height))
        pygame.draw.line(screen, line, (rail_w, 0), (rail_w, height))
        mark = pygame.Rect(int(21 * scale), int(22 * scale), int(66 * scale), int(66 * scale))
        rounded(mark, gold, 20)
        text("A", (mark.x + int(19 * scale), mark.y + int(11 * scale)), (23, 17, 6), f_mark)
        for i, name in enumerate(tab_names):
            by = int((145 + i * 72) * scale)
            rect = pygame.Rect(int(13 * scale), by, rail_w - int(26 * scale), int(54 * scale))
            if i == selected:
                rounded(rect, (34, 30, 22), 15, (96, 78, 39))
            text(str(i + 1), (rect.x + int(9 * scale), rect.y + int(15 * scale)), gold if i == selected else muted, f_small)
            text(name[:4], (rect.x + int(28 * scale), rect.y + int(15 * scale)), gold_soft if i == selected else muted, f_small)

        cx = rail_w + margin
        cw = width - cx - margin
        text("AURUM · HOPPER", (cx, int(25 * scale)), gold, f_small)
        text(tab_names[selected], (cx, int(48 * scale)), ink, f_title)
        status = "ONLINE" if snapshot["online"] else "OFFLINE"
        status_color = good if snapshot["online"] else danger
        chip = pygame.Rect(width - int(188 * scale), int(34 * scale), int(154 * scale), int(38 * scale))
        rounded(chip, (18, 31, 28) if snapshot["online"] else (38, 22, 23), 19, status_color)
        pygame.draw.circle(screen, status_color, (chip.x + int(19 * scale), chip.centery), max(3, int(5 * scale)))
        text(status, (chip.x + int(34 * scale), chip.y + int(9 * scale)), status_color, f_small)

        content = pygame.Rect(cx, top_h, cw, height - top_h - bottom_h)
        if selected == 0:
            draw_home(content)
        else:
            draw_detail(content, tab_names[selected])

        pygame.draw.line(screen, line, (rail_w, height - bottom_h), (width, height - bottom_h))
        text("Aurum Gen1 · native physical desktop · Ctrl+Alt+F1 recovery console", (cx, height - int(48 * scale)), muted, f_small)
        refresh_rect = pygame.Rect(width - int(150 * scale), height - int(58 * scale), int(118 * scale), int(38 * scale))
        rounded(refresh_rect, panel2, 14, line)
        text("Refresh  F5", (refresh_rect.x + int(13 * scale), refresh_rect.y + int(10 * scale)), gold_soft, f_small)

        pygame.display.flip()
        clock.tick(30)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aurum native physical desktop")
    parser.add_argument("command", nargs="?", choices=("run", "snapshot"), default="run")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    global DEFAULT_STATE, DEFAULT_RUN
    DEFAULT_STATE = args.state_dir
    DEFAULT_RUN = args.run_dir
    if args.command == "snapshot":
        print(json.dumps(collect_snapshot(state_dir=args.state_dir), sort_keys=True))
        return 0

    args.run_dir.mkdir(parents=True, exist_ok=True)
    pid_path = args.run_dir / "aurum-desktop.pid"
    state_path = args.state_dir / "desktop-ui.json"
    pid_path.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    _atomic_json(state_path, {
        "schema": SCHEMA,
        "status": "running",
        "pid": os.getpid(),
        "surface": "physical",
        "machine": "Hopper",
        "host_actuation": False,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    try:
        return _render()
    finally:
        pid_path.unlink(missing_ok=True)
        _atomic_json(state_path, {
            "schema": SCHEMA,
            "status": "stopped",
            "surface": "physical",
            "machine": "Hopper",
            "host_actuation": False,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })


if __name__ == "__main__":
    raise SystemExit(main())
