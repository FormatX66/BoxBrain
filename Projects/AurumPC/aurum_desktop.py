#!/usr/bin/env python3
"""Polished Aurum Gen1 physical desktop for Hopper."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import signal
import time
from pathlib import Path
from typing import Any

SCHEMA = "aurum.desktop.v1"
STOP_REQUESTED = False


def _json(path: Path) -> dict[str, Any]:
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


def _head(workspace: Path) -> str:
    raw = _text(workspace / ".git" / "HEAD", "")
    if raw.startswith("ref: "):
        return _text(workspace / ".git" / raw[5:].strip(), "unknown")
    return raw or "unknown"


def _branch(workspace: Path) -> str:
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
        if len(fields) >= 4 and fields[1] == "00000000":
            try:
                flags = int(fields[3], 16)
            except ValueError:
                continue
            if flags & 1:
                return True
    return False


def _traits(workspace: Path, runtime: Path) -> dict[str, Any]:
    for path in (
        runtime / "aurum_traits.py",
        workspace / "Projects/AurumPC/aurum_traits.py",
    ):
        if not path.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"aurum_traits_{os.getpid()}", path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                result = module.summary()
                if isinstance(result, dict):
                    return result
        except Exception:
            continue
    return {"total": 0, "foundation_ready": 0, "planned": 0, "traits": []}


def snapshot(state: Path, workspace: Path, runtime: Path) -> dict[str, Any]:
    input_state = _json(Path("/run/aurum-input-status.json"))
    touchpads = list(input_state.get("touchpads") or [])
    pointers = list(input_state.get("pointers") or [])
    libinput = input_state.get("libinput") if isinstance(input_state.get("libinput"), dict) else {}
    runtime_state = _json(state / "runtime-update.json")
    autonomy = _json(state / "autonomy.json")
    driver = _json(state / "driver-lab/latest-cycle.json")
    identity = _json(state / "machine-identity.json")
    chain = _json(runtime / "codelation/autobuild/native_chain_state.json")
    traits = _traits(workspace, runtime)
    head = _head(workspace)
    trackpad_ok = bool(
        touchpads
        and all(item.get("present") and item.get("readable") for item in touchpads)
        and (libinput.get("xorg_driver") or input_state.get("status") == "ready")
    )
    return {
        "machine": identity.get("display_name") or "Hopper",
        "hostname": identity.get("hostname") or _text(Path("/etc/hostname"), "hopper"),
        "online": _online(),
        "head": head,
        "head_short": head[:12] if head != "unknown" else "unknown",
        "branch": _branch(workspace),
        "runtime_status": runtime_state.get("status") or "current",
        "runtime_schema": runtime_state.get("schema") or "aurum-pc-runtime-update-v4",
        "autonomy": autonomy.get("status") or "ready",
        "driver": driver.get("status") or "ready",
        "driver_devices": int(driver.get("devices_modeled") or len(driver.get("devices") or [])),
        "pointers": len(pointers),
        "touchpads": len(touchpads),
        "trackpad_ok": trackpad_ok,
        "xorg_libinput": bool(libinput.get("xorg_driver")),
        "generation": chain.get("completed_generations") or 1,
        "next_gap": chain.get("next_gap") or "continuous observation",
        "traits": list(traits.get("traits") or []),
        "traits_total": int(traits.get("total") or 0),
        "traits_ready": int(traits.get("foundation_ready") or 0),
        "traits_planned": int(traits.get("planned") or 0),
    }


def _write_receipt(state: Path, payload: dict[str, Any]) -> None:
    path = state / "desktop-ui.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _stop(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def run(state: Path, run_dir: Path, workspace: Path, runtime: Path) -> int:
    global STOP_REQUESTED
    STOP_REQUESTED = False
    try:
        import pygame
    except Exception as exc:
        _write_receipt(state, {"schema": SCHEMA, "status": "failed", "detail": f"pygame:{exc}"})
        return 1

    pygame.init()
    pygame.font.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    width, height = screen.get_size()
    pygame.display.set_caption("Aurum — Hopper")
    scale = min(width / 1440.0, height / 900.0)

    def font(size: int, bold: bool = False):
        return pygame.font.SysFont("DejaVu Sans", max(11, int(size * scale)), bold=bold)

    tiny, small, body = font(11), font(14), font(18)
    card_font, title_font = font(24, True), font(43, True)
    bg, rail, panel, panel_hi = (7, 9, 14), (10, 12, 18), (16, 20, 28), (21, 26, 36)
    line, gold, gold2 = (54, 58, 70), (236, 190, 78), (255, 224, 147)
    ink, muted, good, bad, cyan = (244, 242, 236), (145, 153, 170), (112, 218, 161), (247, 128, 136), (104, 204, 217)

    def text(value: object, x: int, y: int, face=body, color=ink):
        screen.blit(face.render(str(value), True, color), (x, y))

    def rounded(rect, fill, border=None, radius=18):
        pygame.draw.rect(screen, fill, rect, border_radius=max(5, int(radius * scale)))
        if border:
            pygame.draw.rect(screen, border, rect, width=max(1, int(scale)), border_radius=max(5, int(radius * scale)))

    def logo(cx: int, cy: int, radius: int):
        for i in range(7):
            a = math.tau * i / 7 - math.pi / 2
            leaf = pygame.Surface((max(8, int(radius * .52)), max(14, int(radius * .95))), pygame.SRCALPHA)
            pygame.draw.ellipse(leaf, gold, leaf.get_rect())
            leaf = pygame.transform.rotate(leaf, -math.degrees(a) - 90)
            pos = (cx + int(math.cos(a) * radius * .62), cy + int(math.sin(a) * radius * .62))
            screen.blit(leaf, leaf.get_rect(center=pos))
        pygame.draw.circle(screen, gold2, (cx, cy), max(3, int(radius * .16)))

    def dot(x: int, y: int, color):
        pygame.draw.circle(screen, color, (x, y), max(4, int(5 * scale)))

    def fit(value: object, limit: int = 46) -> str:
        s = " ".join(str(value).split())
        return s if len(s) <= limit else s[: limit - 1] + "…"

    snap = snapshot(state, workspace, runtime)
    start = time.monotonic()
    stages = ["Machine", "Input", "Network", "Runtime", "Desktop"]
    while time.monotonic() - start < 1.8 and not STOP_REQUESTED:
        elapsed = time.monotonic() - start
        screen.fill(bg)
        logo(width // 2, int(height * .34), int(64 * scale))
        label = font(26, True).render("AURUM", True, gold2)
        screen.blit(label, (width // 2 - label.get_width() // 2, int(height * .45)))
        text("Waking Hopper · Gen1", width // 2 - int(95 * scale), int(height * .52), small, muted)
        bx, by = width // 2 - int(180 * scale), int(height * .65)
        readiness = [True, snap["pointers"] > 0, snap["online"], True, True]
        for i, name in enumerate(stages):
            active = elapsed >= i * .22
            color = good if active and readiness[i] else gold if active else line
            dot(bx + i * int(90 * scale), by, color)
            lab = tiny.render(name, True, muted)
            screen.blit(lab, (bx + i * int(90 * scale) - lab.get_width() // 2, by + int(14 * scale)))
        pygame.display.flip()
        pygame.event.pump()
        time.sleep(.03)

    _write_receipt(state, {
        "schema": SCHEMA,
        "ui_version": "gen1-polished-v1",
        "status": "running",
        "pid": os.getpid(),
        "surface": "physical",
        "machine": "Hopper",
        "host_actuation": False,
        "video_driver": os.environ.get("SDL_VIDEODRIVER", "auto"),
        "resolution": [width, height],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })

    rail_w, margin, gap = int(172 * scale), int(34 * scale), int(18 * scale)
    tabs = ["Home", "Traits", "Build", "Hardware", "Field", "Settings"]
    selected, last_refresh = 0, 0.0
    clock = pygame.time.Clock()

    def card(rect, label, value, note, color=gold):
        rounded(rect, panel, line)
        dot(rect.x + int(22 * scale), rect.y + int(24 * scale), color)
        text(label.upper(), rect.x + int(38 * scale), rect.y + int(13 * scale), tiny, muted)
        text(fit(value, 28), rect.x + int(20 * scale), rect.y + int(48 * scale), card_font, ink)
        text(fit(note, 50), rect.x + int(20 * scale), rect.bottom - int(31 * scale), small, muted)

    while not STOP_REQUESTED:
        now = time.monotonic()
        if now - last_refresh >= 4:
            snap = snapshot(state, workspace, runtime)
            last_refresh = now

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                STOP_REQUESTED = True
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F5:
                    snap = snapshot(state, workspace, runtime); last_refresh = now
                elif event.key == pygame.K_F12:
                    STOP_REQUESTED = True
                elif pygame.K_1 <= event.key <= pygame.K_6:
                    selected = event.key - pygame.K_1
                elif event.key in (pygame.K_LEFT, pygame.K_UP):
                    selected = (selected - 1) % len(tabs)
                elif event.key in (pygame.K_RIGHT, pygame.K_DOWN):
                    selected = (selected + 1) % len(tabs)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i in range(len(tabs)):
                    r = pygame.Rect(int(13 * scale), int((126 + i * 62) * scale), rail_w - int(26 * scale), int(48 * scale))
                    if r.collidepoint(event.pos):
                        selected = i
            elif event.type == pygame.MOUSEWHEEL:
                selected = (selected - event.y) % len(tabs)

        screen.fill(bg)
        pygame.draw.circle(screen, (24, 21, 15), (width - int(100 * scale), int(30 * scale)), int(250 * scale))
        pygame.draw.rect(screen, rail, pygame.Rect(0, 0, rail_w, height))
        pygame.draw.line(screen, line, (rail_w, 0), (rail_w, height))
        logo(int(50 * scale), int(48 * scale), int(26 * scale))
        text("AURUM", int(92 * scale), int(28 * scale), small, gold2)
        text("GEN1", int(92 * scale), int(49 * scale), tiny, muted)

        for i, name in enumerate(tabs):
            r = pygame.Rect(int(13 * scale), int((126 + i * 62) * scale), rail_w - int(26 * scale), int(48 * scale))
            if i == selected:
                rounded(r, (30, 27, 22), gold, 14)
            text(str(i + 1), r.x + int(11 * scale), r.y + int(15 * scale), tiny, gold if i == selected else muted)
            text(name, r.x + int(32 * scale), r.y + int(12 * scale), small, gold2 if i == selected else muted)

        cx, cy = rail_w + margin, int(112 * scale)
        cw = width - cx - margin
        text("AURUM · HOPPER", cx, int(22 * scale), small, gold)
        text(tabs[selected], cx, int(43 * scale), title_font, ink)

        online_color = good if snap["online"] else bad
        chip = pygame.Rect(width - int(188 * scale), int(31 * scale), int(154 * scale), int(37 * scale))
        rounded(chip, (17, 30, 27) if snap["online"] else (38, 22, 24), online_color)
        dot(chip.x + int(20 * scale), chip.centery, online_color)
        text("ONLINE" if snap["online"] else "OFFLINE", chip.x + int(38 * scale), chip.y + int(9 * scale), small, online_color)

        if selected == 0:
            hero = pygame.Rect(cx, cy, cw, int(124 * scale))
            rounded(hero, panel_hi, line, 22)
            text("GENERATION ONE", hero.x + int(26 * scale), hero.y + int(21 * scale), tiny, gold)
            text("Hopper is alive.", hero.x + int(26 * scale), hero.y + int(43 * scale), title_font, ink)
            text("Physical desktop online · machine state flowing through Aurum", hero.x + int(28 * scale), hero.bottom - int(32 * scale), small, muted)
            logo(hero.right - int(78 * scale), hero.centery, int(35 * scale))
            items = [
                ("Generation", "Gen1", f"head {snap['head_short']}", good),
                ("Traits", f"{snap['traits_ready']} ready", f"{snap['traits_total']} registered · {snap['traits_planned']} to materialize", good),
                ("Runtime", snap["runtime_status"], snap["runtime_schema"], good),
                ("Network", "Online" if snap["online"] else "Offline", snap["hostname"], online_color),
                ("Trackpad", "Ready" if snap["trackpad_ok"] else "Needs repair", f"{snap['touchpads']} touchpad · libinput {'ready' if snap['xorg_libinput'] else 'missing'}", good if snap["trackpad_ok"] else bad),
                ("Drivers", snap["driver"], f"{snap['driver_devices']} modeled devices", cyan),
            ]
            cols = 3 if cw > int(940 * scale) else 2
            card_w = (cw - gap * (cols - 1)) // cols
            card_h, sy = int(145 * scale), hero.bottom + gap
            for i, item in enumerate(items):
                row, col = divmod(i, cols)
                card(pygame.Rect(cx + col * (card_w + gap), sy + row * (card_h + gap), card_w, card_h), *item)
        elif selected == 1:
            text("Stable capabilities, adaptive implementation.", cx, cy, small, muted)
            traits = list(snap["traits"])
            cols, sy = (3 if cw > int(940 * scale) else 2), cy + int(42 * scale)
            card_w, card_h = (cw - gap * (cols - 1)) // cols, int(124 * scale)
            for i, trait in enumerate(traits):
                row, col = divmod(i, cols)
                stage = str(trait.get("stage") or "planned")
                card(pygame.Rect(cx + col * (card_w + gap), sy + row * (card_h + gap), card_w, card_h), str(trait.get("id") or "TR8"), str(trait.get("name") or "Trait"), "foundation ready" if stage == "foundation-ready" else "materialization lane", good if stage == "foundation-ready" else gold)
        else:
            box = pygame.Rect(cx, cy, cw, height - cy - int(75 * scale))
            rounded(box, panel, line, 22)
            text(tabs[selected], box.x + int(28 * scale), box.y + int(24 * scale), card_font, gold2)
            if tabs[selected] == "Hardware":
                rows = [("Machine", snap["machine"]), ("Display", f"{width} × {height}"), ("Pointers", snap["pointers"]), ("Touchpads", snap["touchpads"]), ("Trackpad", "ready" if snap["trackpad_ok"] else "repair needed"), ("Xorg libinput", "ready" if snap["xorg_libinput"] else "missing"), ("Modeled devices", snap["driver_devices"])]
            elif tabs[selected] == "Build":
                rows = [("Branch", snap["branch"]), ("Head", snap["head"]), ("Runtime", snap["runtime_status"]), ("Autonomy", snap["autonomy"]), ("Generation", snap["generation"]), ("Next frontier", snap["next_gap"])]
            elif tabs[selected] == "Field":
                rows = [("Driver lane", snap["driver"]), ("Observed devices", snap["driver_devices"]), ("Next gap", snap["next_gap"]), ("Mode", "continuous adaptive generation")]
            else:
                rows = [("Aurum desktop", "Gen1 polished physical surface"), ("Refresh", "F5"), ("Recovery", "Ctrl+Alt+F1"), ("Return", "Ctrl+Alt+F2"), ("Authority", "bounded; no arbitrary shell")]
            ry = box.y + int(82 * scale)
            for label, value in rows:
                text(label, box.x + int(30 * scale), ry, small, muted)
                text(fit(value, 72), box.x + int(245 * scale), ry - int(4 * scale), body, ink)
                pygame.draw.line(screen, line, (box.x + int(28 * scale), ry + int(29 * scale)), (box.right - int(28 * scale), ry + int(29 * scale)))
                ry += int(56 * scale)

        footer_y = height - int(42 * scale)
        pygame.draw.line(screen, line, (cx, footer_y - int(12 * scale)), (width - margin, footer_y - int(12 * scale)))
        input_color = good if snap["trackpad_ok"] else bad
        dot(cx + int(5 * scale), footer_y + int(2 * scale), input_color)
        text("Trackpad ready" if snap["trackpad_ok"] else "Trackpad repair needed", cx + int(20 * scale), footer_y - int(6 * scale), small, input_color)
        text("Ctrl+Alt+F1 recovery", cx + int(200 * scale), footer_y - int(6 * scale), small, muted)

        pygame.display.flip()
        clock.tick(30)

    _write_receipt(state, {"schema": SCHEMA, "ui_version": "gen1-polished-v1", "status": "stopped", "machine": "Hopper", "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    pygame.quit()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Aurum Gen1 Hopper desktop")
    parser.add_argument("command", nargs="?", default="run", choices=("run",))
    parser.add_argument("--state-dir", type=Path, default=Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state")))
    parser.add_argument("--run-dir", type=Path, default=Path(os.environ.get("AURUM_RUN_DIR", "/run/aurum")))
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    workspace = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
    runtime = Path(os.environ.get("AURUM_RUNTIME_ROOT", "/opt/aurum"))
    return run(args.state_dir, args.run_dir, workspace, runtime)


if __name__ == "__main__":
    raise SystemExit(main())
