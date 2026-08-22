#!/usr/bin/env python3
"""Aurum Native GUI physical desktop for Hopper.

The desktop is an evidence surface: values are measured from Hopper or shown as
unknown.  It never substitutes decorative percentages or optimistic labels for
missing machine evidence.

Ctrl+Alt+F1 recovery remains a bounded physical recovery path.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import math
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

SCHEMA = "aurum.desktop.gen1-polished-physical-surface"
GENERATION_NAME = "Gen1 polished physical surface"
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


def _run_text(arguments: list[str], timeout: float = 1.5) -> str:
    try:
        result = subprocess.run(
            arguments,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _head(workspace: Path) -> str:
    raw = _text(workspace / ".git" / "HEAD", "")
    if raw.startswith("ref: "):
        return _text(workspace / ".git" / raw[5:].strip(), "unknown")
    return raw or "unknown"


def _branch(workspace: Path) -> str:
    raw = _text(workspace / ".git" / "HEAD", "")
    if raw.startswith("ref: refs/heads/"):
        return raw.removeprefix("ref: refs/heads/").strip()
    return "detached" if raw else "unknown"


def _online() -> bool:
    try:
        routes = Path("/proc/net/route").read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()[1:]
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
        if flags & 1:
            return True
    return False


def _battery_status() -> dict[str, Any]:
    root = Path("/sys/class/power_supply")
    try:
        batteries = sorted(
            entry
            for entry in root.iterdir()
            if entry.name.upper().startswith("BAT") and (entry / "capacity").is_file()
        )
    except OSError:
        batteries = []
    if not batteries:
        return {
            "present": False,
            "percent": None,
            "status": "Unavailable",
            "charging": False,
            "minutes_remaining": None,
            "name": None,
        }
    bat = batteries[0]
    try:
        percent = max(0, min(100, int(_text(bat / "capacity", "0"))))
    except ValueError:
        percent = None
    status = _text(bat / "status", "Unknown")
    charging = status.lower() in {"charging", "full"}
    minutes = None
    try:
        energy_now = float(_text(bat / "energy_now", "0"))
        power_now = float(_text(bat / "power_now", "0"))
        if power_now > 0 and status.lower() == "discharging":
            minutes = int((energy_now / power_now) * 60)
    except ValueError:
        pass
    return {
        "present": True,
        "percent": percent,
        "status": status,
        "charging": charging,
        "minutes_remaining": minutes,
        "name": bat.name,
    }


def _wifi_status() -> dict[str, Any]:
    root = Path("/sys/class/net")
    try:
        interfaces = [
            entry.name
            for entry in sorted(root.iterdir(), key=lambda p: p.name)
            if (entry / "wireless").exists() or entry.name.startswith("wl")
        ]
    except OSError:
        interfaces = []
    if not interfaces:
        return {
            "present": False,
            "connected": False,
            "interface": None,
            "ssid": None,
            "signal": None,
            "ip": None,
            "operstate": "missing",
        }
    interface = interfaces[0]
    operstate = _text(root / interface / "operstate", "unknown")
    signal_strength = None
    try:
        for line in Path("/proc/net/wireless").read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            if line.lstrip().startswith(interface + ":"):
                quality = float(line.split()[2].rstrip("."))
                signal_strength = max(0, min(100, int((quality / 70.0) * 100)))
                break
    except (OSError, ValueError, IndexError):
        pass

    ssid = ""
    iwgetid = shutil.which("iwgetid")
    if iwgetid:
        ssid = _run_text([iwgetid, interface, "-r"])
    if not ssid:
        iw = shutil.which("iw")
        if iw:
            for line in _run_text([iw, "dev", interface, "link"]).splitlines():
                stripped = line.strip()
                if stripped.startswith("SSID:"):
                    ssid = stripped.split(":", 1)[1].strip()
                    break

    ip_addr = None
    ip = shutil.which("ip")
    if ip:
        out = _run_text([ip, "-4", "-o", "addr", "show", "dev", interface])
        for token in out.split():
            if "/" in token and token[:1].isdigit():
                ip_addr = token.split("/", 1)[0]
                break
    connected = bool(ssid and operstate == "up")
    return {
        "present": True,
        "connected": connected,
        "interface": interface,
        "ssid": ssid or None,
        "signal": signal_strength,
        "ip": ip_addr,
        "operstate": operstate,
    }


def _cpu_percent(sample_seconds: float = 0.08) -> int | None:
    def read() -> tuple[int, int] | None:
        try:
            fields = Path("/proc/stat").read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()[0].split()
            values = [int(value) for value in fields[1:]]
        except (OSError, ValueError, IndexError):
            return None
        if len(values) < 4:
            return None
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return sum(values), idle

    first = read()
    if first is None:
        return None
    time.sleep(max(0.01, sample_seconds))
    second = read()
    if second is None:
        return None
    total_delta = second[0] - first[0]
    idle_delta = second[1] - first[1]
    if total_delta <= 0:
        return None
    return max(0, min(100, round((1.0 - idle_delta / total_delta) * 100)))


def _memory_percent() -> int | None:
    values: dict[str, int] = {}
    try:
        for raw in Path("/proc/meminfo").read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            if ":" not in raw:
                continue
            key, rest = raw.split(":", 1)
            token = rest.strip().split()[0]
            values[key] = int(token)
    except (OSError, ValueError, IndexError):
        return None
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if not total or available is None:
        return None
    return max(0, min(100, round((1.0 - available / total) * 100)))


def _storage_percent() -> int | None:
    try:
        usage = shutil.disk_usage("/")
    except OSError:
        return None
    if usage.total <= 0:
        return None
    return max(0, min(100, round(usage.used / usage.total * 100)))


def _gpu_percent() -> int | None:
    candidates = sorted(Path("/sys/class/drm").glob("card*/device/gpu_busy_percent"))
    for path in candidates:
        try:
            return max(0, min(100, int(path.read_text(encoding="utf-8").strip())))
        except (OSError, ValueError):
            continue
    return None


def _power_profile() -> str | None:
    tool = shutil.which("powerprofilesctl")
    if not tool:
        return None
    value = _run_text([tool, "get"])
    return value or None


def _traits(workspace: Path, runtime: Path) -> dict[str, Any]:
    for path in (
        runtime / "aurum_traits.py",
        workspace / "Projects/AurumPC/aurum_traits.py",
    ):
        if not path.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"aurum_traits_{os.getpid()}", path
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                result = module.summary()
                if isinstance(result, dict):
                    return result
        except Exception:
            continue
    return {"total": 0, "foundation_ready": 0, "planned": 0, "traits": []}


def _time_module(workspace: Path, runtime: Path):
    for path in (
        runtime / "aurum_time.py",
        workspace / "Projects/AurumPC/aurum_time.py",
    ):
        if not path.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"aurum_time_{os.getpid()}", path
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
        except Exception:
            continue
    return None


def _time_status(workspace: Path, runtime: Path) -> dict[str, Any]:
    module = _time_module(workspace, runtime)
    if module and hasattr(module, "time_status"):
        try:
            result = module.time_status()
            if isinstance(result, dict):
                return result
        except Exception:
            pass
    epoch = time.time()
    local = dt.datetime.fromtimestamp(epoch).astimezone()
    return {
        "schema": "aurum.time-status.v1",
        "epoch": epoch,
        "local_iso": local.isoformat(timespec="seconds"),
        "timezone": str(local.tzinfo or "local"),
        "synchronized": False,
        "source": "local-unsynchronized",
        "server_name": None,
        "server_address": None,
        "authoritative": False,
    }


def _request_time_sync(workspace: Path, runtime: Path, timeout_seconds: int = 5) -> dict[str, Any]:
    module = _time_module(workspace, runtime)
    if module and hasattr(module, "synchronize_clock"):
        try:
            result = module.synchronize_clock(timeout_seconds=timeout_seconds)
            if isinstance(result, dict):
                return result
        except Exception as exc:
            return {"status": "failed", "detail": f"{type(exc).__name__}:{exc}"}
    return {"status": "unavailable", "detail": "aurum_time helper unavailable"}


def _current_vt() -> str | None:
    tool = shutil.which("fgconsole")
    if not tool:
        return None
    value = _run_text([tool], timeout=1)
    return value or None


def snapshot(state: Path, workspace: Path, runtime: Path) -> dict[str, Any]:
    input_state = _json(Path("/run/aurum-input-status.json"))
    touchpads = list(input_state.get("touchpads") or [])
    pointers = list(input_state.get("pointers") or [])
    keyboards = list(input_state.get("keyboards") or [])
    libinput = (
        input_state.get("libinput")
        if isinstance(input_state.get("libinput"), dict)
        else {}
    )
    runtime_state = _json(state / "runtime-update.json")
    autonomy = _json(state / "autonomy.json")
    driver = _json(state / "driver-lab/latest-cycle.json")
    identity = _json(state / "machine-identity.json")
    chain = _json(runtime / "codelation/autobuild/native_chain_state.json")
    traits = _traits(workspace, runtime)
    pointer_proof = _json(state / "pointer-motion.json")
    head = _head(workspace)

    trackpad_detected = bool(
        touchpads
        and all(item.get("present") and item.get("readable") for item in touchpads)
        and (libinput.get("xorg_driver") or input_state.get("status") == "ready")
    )
    generation_raw = chain.get("completed_generations")
    try:
        generation = int(generation_raw) if generation_raw is not None else None
    except (TypeError, ValueError):
        generation = None

    return {
        "machine": identity.get("display_name") or "Hopper",
        "hostname": identity.get("hostname") or _text(Path("/etc/hostname"), "hopper"),
        "online": _online(),
        "head": head,
        "head_short": head[:12] if head != "unknown" else "unknown",
        "branch": _branch(workspace),
        "runtime_status": runtime_state.get("status") or "unknown",
        "runtime_schema": runtime_state.get("schema") or None,
        "autonomy": autonomy.get("status") or "unknown",
        "driver": driver.get("status") or "unknown",
        "driver_devices": driver.get("devices_modeled"),
        "pointers": len(pointers),
        "touchpads": len(touchpads),
        "keyboards": len(keyboards),
        "trackpad_detected": trackpad_detected,
        "pointer_verified": pointer_proof.get("status") == "motion-observed",
        "xorg_libinput": bool(libinput.get("xorg_driver")),
        "generation": generation,
        "next_gap": chain.get("next_gap") or None,
        "traits": list(traits.get("traits") or []),
        "traits_total": int(traits.get("total") or 0),
        "traits_ready": int(traits.get("foundation_ready") or 0),
        "traits_planned": int(traits.get("planned") or 0),
        "battery": _battery_status(),
        "wifi": _wifi_status(),
        "cpu_percent": _cpu_percent(),
        "memory_percent": _memory_percent(),
        "storage_percent": _storage_percent(),
        "gpu_percent": _gpu_percent(),
        "power_profile": _power_profile(),
        "time": _time_status(workspace, runtime),
        "vt": _current_vt(),
    }


def _system_health(snap: dict[str, Any]) -> tuple[str, list[str]]:
    issues: list[str] = []
    if not snap.get("online"):
        issues.append("no default network route")
    battery = snap.get("battery") or {}
    if battery.get("present") and battery.get("percent") is not None:
        if int(battery["percent"]) <= 10 and not battery.get("charging"):
            issues.append("battery critically low")
    if not snap.get("pointers"):
        issues.append("no pointer device reported")
    if not (snap.get("time") or {}).get("synchronized"):
        issues.append("time not server-synchronized")
    return ("Attention" if issues else "Live"), issues


def _write_receipt(state: Path, payload: dict[str, Any]) -> None:
    path = state / "desktop-ui.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _write_pointer_proof(
    state: Path,
    *,
    position: tuple[int, int],
    observed_at: str,
    source: str = "motion",
) -> None:
    path = state / "pointer-motion.json"
    payload = {
        "schema": "aurum.pointer-motion.v1",
        "status": "motion-observed",
        "machine": "Hopper",
        "position": [int(position[0]), int(position[1])],
        "source": source,
        "observed_at": observed_at,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _stop(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def _bounded_system_action(action: str) -> tuple[bool, str]:
    commands = {
        "recovery": ["chvt", "1"],
        "sleep": ["systemctl", "suspend"],
        "restart": ["systemctl", "reboot"],
        "shutdown": ["systemctl", "poweroff"],
    }
    args = commands.get(action)
    if not args:
        return False, "unsupported action"
    tool = shutil.which(args[0])
    if not tool:
        return False, f"{args[0]} unavailable"
    try:
        result = subprocess.run(
            [tool, *args[1:]],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return result.returncode == 0, result.stdout.strip()[-300:]


def run(state: Path, run_dir: Path, workspace: Path, runtime: Path) -> int:
    global STOP_REQUESTED
    STOP_REQUESTED = False
    try:
        import pygame
    except Exception as exc:
        _write_receipt(
            state,
            {"schema": SCHEMA, "status": "failed", "detail": f"pygame:{exc}"},
        )
        return 1

    pygame.init()
    pygame.font.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    width, height = screen.get_size()
    pygame.display.set_caption("Aurum Native GUI — Hopper")
    pygame.mouse.set_visible(False)

    scale = min(width / 1672.0, height / 941.0)
    S = lambda n: max(1, int(n * scale))

    bg = (4, 6, 9)
    sidebar = (8, 11, 15)
    panel = (12, 16, 21)
    panel_hover = (17, 22, 27)
    panel_shadow = (1, 2, 3)
    gold = (210, 158, 59)
    gold_hi = (245, 203, 105)
    gold_dim = (87, 66, 31)
    teal = (23, 192, 203)
    teal_hi = (87, 232, 231)
    ink = (240, 240, 235)
    muted = (147, 158, 166)
    good = (72, 205, 166)
    warn = (242, 191, 82)
    bad = (240, 112, 112)
    line = (52, 59, 64)

    def font(size: int, bold: bool = False):
        return pygame.font.SysFont("DejaVu Sans", max(10, S(size)), bold=bold)

    tiny = font(11)
    small = font(14)
    body = font(17)
    card_font = font(22, True)
    title_font = font(32, True)

    def text(value: object, x: int, y: int, face=body, color=ink):
        rendered = face.render(str(value), True, color)
        screen.blit(rendered, (x, y))
        return rendered

    def rounded(rect, fill, border=None, radius=14, border_width=1):
        pygame.draw.rect(screen, fill, rect, border_radius=S(radius))
        if border:
            pygame.draw.rect(
                screen,
                border,
                rect,
                width=max(1, S(border_width)),
                border_radius=S(radius),
            )

    def shadowed(rect, fill=panel, border=line, radius=14):
        shadow = rect.move(S(3), S(5))
        rounded(shadow, panel_shadow, None, radius)
        rounded(rect, fill, border, radius)

    def dot(x: int, y: int, color):
        pygame.draw.circle(screen, color, (x, y), max(3, S(4)))

    def fit(value: object, limit: int = 36) -> str:
        if value is None or value == "":
            return "Unknown"
        string = " ".join(str(value).split())
        return string if len(string) <= limit else string[: limit - 1] + "…"

    def leaf(cx: int, cy: int, w: int, h: int, angle: float, color=gold):
        surf = pygame.Surface((max(2, w), max(2, h)), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, color, surf.get_rect())
        surf = pygame.transform.rotate(surf, angle)
        screen.blit(surf, surf.get_rect(center=(cx, cy)))

    def aurum_mark(x: int, y: int, size: int):
        s = size
        ax, ay = x + int(s * .12), y + int(s * .08)
        left = (ax, ay + int(s * .70))
        apex = (ax + int(s * .24), ay)
        right = (ax + int(s * .48), ay + int(s * .70))
        pygame.draw.lines(screen, gold_hi, False, [left, apex, right], max(2, int(s * .055)))
        pygame.draw.line(
            screen,
            gold,
            (ax + int(s * .12), ay + int(s * .43)),
            (ax + int(s * .36), ay + int(s * .43)),
            max(2, int(s * .035)),
        )
        ux, uy = ax + int(s * .30), ay + int(s * .38)
        urect = pygame.Rect(ux, uy, int(s * .42), int(s * .36))
        pygame.draw.arc(screen, teal, urect, math.pi, math.tau, max(2, int(s * .035)))
        for rx, ry, ang in [
            (.45, .22, -45),
            (.51, .14, 35),
            (.57, .06, -40),
            (.62, .17, 34),
        ]:
            leaf(
                ax + int(s * rx),
                ay + int(s * ry),
                max(5, int(s * .10)),
                max(8, int(s * .18)),
                ang,
                gold_hi,
            )

    def wifi_icon(cx: int, cy: int, strength: int | None):
        level = 0 if strength is None else max(0, min(3, math.ceil(max(0, strength) / 34)))
        source_y = cy + S(3)
        pygame.draw.circle(
            screen,
            teal_hi if level else gold_dim,
            (cx, source_y),
            max(2, S(3)),
        )
        # Pond-ripple geometry: each ring shares the same source and expands
        # outward.  Inner-to-outer illumination makes signal direction honest.
        ripples = (
            (S(10), S(4)),
            (S(18), S(7)),
            (S(27), S(11)),
        )
        for index, (rx, ry) in enumerate(ripples, start=1):
            color = teal_hi if level >= index else gold_dim
            rect = pygame.Rect(cx - rx, source_y - ry, rx * 2, ry * 2)
            pygame.draw.ellipse(screen, color, rect, width=max(1, S(2)))

    def battery_icon(x: int, y: int, percent: int | None, charging: bool):
        w, h = S(38), S(18)
        pygame.draw.rect(
            screen, muted, pygame.Rect(x, y, w, h), width=max(1, S(2)), border_radius=S(3)
        )
        pygame.draw.rect(
            screen, muted, pygame.Rect(x + w, y + S(5), S(4), S(8)), border_radius=S(1)
        )
        if percent is not None:
            p = max(0, min(100, percent))
            fillw = max(0, int((w - S(6)) * p / 100))
            if fillw:
                pygame.draw.rect(
                    screen,
                    good if p > 20 else bad,
                    pygame.Rect(x + S(3), y + S(3), fillw, h - S(6)),
                    border_radius=S(2),
                )
        if charging:
            text("⚡", x + S(47), y - S(4), body, teal_hi)

    def progress_bar(rect, percent: int | None, color=teal):
        pygame.draw.rect(screen, (28, 34, 39), rect, border_radius=S(4))
        if percent is None:
            pygame.draw.line(
                screen, muted, rect.midleft, rect.midright, max(1, S(1))
            )
            return
        fill = pygame.Rect(
            rect.x,
            rect.y,
            int(rect.width * max(0, min(100, percent)) / 100),
            rect.height,
        )
        if fill.width:
            pygame.draw.rect(screen, color, fill, border_radius=S(4))

    def draw_cursor(position: tuple[int, int]):
        x, y = int(position[0]), int(position[1])
        s = max(10, S(15))
        points = [
            (x, y),
            (x, y + s),
            (x + int(s * .32), y + int(s * .72)),
            (x + int(s * .62), y + int(s * 1.28)),
            (x + int(s * .82), y + int(s * 1.17)),
            (x + int(s * .52), y + int(s * .63)),
            (x + s, y + int(s * .63)),
        ]
        pygame.draw.polygon(screen, (3, 3, 3), points)
        pygame.draw.lines(screen, ink, True, points, max(1, S(2)))

    initial_time = _time_status(workspace, runtime)
    if _online() and not initial_time.get("synchronized"):
        _request_time_sync(workspace, runtime, timeout_seconds=5)

    snap = snapshot(state, workspace, runtime)
    _write_receipt(
        state,
        {
            "schema": SCHEMA,
            "generation_name": GENERATION_NAME,
            "ui_identity": "gen1-polished-physical-surface",
            "status": "running",
            "pid": os.getpid(),
            "surface": "physical",
            "machine": "Hopper",
            "host_actuation": "bounded-confirmed-actions",
            "cursor": "aurum-software",
            "resolution": [width, height],
            "telemetry": "measured-or-unknown",
            "time_source": (snap.get("time") or {}).get("source"),
            "time_synchronized": bool((snap.get("time") or {}).get("synchronized")),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )

    nav = ["Home", "Traits", "Build", "Hardware", "Field", "Settings"]
    selected = 0
    detail_view: str | None = None
    toast = ""
    toast_until = 0.0
    confirm_action: str | None = None
    last_refresh = 0.0
    pointer_motion_observed = bool(snap["pointer_verified"])
    clock = pygame.time.Clock()
    click_targets: list[tuple[Any, str, Any]] = []

    def add_target(rect, action, payload=None):
        click_targets.append((rect.copy(), action, payload))

    def nav_click(index):
        nonlocal selected, detail_view
        selected = int(index)
        detail_view = None

    def handle_action(action, payload=None):
        nonlocal selected, detail_view, toast, toast_until, confirm_action, last_refresh, snap
        if action == "nav":
            nav_click(payload)
        elif action == "detail":
            selected, detail_view = int(payload[0]), str(payload[1])
        elif action == "recovery":
            ok, detail = _bounded_system_action("recovery")
            toast = "Recovery console requested" if ok else f"Recovery failed: {detail or 'unavailable'}"
            toast_until = time.monotonic() + 4
        elif action in {"sleep", "restart", "shutdown"}:
            confirm_action = action
        elif action == "confirm":
            act = str(payload)
            ok, detail = _bounded_system_action(act)
            toast = f"{act.title()} requested" if ok else f"{act.title()} failed: {detail or 'unavailable'}"
            toast_until = time.monotonic() + 4
            confirm_action = None
        elif action == "cancel":
            confirm_action = None
        elif action == "refresh":
            last_refresh = 0
            toast = "Refreshing Hopper telemetry"
            toast_until = time.monotonic() + 2
        elif action == "timesync":
            result = _request_time_sync(workspace, runtime, timeout_seconds=5)
            last_refresh = 0
            if result.get("synchronized"):
                server = result.get("server_name") or result.get("server_address") or "time server"
                toast = f"Time synchronized · {server}"
            else:
                toast = f"Time sync {result.get('status', 'unavailable')}"
            toast_until = time.monotonic() + 4

    def button(rect, label, action, payload=None, accent=gold):
        hover = rect.collidepoint(pygame.mouse.get_pos())
        shadowed(
            rect,
            panel_hover if hover else (10, 14, 18),
            accent if hover else line,
            9,
        )
        text(label, rect.x + S(14), rect.y + S(8), small, ink)
        text("›", rect.right - S(20), rect.y + S(7), body, accent)
        add_target(rect, action, payload)

    def card_shell(rect, title, status="", status_color=teal):
        hover = rect.collidepoint(pygame.mouse.get_pos())
        shadowed(rect, panel_hover if hover else panel, gold_dim if hover else line, 12)
        text(title.upper(), rect.x + S(15), rect.y + S(13), tiny, gold_hi)
        if status:
            dot(rect.x + S(17), rect.y + S(38), status_color)
            text(status, rect.x + S(28), rect.y + S(30), tiny, status_color)

    while not STOP_REQUESTED:
        now = time.monotonic()
        if now - last_refresh >= 4:
            snap = snapshot(state, workspace, runtime)
            pointer_motion_observed = pointer_motion_observed or bool(snap["pointer_verified"])
            last_refresh = now

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                STOP_REQUESTED = True
            elif event.type == pygame.KEYDOWN:
                ctrl = bool(event.mod & pygame.KMOD_CTRL)
                alt = bool(event.mod & pygame.KMOD_ALT)
                if ctrl and alt and event.key == pygame.K_F1:
                    handle_action("recovery")
                elif event.key == pygame.K_F5:
                    handle_action("refresh")
                elif event.key == pygame.K_F12:
                    STOP_REQUESTED = True
                elif pygame.K_1 <= event.key <= pygame.K_6:
                    nav_click(event.key - pygame.K_1)
            elif event.type == pygame.MOUSEMOTION and event.rel != (0, 0):
                if not pointer_motion_observed:
                    pointer_motion_observed = True
                    observed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    _write_pointer_proof(
                        state, position=event.pos, observed_at=observed_at
                    )
            elif event.type == pygame.MOUSEWHEEL:
                if not pointer_motion_observed:
                    pointer_motion_observed = True
                    observed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    _write_pointer_proof(
                        state,
                        position=pygame.mouse.get_pos(),
                        observed_at=observed_at,
                        source="scroll",
                    )
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                for rect, action, payload in reversed(click_targets):
                    if rect.collidepoint(event.pos):
                        handle_action(action, payload)
                        break

        click_targets.clear()
        screen.fill(bg)
        for y in range(0, height, max(1, S(72))):
            pygame.draw.line(screen, (8, 13, 17), (0, y), (width, y), 1)
        for x in range(0, width, max(1, S(110))):
            pygame.draw.line(screen, (7, 11, 14), (x, 0), (x, height), 1)

        top_h = S(68)
        pygame.draw.rect(screen, (5, 8, 11), pygame.Rect(0, 0, width, top_h))
        pygame.draw.line(screen, line, (0, top_h - 1), (width, top_h - 1))
        aurum_mark(S(18), S(10), S(56))
        text("A U R U M", S(82), S(16), body, gold_hi)
        text("NATIVE GUI", S(205), S(19), tiny, teal)

        identity_rect = pygame.Rect(S(465), S(14), S(430), S(40))
        shadowed(identity_rect, (9, 13, 17), line, 14)
        text(
            f"{fit(snap['machine'], 18)}  •  LIVE MACHINE STATE",
            identity_rect.x + S(16),
            identity_rect.y + S(10),
            small,
            ink,
        )
        add_target(identity_rect, "refresh")

        wifi = snap["wifi"]
        battery = snap["battery"]
        time_state = snap["time"]

        wifi_rect = pygame.Rect(width - S(520), S(10), S(190), S(48))
        shadowed(wifi_rect, (8, 13, 16), line, 10)
        wifi_icon(
            wifi_rect.x + S(28),
            wifi_rect.centery - S(4),
            wifi.get("signal"),
        )
        text(
            fit(wifi.get("ssid"), 18),
            wifi_rect.x + S(54),
            wifi_rect.y + S(7),
            tiny,
            ink,
        )
        text(
            "Connected" if wifi.get("connected") else "Offline",
            wifi_rect.x + S(54),
            wifi_rect.y + S(25),
            tiny,
            good if wifi.get("connected") else bad,
        )
        add_target(wifi_rect, "detail", (5, "Network"))

        batt_rect = pygame.Rect(width - S(320), S(10), S(145), S(48))
        shadowed(batt_rect, (8, 13, 16), line, 10)
        bp = battery.get("percent")
        text(
            f"{bp}%" if bp is not None else "—",
            batt_rect.x + S(10),
            batt_rect.y + S(7),
            body,
            ink,
        )
        battery_icon(
            batt_rect.x + S(60),
            batt_rect.y + S(14),
            bp,
            bool(battery.get("charging")),
        )
        text(
            fit(battery.get("status"), 16),
            batt_rect.x + S(10),
            batt_rect.y + S(30),
            tiny,
            good if battery.get("charging") else muted,
        )
        add_target(batt_rect, "detail", (5, "Power"))

        time_rect = pygame.Rect(width - S(165), S(10), S(150), S(48))
        shadowed(
            time_rect,
            (8, 13, 16),
            teal if time_state.get("synchronized") else warn,
            10,
        )
        try:
            display_dt = dt.datetime.fromisoformat(str(time_state.get("local_iso")))
            time_label = display_dt.strftime("%-I:%M %p")
            date_label = display_dt.strftime("%b %d, %Y")
        except (TypeError, ValueError):
            time_label, date_label = "Time unknown", "Not synchronized"
        text(time_label, time_rect.x + S(10), time_rect.y + S(5), small, ink)
        text(
            date_label,
            time_rect.x + S(10),
            time_rect.y + S(24),
            tiny,
            muted,
        )
        text(
            "NTP" if time_state.get("synchronized") else "LOCAL",
            time_rect.right - S(39),
            time_rect.y + S(5),
            tiny,
            good if time_state.get("synchronized") else warn,
        )
        add_target(time_rect, "detail", (5, "Time"))

        side_w = S(255)
        side = pygame.Rect(0, top_h, side_w, height - top_h)
        pygame.draw.rect(screen, sidebar, side)
        pygame.draw.line(screen, line, (side_w, top_h), (side_w, height))
        aurum_mark(S(55), top_h + S(25), S(125))
        text("A U R U M", S(60), top_h + S(145), small, gold_hi)
        text("ONE SEED. ENDLESS POSSIBILITIES.", S(26), top_h + S(173), tiny, teal)

        nav_y = top_h + S(218)
        for i, name in enumerate(nav):
            rect = pygame.Rect(S(20), nav_y + i * S(58), side_w - S(40), S(44))
            hover = rect.collidepoint(pygame.mouse.get_pos())
            if i == selected:
                rounded(rect, (29, 23, 12), gold, 12)
            elif hover:
                rounded(rect, (17, 19, 20), gold_dim, 12)
            text(str(i + 1), rect.x + S(13), rect.y + S(13), tiny, gold if i == selected else muted)
            text(name, rect.x + S(39), rect.y + S(9), small, gold_hi if i == selected else ink)
            add_target(rect, "nav", i)

        main_x = side_w + S(25)
        main_w = width - main_x - S(25)
        content_top = top_h + S(22)
        health_label, health_issues = _system_health(snap)
        text(f"{snap['machine']} · live system state", main_x, content_top, title_font, gold_hi)
        subtitle = (
            "Measured locally. Unknown values stay unknown."
            if not health_issues
            else f"{len(health_issues)} item{'s' if len(health_issues) != 1 else ''} need attention."
        )
        text(subtitle, main_x, content_top + S(40), small, teal if not health_issues else warn)

        if selected == 0:
            grid_top = content_top + S(82)
            gap = S(12)
            card_w = (main_w - gap * 3) // 4
            row_h = S(208)

            r1 = pygame.Rect(main_x, grid_top, card_w, row_h)
            card_shell(
                r1,
                "System Evidence",
                health_label,
                good if health_label == "Live" else warn,
            )
            text("Runtime", r1.x + S(18), r1.y + S(65), tiny, muted)
            text(fit(snap["runtime_status"], 24), r1.x + S(110), r1.y + S(61), small, ink)
            text("Branch", r1.x + S(18), r1.y + S(94), tiny, muted)
            text(fit(snap["branch"], 24), r1.x + S(110), r1.y + S(90), small, ink)
            text("Head", r1.x + S(18), r1.y + S(123), tiny, muted)
            text(fit(snap["head_short"], 18), r1.x + S(110), r1.y + S(119), small, ink)
            button(
                pygame.Rect(r1.x + S(12), r1.bottom - S(42), r1.width - S(24), S(30)),
                "View Runtime Evidence",
                "detail",
                (2, "Runtime"),
            )

            r2 = pygame.Rect(r1.right + gap, grid_top, card_w, row_h)
            card_shell(
                r2,
                "Network",
                "Connected" if wifi.get("connected") else "Offline",
                good if wifi.get("connected") else bad,
            )
            wifi_icon(r2.x + S(72), r2.y + S(105), wifi.get("signal"))
            text("SSID", r2.x + S(135), r2.y + S(63), tiny, muted)
            text(fit(wifi.get("ssid"), 18), r2.x + S(135), r2.y + S(81), small, ink)
            text(
                f"Signal {wifi.get('signal')}%" if wifi.get("signal") is not None else "Signal unknown",
                r2.x + S(135),
                r2.y + S(111),
                tiny,
                teal,
            )
            text(
                f"IP {wifi.get('ip')}" if wifi.get("ip") else "IP unknown",
                r2.x + S(135),
                r2.y + S(132),
                tiny,
                muted,
            )
            button(
                pygame.Rect(r2.x + S(12), r2.bottom - S(42), r2.width - S(24), S(30)),
                "Network Evidence",
                "detail",
                (5, "Network"),
            )

            r3 = pygame.Rect(r2.right + gap, grid_top, card_w, row_h)
            card_shell(
                r3,
                "Power & Battery",
                fit(battery.get("status"), 18),
                good if battery.get("charging") else teal,
            )
            center = (r3.x + S(76), r3.y + S(106))
            pygame.draw.circle(screen, gold_dim, center, S(47), width=S(6))
            if bp is not None:
                pygame.draw.arc(
                    screen,
                    gold_hi,
                    pygame.Rect(center[0] - S(47), center[1] - S(47), S(94), S(94)),
                    math.pi / 2,
                    math.pi / 2 + math.tau * int(bp) / 100,
                    width=S(6),
                )
            text(f"{bp}%" if bp is not None else "—", center[0] - S(28), center[1] - S(14), card_font, gold_hi)
            text("Profile", r3.x + S(145), r3.y + S(72), tiny, muted)
            text(fit(snap.get("power_profile"), 18), r3.x + S(145), r3.y + S(89), small, ink)
            remaining = battery.get("minutes_remaining")
            text(
                f"{remaining // 60}h {remaining % 60}m remaining"
                if remaining is not None
                else "Runtime estimate unknown",
                r3.x + S(145),
                r3.y + S(120),
                tiny,
                muted,
            )
            button(
                pygame.Rect(r3.x + S(12), r3.bottom - S(42), r3.width - S(24), S(30)),
                "Power Evidence",
                "detail",
                (5, "Power"),
            )

            r4 = pygame.Rect(r3.right + gap, grid_top, card_w, row_h)
            trait_status = "Registered" if snap["traits_total"] else "No evidence"
            card_shell(r4, "Traits", trait_status, teal if snap["traits_total"] else muted)
            pygame.draw.line(
                screen,
                gold,
                (r4.x + S(65), r4.y + S(145)),
                (r4.x + S(100), r4.y + S(65)),
                S(2),
            )
            for i in range(7):
                leaf(
                    r4.x + S(70) + (i % 3) * S(22),
                    r4.y + S(130) - i * S(10),
                    S(15),
                    S(28),
                    -40 + (i % 2) * 80,
                    gold_hi,
                )
            text(f"{snap['traits_ready']} ready", r4.x + S(145), r4.y + S(72), small, ink)
            text(f"{snap['traits_total']} registered", r4.x + S(145), r4.y + S(98), tiny, muted)
            button(
                pygame.Rect(r4.x + S(12), r4.bottom - S(42), r4.width - S(24), S(30)),
                "View Traits",
                "nav",
                1,
            )

            row2 = grid_top + row_h + gap
            r5 = pygame.Rect(main_x, row2, card_w, row_h)
            metrics = [
                ("CPU", snap.get("cpu_percent")),
                ("Memory", snap.get("memory_percent")),
                ("Storage", snap.get("storage_percent")),
                ("GPU", snap.get("gpu_percent")),
            ]
            known_count = sum(value is not None for _, value in metrics)
            card_shell(r5, "Hardware Telemetry", f"{known_count}/4 live metrics", teal if known_count else muted)
            ry = r5.y + S(62)
            for label_name, value in metrics:
                text(label_name, r5.x + S(18), ry, tiny, ink)
                progress_bar(
                    pygame.Rect(r5.x + S(90), ry + S(4), r5.width - S(125), S(6)),
                    value,
                )
                text(
                    f"{value}%" if value is not None else "—",
                    r5.right - S(40),
                    ry,
                    tiny,
                    muted,
                )
                ry += S(27)
            button(
                pygame.Rect(r5.x + S(12), r5.bottom - S(42), r5.width - S(24), S(30)),
                "Hardware Evidence",
                "nav",
                3,
            )

            r6 = pygame.Rect(r5.right + gap, row2, card_w, row_h)
            input_status = "Pointer verified" if pointer_motion_observed else "Input detected"
            card_shell(r6, "Input & Recovery", input_status, good if pointer_motion_observed else warn)
            input_rows = [
                ("Trackpad", "verified by motion" if pointer_motion_observed else ("detected" if snap["trackpad_detected"] else "unknown")),
                ("Pointers", str(snap["pointers"])),
                ("Keyboards", str(snap["keyboards"]) if snap["keyboards"] else "unknown"),
                ("Recovery", "Ctrl+Alt+F1"),
            ]
            ry = r6.y + S(60)
            for label_name, value in input_rows:
                text(label_name, r6.x + S(18), ry, tiny, muted)
                text(value, r6.x + S(135), ry, tiny, ink)
                ry += S(27)
            button(
                pygame.Rect(r6.x + S(12), r6.bottom - S(42), r6.width - S(24), S(30)),
                "Open Recovery Console",
                "recovery",
                accent=teal,
            )

            r7 = pygame.Rect(r6.right + gap, row2, card_w, row_h)
            sync = bool(time_state.get("synchronized"))
            card_shell(r7, "Verified Time", "NTP synchronized" if sync else "Local clock only", good if sync else warn)
            text("Source", r7.x + S(18), r7.y + S(65), tiny, muted)
            source = time_state.get("server_name") or time_state.get("server_address")
            text(fit(source if sync else "not authoritative", 25), r7.x + S(110), r7.y + S(61), small, ink)
            text("Zone", r7.x + S(18), r7.y + S(95), tiny, muted)
            text(fit(time_state.get("timezone"), 25), r7.x + S(110), r7.y + S(91), small, ink)
            text("Mode", r7.x + S(18), r7.y + S(125), tiny, muted)
            text("server time" if sync else "local fallback", r7.x + S(110), r7.y + S(121), small, good if sync else warn)
            button(
                pygame.Rect(r7.x + S(12), r7.bottom - S(42), r7.width - S(24), S(30)),
                "Sync / View Time",
                "detail",
                (5, "Time"),
                accent=teal,
            )

            r8 = pygame.Rect(r7.right + gap, row2, card_w, row_h)
            card_shell(r8, "System Tools", "Real actions", teal)
            tool_rows = [
                ("Update & Sync", (2, "Update & Sync")),
                ("Recovery", (5, "Recovery")),
                ("Power", (5, "Power")),
                ("Network", (5, "Network")),
            ]
            ry = r8.y + S(58)
            for label_name, target in tool_rows:
                rr = pygame.Rect(r8.x + S(12), ry - S(4), r8.width - S(24), S(28))
                if rr.collidepoint(pygame.mouse.get_pos()):
                    rounded(rr, (23, 25, 24), gold_dim, 7)
                text(label_name, rr.x + S(7), rr.y + S(6), tiny, ink)
                text("›", rr.right - S(15), rr.y + S(3), small, gold_hi)
                add_target(rr, "detail", target)
                ry += S(31)

            qa_y = row2 + row_h + gap
            qa_h = max(S(58), height - qa_y - S(48))
            qa = pygame.Rect(main_x, qa_y, main_w, qa_h)
            shadowed(qa, panel, line, 12)
            text("QUICK ACTIONS", qa.x + S(16), qa.y + S(12), tiny, gold_hi)
            bw = S(150)
            quick = [
                ("Refresh", "refresh"),
                ("Recovery", "recovery"),
                ("Sleep", "sleep"),
                ("Restart", "restart"),
                ("Shut Down", "shutdown"),
            ]
            for i, (label_name, action) in enumerate(quick):
                br = pygame.Rect(
                    qa.x + S(140) + i * (bw + S(10)),
                    qa.y + S(10),
                    bw,
                    S(38),
                )
                rounded(
                    br,
                    panel_hover if br.collidepoint(pygame.mouse.get_pos()) else (10, 14, 18),
                    teal if action == "refresh" else gold_dim,
                    10,
                )
                text(label_name, br.x + S(18), br.y + S(9), small, ink)
                add_target(br, action)

        else:
            box = pygame.Rect(
                main_x,
                content_top + S(82),
                main_w,
                height - (content_top + S(82)) - S(28),
            )
            shadowed(box, panel, line, 14)
            heading = detail_view or nav[selected]
            text(heading, box.x + S(24), box.y + S(22), title_font, gold_hi)
            text(
                f"{nav[selected]} · measured Hopper state",
                box.x + S(26),
                box.y + S(63),
                tiny,
                teal,
            )

            if heading == "Network":
                rows = [
                    ("Status", "Connected" if wifi.get("connected") else "Offline"),
                    ("SSID", wifi.get("ssid")),
                    ("Signal", f"{wifi.get('signal')}%" if wifi.get("signal") is not None else None),
                    ("Address", wifi.get("ip")),
                    ("Interface", wifi.get("interface")),
                    ("Operstate", wifi.get("operstate")),
                ]
            elif heading == "Power":
                rows = [
                    ("Battery", f"{bp}%" if bp is not None else None),
                    ("Status", battery.get("status")),
                    ("Charging", battery.get("charging")),
                    ("Power profile", snap.get("power_profile")),
                    ("Battery device", battery.get("name")),
                ]
            elif heading == "Time":
                rows = [
                    ("Authority", "NTP server" if time_state.get("synchronized") else "Local clock only"),
                    ("Synchronized", time_state.get("synchronized")),
                    ("Server name", time_state.get("server_name")),
                    ("Server address", time_state.get("server_address")),
                    ("Timezone", time_state.get("timezone")),
                    ("Local ISO", time_state.get("local_iso")),
                ]
            elif heading == "Recovery":
                rows = [
                    ("Recovery hotkey", "Ctrl+Alt+F1"),
                    ("Target", "tty1"),
                    ("Current VT", snap.get("vt")),
                    ("Pointer proof", "verified" if pointer_motion_observed else "not yet verified"),
                ]
            elif heading == "Runtime":
                rows = [
                    ("Branch", snap["branch"]),
                    ("Head", snap["head"]),
                    ("Runtime", snap["runtime_status"]),
                    ("Runtime schema", snap["runtime_schema"]),
                    ("Autonomy", snap["autonomy"]),
                    ("Generation", snap["generation"]),
                    ("Next frontier", snap["next_gap"]),
                ]
            elif nav[selected] == "Hardware":
                rows = [
                    ("Machine", snap["machine"]),
                    ("Display", f"{width} × {height}"),
                    ("CPU", f"{snap['cpu_percent']}%" if snap["cpu_percent"] is not None else None),
                    ("Memory", f"{snap['memory_percent']}%" if snap["memory_percent"] is not None else None),
                    ("Storage", f"{snap['storage_percent']}%" if snap["storage_percent"] is not None else None),
                    ("GPU", f"{snap['gpu_percent']}%" if snap["gpu_percent"] is not None else None),
                    ("Pointers", snap["pointers"]),
                    ("Touchpads", snap["touchpads"]),
                    ("Xorg libinput", "reported" if snap["xorg_libinput"] else None),
                ]
            elif nav[selected] == "Build":
                rows = [
                    ("Branch", snap["branch"]),
                    ("Head", snap["head"]),
                    ("Runtime", snap["runtime_status"]),
                    ("Autonomy", snap["autonomy"]),
                    ("Generation", snap["generation"]),
                    ("Next frontier", snap["next_gap"]),
                ]
            elif nav[selected] == "Traits":
                rows = [
                    (
                        str(item.get("name") or item.get("id") or "Trait"),
                        str(item.get("stage") or "unknown"),
                    )
                    for item in snap["traits"]
                ] or [("Traits", "No trait evidence reported")]
            else:
                rows = [
                    ("Aurum desktop", "Gen1 polished physical surface"),
                    ("Machine", snap["machine"]),
                    ("Runtime", snap["runtime_status"]),
                    ("Network route", "online" if snap["online"] else "offline"),
                    ("Evidence policy", "measured-or-unknown"),
                ]

            ry = box.y + S(110)
            for label_name, value in rows[:9]:
                text(label_name, box.x + S(30), ry, small, muted)
                text(fit(value, 60), box.x + S(250), ry - S(4), body, ink if value is not None else warn)
                pygame.draw.line(
                    screen,
                    (39, 44, 46),
                    (box.x + S(28), ry + S(29)),
                    (box.right - S(28), ry + S(29)),
                )
                ry += S(52)

            if heading == "Recovery":
                button(
                    pygame.Rect(box.x + S(30), box.bottom - S(62), S(250), S(38)),
                    "Open Recovery Console",
                    "recovery",
                    accent=teal,
                )
            elif heading == "Time":
                button(
                    pygame.Rect(box.x + S(30), box.bottom - S(62), S(250), S(38)),
                    "Synchronize From Time Server",
                    "timesync",
                    accent=teal,
                )

        footer_y = height - S(27)
        text(
            "AURUM OS · LIVE VALUES ARE MEASURED; MISSING VALUES ARE SHOWN AS UNKNOWN.",
            S(18),
            footer_y,
            tiny,
            teal,
        )

        if toast and now < toast_until:
            tw = font(13, True).render(toast, True, ink)
            tr = pygame.Rect(
                width // 2 - tw.get_width() // 2 - S(18),
                height - S(64),
                tw.get_width() + S(36),
                S(34),
            )
            rounded(tr, (20, 17, 10), gold, 10)
            screen.blit(tw, (tr.x + S(18), tr.y + S(9)))

        if confirm_action:
            shade = pygame.Surface((width, height), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 165))
            screen.blit(shade, (0, 0))
            mr = pygame.Rect(
                width // 2 - S(240),
                height // 2 - S(90),
                S(480),
                S(180),
            )
            shadowed(mr, (13, 15, 17), gold, 16)
            text(
                f"Confirm {confirm_action.title()}?",
                mr.x + S(28),
                mr.y + S(28),
                card_font,
                gold_hi,
            )
            text(
                "This is a real system action on Hopper.",
                mr.x + S(28),
                mr.y + S(72),
                small,
                muted,
            )
            yes = pygame.Rect(mr.x + S(28), mr.bottom - S(58), S(180), S(36))
            no = pygame.Rect(mr.right - S(208), mr.bottom - S(58), S(180), S(36))
            rounded(yes, (24, 18, 8), gold, 10)
            rounded(no, (12, 16, 18), teal, 10)
            text("Confirm", yes.x + S(56), yes.y + S(9), small, gold_hi)
            text("Cancel", no.x + S(62), no.y + S(9), small, teal_hi)
            add_target(yes, "confirm", confirm_action)
            add_target(no, "cancel")

        draw_cursor(pygame.mouse.get_pos())
        pygame.display.flip()
        clock.tick(30)

    _write_receipt(
        state,
        {
            "schema": SCHEMA,
            "generation_name": GENERATION_NAME,
            "ui_identity": "gen1-polished-physical-surface",
            "status": "stopped",
            "machine": "Hopper",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )
    pygame.quit()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Aurum Native GUI physical desktop")
    parser.add_argument("command", nargs="?", default="run", choices=("run",))
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state")),
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=Path(os.environ.get("AURUM_RUN_DIR", "/run/aurum")),
    )
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    workspace = Path(
        os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain")
    )
    runtime = Path(os.environ.get("AURUM_RUNTIME_ROOT", "/opt/aurum"))
    return run(args.state_dir, args.run_dir, workspace, runtime)


if __name__ == "__main__":
    raise SystemExit(main())
