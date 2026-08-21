#!/usr/bin/env python3
"""Aurum's native physical desktop for Hopper.

The desktop is a presentation surface, not a shell. It renders verified local
state and durable user-facing traits, keeps tty1 available as recovery, and
does not expose arbitrary host actuation. The physical launcher owns VT2.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import signal
import sys
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


def _git_branch(workspace: Path) -> str:
    raw = _text(workspace / ".git" / "HEAD", "")
    if raw.startswith("ref: refs/heads/"):
        return raw.removeprefix("ref: refs/heads/").strip()
    return "detached"


def _online() -> bool:
    try:
        routes = Path("/proc/net/route").read_text(encoding="utf-8", errors="replace").splitlines()[1:]
    except OSError:
        return False
    for line in routes:
        fields = line.split()
        if len(fields) < 4 or fields[1] != "00000000":
            continue
        try:
            flags = int(fields[3], 16)
        except ValueError:
            continue
        if not (flags & 0x1):
            continue
        interface = fields[0]
        if _text(Path("/sys/class/net") / interface / "operstate", "down") in {"up", "unknown"}:
            return True
    return False


def _load_traits(workspace: Path, runtime_root: Path) -> dict[str, Any]:
    candidates = (
        runtime_root / "aurum_traits.py",
        workspace / "Projects" / "AurumPC" / "aurum_traits.py",
        Path(__file__).with_name("aurum_traits.py"),
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"aurum_traits_{os.getpid()}_{time.time_ns()}", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            result = module.summary()
            if isinstance(result, dict) and result.get("schema") == "aurum.traits.v1":
                return result
        except Exception:
            continue
    return {
        "schema": "aurum.traits.v1",
        "total": 0,
        "foundation_ready": 0,
        "planned": 0,
        "traits": [],
        "host_actuation": False,
    }


def collect_snapshot(
    *,
    state_dir: Path = DEFAULT_STATE,
    workspace: Path = DEFAULT_WORKSPACE,
    runtime_root: Path = DEFAULT_RUNTIME,
    input_state: Path = Path("/run/aurum-input-status.json"),
) -> dict[str, Any]:
    autonomy = _json_file(state_dir / "autonomy.json")
    runtime = _json_file(state_dir / "runtime-update.json")
    identity = _json_file(state_dir / "machine-identity.json")
    seed = _json_file(state_dir / "seed.json")
    if not seed and (state_dir / "seed.bin").is_file():
        seed = {"status": "seeded"}
    driver = _json_file(state_dir / "driver-lab" / "latest-cycle.json")
    input_status = _json_file(input_state)
    wake_policy = input_status.get("wake_policy") if isinstance(input_status.get("wake_policy"), dict) else {}
    chain = _json_file(runtime_root / "codelation" / "autobuild" / "native_chain_state.json")
    traits = _load_traits(workspace, runtime_root)
    head = _git_head(workspace)
    return {
        "schema": SCHEMA,
        "machine": identity.get("display_name") or "Hopper",
        "hostname": identity.get("hostname") or _text(Path("/etc/hostname"), "hopper"),
        "online": _online(),
        "head": head,
        "head_short": head[:12] if head and head != "unknown" else "unknown",
        "branch": _git_branch(workspace),
        "runtime_schema": runtime.get("schema") or "unknown",
        "runtime_status": runtime.get("status") or "unknown",
        "autonomy_status": autonomy.get("status") or "unknown",
        "autonomy_unattended": bool(autonomy.get("unattended")),
        "seed_status": seed.get("status") or seed.get("state") or "unknown",
        "driver_status": driver.get("status") or "ready",
        "driver_devices": len(driver.get("devices") or driver.get("queue") or []),
        "input_status": input_status.get("status") or "unknown",
        "pointer_devices": len(input_status.get("pointers") or []),
        "touchpad_devices": len(input_status.get("touchpads") or []),
        "input_wake_status": wake_policy.get("status") or "unknown",
        "completed_generations": chain.get("completed_generations"),
        "next_gap": chain.get("next_gap") or "continuous observation",
        "traits": list(traits.get("traits") or []),
        "traits_total": int(traits.get("total") or 0),
        "traits_foundation_ready": int(traits.get("foundation_ready") or 0),
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

    scale = min(width / 1440.0, height / 900.0)

    def font(size: int, bold: bool = False):
        return pygame.font.SysFont("DejaVu Sans", max(11, int(size * scale)), bold=bold)

    f_tiny = font(12)
    f_small = font(15)
    f_body = font(19)
    f_card = font(25, True)
    f_title = font(46, True)
    f_mark = font(34, True)

    bg = (8, 10, 15)
    rail_bg = (10, 12, 18)
    panel = (18, 22, 31)
    panel2 = (23, 28, 39)
    selected_bg = (34, 30, 22)
    line = (66, 58, 39)
    selected_line = (96, 78, 39)
    gold = (245, 196, 81)
    gold_soft = (255, 230, 160)
    ink = (246, 242, 232)
    muted = (158, 165, 181)
    good = (121, 220, 167)
    warn = (245, 196, 81)
    danger = (255, 140, 140)

    rail_w = int(148 * scale)
    margin = int(34 * scale)
    gap = int(18 * scale)
    top_h = int(112 * scale)
    bottom_h = int(70 * scale)
    tab_names = ["Home", "Traits", "Build", "Hardware", "Field", "Settings"]
    selected = 0
    last_refresh = 0.0
    focus_gained = getattr(pygame, "WINDOWFOCUSGAINED", -1)
    snapshot = collect_snapshot()
    clock = pygame.time.Clock()

    def rounded(rect, color, radius=18, border=None):
        pygame.draw.rect(screen, color, rect, border_radius=max(4, int(radius * scale)))
        if border:
            pygame.draw.rect(
                screen,
                border,
                rect,
                width=max(1, int(scale)),
                border_radius=max(4, int(radius * scale)),
            )

    def text(surface_text, pos, color=ink, face=f_body):
        screen.blit(face.render(str(surface_text), True, color), pos)

    def card(rect, title, value, note, status_color=gold):
        rounded(rect, panel, 18, line)
        x, y, _w, h = rect
        pygame.draw.circle(
            screen,
            status_color,
            (x + int(22 * scale), y + int(24 * scale)),
            max(3, int(5 * scale)),
        )
        text(title.upper(), (x + int(38 * scale), y + int(13 * scale)), muted, f_tiny)
        text(_fit(value, 30), (x + int(20 * scale), y + int(48 * scale)), ink, f_card)
        text(_fit(note, 52), (x + int(20 * scale), y + h - int(30 * scale)), muted, f_small)

    def draw_home(content):
        x, y, w, _h = content
        cols = 3 if w > int(940 * scale) else 2
        card_w = (w - gap * (cols - 1)) // cols
        card_h = int(154 * scale)
        cards = [
            ("Generation", "Gen1", f"head {snapshot['head_short']}", good),
            (
                "Traits",
                f"{snapshot['traits_foundation_ready']} ready",
                f"{snapshot['traits_total']} registered · {snapshot['traits_planned']} to materialize",
                good if snapshot["traits_foundation_ready"] else warn,
            ),
            (
                "Autonomy",
                snapshot["autonomy_status"],
                "unattended" if snapshot["autonomy_unattended"] else "operator present",
                good if snapshot["autonomy_status"] == "cycle-complete" else warn,
            ),
            (
                "Runtime",
                snapshot["runtime_status"],
                snapshot["runtime_schema"],
                good if snapshot["runtime_status"] in {"current", "updated"} else warn,
            ),
            (
                "Network",
                "Online" if snapshot["online"] else "Offline",
                snapshot["hostname"],
                good if snapshot["online"] else danger,
            ),
            (
                "Seed",
                snapshot["seed_status"],
                "Codelation local seed",
                good if snapshot["seed_status"] in {"seeded", "ready"} else warn,
            ),
        ]
        for index, data in enumerate(cards):
            row, col = divmod(index, cols)
            rect = pygame.Rect(
                x + col * (card_w + gap),
                y + row * (card_h + gap),
                card_w,
                card_h,
            )
            card(rect, *data)

    def draw_traits(content):
        x, y, w, h = content
        traits = list(snapshot.get("traits") or [])
        cols = 2 if w < int(1050 * scale) else 3
        rows = max(1, (len(traits) + cols - 1) // cols)
        card_w = (w - gap * (cols - 1)) // cols
        available_h = h - int(54 * scale)
        card_h = max(int(106 * scale), min(int(142 * scale), (available_h - gap * max(0, rows - 1)) // rows))
        text(
            "Capabilities stay stable while their implementation can evolve underneath them.",
            (x, y),
            muted,
            f_small,
        )
        start_y = y + int(42 * scale)
        for index, trait in enumerate(traits):
            row, col = divmod(index, cols)
            rect = pygame.Rect(
                x + col * (card_w + gap),
                start_y + row * (card_h + gap),
                card_w,
                card_h,
            )
            stage = str(trait.get("stage") or "planned")
            color = good if stage == "foundation-ready" else warn
            note = "foundation ready" if stage == "foundation-ready" else "next materialization lane"
            card(
                rect,
                str(trait.get("id") or "TR8"),
                str(trait.get("name") or "Trait"),
                note,
                color,
            )

    def draw_detail(content, tab):
        x, y, w, h = content
        rounded(pygame.Rect(x, y, w, h), panel, 22, line)
        text(tab, (x + int(28 * scale), y + int(24 * scale)), gold_soft, f_card)
        rows: list[tuple[str, object]]
        if tab == "Build":
            rows = [
                ("Branch", snapshot["branch"]),
                ("Current head", snapshot["head"]),
                ("Autonomy", snapshot["autonomy_status"]),
                ("Runtime", f"{snapshot['runtime_status']} · {snapshot['runtime_schema']}"),
                (
                    "Completed native generations",
                    snapshot["completed_generations"]
                    if snapshot["completed_generations"] is not None
                    else "adaptive",
                ),
                ("Next frontier", snapshot["next_gap"]),
            ]
        elif tab == "Hardware":
            rows = [
                ("Machine", snapshot["machine"]),
                ("Hostname", snapshot["hostname"]),
                ("Display", f"{width} × {height} fullscreen"),
                ("Physical surface", "VT2 · pygame"),
                ("Input route", os.environ.get("SDL_VIDEODRIVER", "auto")),
                ("Pointer devices", snapshot["pointer_devices"]),
                ("Trackpads", snapshot["touchpad_devices"]),
                ("Wake policy", snapshot["input_wake_status"]),
                ("Modeled devices", snapshot["driver_devices"]),
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
                ("Aurum desktop", "native physical presentation v2"),
                ("Traits", f"{snapshot['traits_total']} registered"),
                ("Refresh", "F5 or click Refresh"),
                ("Recovery console", "Ctrl+Alt+F1"),
                ("Return to desktop", "Ctrl+Alt+F2"),
                ("Host authority", "bounded; no arbitrary shell"),
            ]
        ry = y + int(84 * scale)
        for label, value in rows:
            text(label, (x + int(30 * scale), ry), muted, f_small)
            text(_fit(value, 72), (x + int(255 * scale), ry - int(4 * scale)), ink, f_body)
            pygame.draw.line(
                screen,
                line,
                (x + int(28 * scale), ry + int(30 * scale)),
                (x + w - int(28 * scale), ry + int(30 * scale)),
            )
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
                elif pygame.K_1 <= event.key <= pygame.K_6:
                    selected = event.key - pygame.K_1
                elif event.key in (pygame.K_LEFT, pygame.K_UP):
                    selected = (selected - 1) % len(tab_names)
                elif event.key in (pygame.K_RIGHT, pygame.K_DOWN):
                    selected = (selected + 1) % len(tab_names)
            if event.type == focus_gained:
                snapshot = collect_snapshot()
                last_refresh = now
            if event.type == pygame.MOUSEWHEEL:
                selected = (selected - event.y) % len(tab_names)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                for i in range(len(tab_names)):
                    by = int((126 + i * 62) * scale)
                    rect = pygame.Rect(
                        int(12 * scale),
                        by,
                        rail_w - int(24 * scale),
                        int(48 * scale),
                    )
                    if rect.collidepoint(mx, my):
                        selected = i
                refresh_rect = pygame.Rect(
                    width - int(150 * scale),
                    height - int(56 * scale),
                    int(118 * scale),
                    int(36 * scale),
                )
                if refresh_rect.collidepoint(mx, my):
                    snapshot = collect_snapshot()
                    last_refresh = now

        screen.fill(bg)
        pygame.draw.circle(
            screen,
            (28, 24, 16),
            (width - int(130 * scale), int(70 * scale)),
            int(220 * scale),
        )

        pygame.draw.rect(screen, rail_bg, pygame.Rect(0, 0, rail_w, height))
        pygame.draw.line(screen, line, (rail_w, 0), (rail_w, height))
        mark = pygame.Rect(
            int(21 * scale),
            int(20 * scale),
            int(66 * scale),
            int(66 * scale),
        )
        rounded(mark, gold, 20)
        text("A", (mark.x + int(19 * scale), mark.y + int(11 * scale)), (23, 17, 6), f_mark)
        text("AURUM", (int(95 * scale), int(32 * scale)), gold_soft, f_small)
        text("GEN1", (int(95 * scale), int(52 * scale)), muted, f_tiny)

        for i, name in enumerate(tab_names):
            by = int((126 + i * 62) * scale)
            rect = pygame.Rect(
                int(12 * scale),
                by,
                rail_w - int(24 * scale),
                int(48 * scale),
            )
            if i == selected:
                rounded(rect, selected_bg, 14, selected_line)
            number_color = gold if i == selected else muted
            label_color = gold_soft if i == selected else muted
            text(str(i + 1), (rect.x + int(10 * scale), rect.y + int(14 * scale)), number_color, f_tiny)
            text(name, (rect.x + int(30 * scale), rect.y + int(12 * scale)), label_color, f_small)

        cx = rail_w + margin
        cw = width - cx - margin
        text("AURUM · HOPPER", (cx, int(22 * scale)), gold, f_small)
        text(tab_names[selected], (cx, int(43 * scale)), ink, f_title)

        status = "ONLINE" if snapshot["online"] else "OFFLINE"
        status_color = good if snapshot["online"] else danger
        chip = pygame.Rect(
            width - int(188 * scale),
            int(32 * scale),
            int(154 * scale),
            int(36 * scale),
        )
        rounded(chip, (18, 31, 28) if snapshot["online"] else (38, 22, 23), 18, status_color)
        pygame.draw.circle(
            screen,
            status_color,
            (chip.x + int(19 * scale), chip.centery),
            max(3, int(5 * scale)),
        )
        text(status, (chip.x + int(34 * scale), chip.y + int(8 * scale)), status_color, f_small)

        content = pygame.Rect(cx, top_h, cw, height - top_h - bottom_h)
        if selected == 0:
            draw_home(content)
        elif tab_names[selected] == "Traits":
            draw_traits(content)
        else:
            draw_detail(content, tab_names[selected])

        pygame.draw.line(screen, line, (rail_w, height - bottom_h), (width, height - bottom_h))
        footer = "Gen1 · traits are capabilities, not apps · Ctrl+Alt+F1 recovery"
        text(footer, (cx, height - int(45 * scale)), muted, f_small)
        refresh_rect = pygame.Rect(
            width - int(150 * scale),
            height - int(56 * scale),
            int(118 * scale),
            int(36 * scale),
        )
        rounded(refresh_rect, panel2, 14, line)
        text("Refresh  F5", (refresh_rect.x + int(13 * scale), refresh_rect.y + int(9 * scale)), gold_soft, f_small)

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
        "status": "launching",
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
