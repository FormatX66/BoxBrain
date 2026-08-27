#!/usr/bin/env python3
"""Gen1 HTML projection for Hopper.

Aurum owns state, policy, execution, verification, and receipts.  This module
projects those semantics into HTML/CSS/JS for human interaction.  It reuses the
existing loopback-only Aurum GUI server and extends it with bounded Hopper
telemetry, direct-control actions, and the resident GPT trait.  No raw shell is
exposed through the browser surface.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import threading
import time
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
DEFAULT_RUNTIME = Path(os.environ.get("AURUM_RUNTIME_ROOT", "/opt/aurum"))
SEED_DIR = DEFAULT_WORKSPACE / "Projects" / "Codelation" / "seed"
GUI_PATH = SEED_DIR / "aurum_gui.py"
RUNTIME_SEED_DIR = DEFAULT_RUNTIME / "codelation" / "seed"
RUNTIME_GUI_PATH = RUNTIME_SEED_DIR / "aurum_gui.py"
SCHEMA = "aurum.hopper-projection.gen1-html"
WORKSPACE_LOGO_PATH = (
    DEFAULT_WORKSPACE
    / "Projects"
    / "Codelation"
    / "assets"
    / "identity"
    / "aurum-seven-leaf-logo-matrix.jpeg"
)
RUNTIME_LOGO_PATH = DEFAULT_RUNTIME / "codelation" / "assets" / "identity" / "aurum-seven-leaf-logo-matrix.jpeg"
LOGO_PATH = WORKSPACE_LOGO_PATH
LOGO_SHA256 = "633f14213af2cda495100cc61167d03bbbcf2d781f9ff72a0d8d18e87afbbb6c"


def _verified_logo_bytes(path: Path | None = None) -> bytes | None:
    """Return the selected identity mark only when its geometry authority matches."""
    candidates = (path,) if path is not None else (RUNTIME_LOGO_PATH, WORKSPACE_LOGO_PATH)
    for candidate in candidates:
        try:
            payload = candidate.read_bytes()
        except OSError:
            continue
        if hashlib.sha256(payload).hexdigest() == LOGO_SHA256:
            return payload
    return None


def _load_path(path: Path, prefix: str):
    if not path.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location(
            f"{prefix}_{os.getpid()}_{time.time_ns()}", path
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def _load_gui():
    for path in (RUNTIME_GUI_PATH, GUI_PATH):
        seed_text = str(path.parent)
        if seed_text not in sys.path:
            sys.path.insert(0, seed_text)
        module = _load_path(path, "aurum_hopper_gui_base")
        if module is not None:
            return module
    raise RuntimeError(
        f"Aurum GUI source unavailable: {RUNTIME_GUI_PATH} or {GUI_PATH}"
    )


def _load_runtime_module(filename: str, prefix: str):
    for path in (
        DEFAULT_RUNTIME / filename,
        DEFAULT_WORKSPACE / "Projects" / "AurumPC" / filename,
    ):
        module = _load_path(path, prefix)
        if module is not None:
            return module
    return None


def _json_safe_dict(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        return None
    return value


def _battery() -> dict[str, Any]:
    root = Path("/sys/class/power_supply")
    try:
        candidates = sorted(p for p in root.iterdir() if p.name.upper().startswith("BAT"))
    except OSError:
        candidates = []
    for bat in candidates:
        try:
            percent = int((bat / "capacity").read_text().strip())
            status = (bat / "status").read_text().strip()
        except (OSError, ValueError):
            continue
        return {
            "present": True,
            "percent": max(0, min(100, percent)),
            "status": status or "Unknown",
            "charging": status.lower() in {"charging", "full"},
        }
    return {"present": False, "percent": None, "status": "Unknown", "charging": False}


def _memory_percent() -> int | None:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if ":" not in line:
                continue
            key, rest = line.split(":", 1)
            values[key] = int(rest.strip().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    total, available = values.get("MemTotal"), values.get("MemAvailable")
    if not total or available is None:
        return None
    return max(0, min(100, round((1 - available / total) * 100)))


def _storage_percent() -> int | None:
    try:
        usage = shutil.disk_usage("/")
    except OSError:
        return None
    return round(usage.used / usage.total * 100) if usage.total else None


def _uptime() -> int | None:
    try:
        return int(float(Path("/proc/uptime").read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        return None


def _telemetry() -> dict[str, Any]:
    executor = _load_runtime_module("aurum_gpt_executor.py", "aurum_gpt_executor")
    state: dict[str, Any] = {"status": "unavailable", "detail": "executor-unavailable"}
    if executor and hasattr(executor, "status_snapshot"):
        try:
            candidate = executor.status_snapshot()
            safe_candidate = _json_safe_dict(candidate)
            if safe_candidate is not None:
                state = safe_candidate
            else:
                state = {"status": "unavailable", "detail": "invalid-executor-status"}
        except Exception as exc:
            state = {
                "status": "unavailable",
                "detail": f"{type(exc).__name__}:{exc}",
            }

    network_module = _load_runtime_module("aurum_network.py", "aurum_network")
    network: dict[str, Any] = {
        "status": "unavailable",
        "online": False,
        "detail": "network-module-unavailable",
    }
    try:
        if network_module:
            candidate = network_module.network_status()
            safe_candidate = _json_safe_dict(candidate)
            if safe_candidate is not None:
                network = safe_candidate
            else:
                network["detail"] = "invalid-network-status"
    except Exception as exc:
        network["detail"] = f"{type(exc).__name__}:{exc}"

    time_module = _load_runtime_module("aurum_time.py", "aurum_time")
    clock: dict[str, Any] = {
        "status": "unavailable",
        "synchronized": False,
        "detail": "time-module-unavailable",
    }
    try:
        if time_module:
            candidate = time_module.time_status()
            safe_candidate = _json_safe_dict(candidate)
            if safe_candidate is not None:
                clock = safe_candidate
            else:
                clock["detail"] = "invalid-time-status"
    except Exception as exc:
        clock["detail"] = f"{type(exc).__name__}:{exc}"

    return {
        "state": state,
        "network": network,
        "time": clock,
        "battery": _battery(),
        "memory_percent": _memory_percent(),
        "storage_percent": _storage_percent(),
        "uptime_seconds": _uptime(),
        "renderer": "html5",
        "projection": "primary-human-surface",
    }


def _appearance() -> dict[str, Any]:
    executor = _load_runtime_module("aurum_gpt_executor.py", "aurum_gpt_executor_appearance")
    if executor is None or not hasattr(executor, "appearance_snapshot"):
        return {
            "schema": "aurum.appearance-preview.v1",
            "status": "default",
            "theme": "default",
            "background_start": "#050706",
            "background_end": "#070b09",
            "temporary": True,
            "resets_on_reboot": True,
            "tracked_source_modified": False,
        }
    try:
        candidate = _json_safe_dict(dict(executor.appearance_snapshot()))
        if candidate is not None:
            return candidate
    except Exception:
        pass
    return {
        "schema": "aurum.appearance-preview.v1",
        "status": "default",
        "theme": "default",
        "background_start": "#050706",
        "background_end": "#070b09",
        "temporary": True,
        "resets_on_reboot": True,
        "tracked_source_modified": False,
    }


PAGE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="aurum-csrf" content="{{CSRF}}">
<title>Aurum · Hopper</title>
<style nonce="{{NONCE}}">
:root{--bg:#050706;--bg-end:#070b09;--panel:#0b100f;--panel2:#0f1514;--gold:#d3a640;--gold2:#f1ca65;--gold3:#70551f;--teal:#13c6ca;--teal2:#78ece7;--ink:#f2eee2;--muted:#8c948f;--line:rgba(211,166,64,.28);--line2:rgba(19,198,202,.25);--bad:#ef7777;--good:#69d6ae}
*{box-sizing:border-box}html,body{height:100%;margin:0}body{background:radial-gradient(circle at 50% -20%,rgba(19,198,202,.06),transparent 38rem),linear-gradient(180deg,#050706,#070b09);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;overflow:hidden}button,input,textarea{font:inherit}.shell{height:100vh;display:grid;grid-template-columns:174px 1fr;grid-template-rows:68px 1fr 74px}.top{grid-column:1/3;border-bottom:1px solid var(--line);display:flex;align-items:center;padding:0 24px;gap:28px;background:rgba(4,7,6,.96)}.brand{display:flex;align-items:center;gap:12px;min-width:210px}.sigil{width:38px;height:38px;border:1px solid var(--gold);display:grid;place-items:center;transform:rotate(45deg);box-shadow:0 0 22px rgba(211,166,64,.16)}.sigil b{transform:rotate(-45deg);font-size:19px;color:var(--gold2)}.brand-name{letter-spacing:.29em;color:var(--gold2);font-weight:720}.search{flex:1;max-width:560px;position:relative}.search input{width:100%;border:1px solid rgba(255,255,255,.09);background:#0a0e0d;color:var(--ink);border-radius:9px;padding:11px 15px;outline:none}.search input:focus{border-color:var(--gold)}.statusbar{margin-left:auto;display:flex;align-items:center;gap:18px;font-size:12px}.mini{display:flex;align-items:center;gap:8px;color:var(--muted)}.mini strong{color:var(--ink);font-weight:600}.online-dot{width:7px;height:7px;border-radius:50%;background:var(--good);box-shadow:0 0 12px var(--good)}.wifi{width:28px;height:18px;position:relative}.wifi i{position:absolute;left:50%;bottom:0;transform:translateX(-50%);border:1.8px solid var(--teal);border-radius:50%;opacity:.28}.wifi i:nth-child(1){width:6px;height:3px;opacity:1}.wifi i:nth-child(2){width:16px;height:8px;opacity:.75}.wifi i:nth-child(3){width:27px;height:14px;opacity:.48}.rail{grid-row:2/4;border-right:1px solid var(--line);padding:18px 12px;background:#070a08;display:flex;flex-direction:column;gap:7px}.nav{height:43px;border:1px solid transparent;border-radius:7px;background:transparent;color:#9fa59f;text-align:left;padding:0 13px;cursor:pointer;display:flex;align-items:center;gap:11px}.nav span:first-child{width:19px;color:var(--gold)}.nav:hover,.nav.active{color:var(--gold2);border-color:var(--line);background:linear-gradient(90deg,rgba(211,166,64,.12),transparent)}.rail-foot{margin-top:auto;border-top:1px solid var(--line);padding-top:14px;font-size:10px;line-height:1.5;color:#66706a}.main{grid-column:2;grid-row:2;overflow:auto;padding:24px 28px 30px}.hero{height:150px;border-bottom:1px solid var(--line);position:relative;overflow:hidden;margin-bottom:20px}.hero h1{font-weight:420;font-size:32px;margin:6px 0;color:var(--gold2)}.hero p{margin:0;color:var(--muted);font-size:13px}.canopy{position:absolute;right:0;top:0;width:58%;height:145px;opacity:.86}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.card{min-height:174px;border:1px solid var(--line);background:linear-gradient(145deg,rgba(13,19,17,.94),rgba(6,9,8,.96));border-radius:7px;padding:15px;position:relative;overflow:hidden;transition:.16s ease}.card:hover{border-color:rgba(241,202,101,.55);transform:translateY(-1px)}.card h2{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--gold2);margin:0 0 10px}.state{display:flex;align-items:center;gap:7px;color:var(--good);font-size:11px;margin-bottom:18px}.metric{display:flex;align-items:center;justify-content:space-between;margin:9px 0;font-size:12px}.metric span:first-child{color:var(--muted)}.metric b{font-weight:600}.bar{height:4px;border-radius:9px;background:#202823;overflow:hidden;margin-top:5px}.bar>i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--gold),var(--teal));transition:width .4s ease}.big{font-size:35px;color:var(--gold2);font-weight:320;line-height:1}.sub{font-size:10px;color:var(--muted);margin-top:7px}.action{position:absolute;left:12px;right:12px;bottom:11px;border:1px solid rgba(211,166,64,.2);background:#0b0e0c;color:#d7d0bc;border-radius:5px;padding:7px 9px;cursor:pointer;font-size:10px;text-align:left}.action:hover{border-color:var(--teal);color:var(--teal2)}.dock{grid-column:2;grid-row:3;border-top:1px solid var(--line);background:rgba(5,8,6,.98);padding:10px 28px;display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center}.prompt-wrap{display:flex;gap:9px}.prompt-wrap input{height:48px;flex:1;border:1px solid rgba(255,255,255,.10);border-radius:7px;background:#0a0e0c;color:var(--ink);padding:0 12px;outline:none}.prompt-wrap input:focus{border-color:var(--gold)}.key{width:160px;border:1px solid rgba(255,255,255,.09);border-radius:7px;background:#0a0e0c;color:var(--ink);padding:0 10px;outline:none}.send{height:48px;border:1px solid var(--gold);background:rgba(211,166,64,.10);color:var(--gold2);border-radius:7px;padding:0 20px;cursor:pointer}.send:hover{background:rgba(211,166,64,.18)}.toast{position:fixed;right:24px;bottom:92px;max-width:560px;border:1px solid var(--line);background:#0b100e;padding:14px 16px;border-radius:8px;box-shadow:0 18px 60px #0008;font-size:12px;line-height:1.5;white-space:pre-wrap;display:none;z-index:20}.toast.show{display:block}.teal{color:var(--teal2)}.unknown{color:#817864}@media(max-width:1150px){.grid{grid-template-columns:repeat(2,1fr)}.statusbar .hide-mid{display:none}}@media(max-width:720px){body{overflow:auto}.shell{display:block}.top{position:sticky;top:0;z-index:10}.rail{display:none}.main{padding:18px}.grid{grid-template-columns:1fr}.dock{position:sticky;bottom:0;grid-template-columns:1fr}.key{display:none}.canopy{opacity:.35;width:100%}}
.main{display:grid;grid-template-columns:minmax(0,1fr) 390px;grid-template-rows:150px minmax(0,1fr);gap:20px;overflow:hidden}.hero{grid-column:1/3;margin:0}.grid{grid-column:1;grid-row:2;grid-template-columns:repeat(2,minmax(0,1fr));overflow:auto;padding-right:5px;align-content:start}.dock{grid-template-columns:minmax(0,1fr) auto}.prompt-wrap{align-items:center;min-width:0}.key{display:none}.gpt-chip{height:32px;display:flex;align-items:center;gap:8px;border:1px solid var(--line2);border-radius:999px;padding:0 11px;color:var(--teal2);font-size:10px;letter-spacing:.08em;text-transform:uppercase;white-space:nowrap;background:rgba(19,198,202,.06)}.gpt-chip i{width:6px;height:6px;border-radius:50%;background:var(--teal);box-shadow:0 0 11px var(--teal)}.send{background:linear-gradient(135deg,rgba(211,166,64,.18),rgba(19,198,202,.08));transition:.18s ease}.send:hover{background:linear-gradient(135deg,rgba(211,166,64,.28),rgba(19,198,202,.14));box-shadow:0 0 26px rgba(211,166,64,.12)}.send:disabled{opacity:.45;cursor:wait}.chat-panel{grid-column:2;grid-row:2;min-height:0;border:1px solid var(--line);border-radius:9px;background:radial-gradient(circle at 90% 0,rgba(19,198,202,.09),transparent 45%),linear-gradient(160deg,rgba(13,19,17,.98),rgba(5,8,7,.98));display:grid;grid-template-rows:auto 1fr auto;overflow:hidden;box-shadow:0 22px 70px #0006}.chat-head{padding:14px 15px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:10px}.mind-orb{width:30px;height:30px;position:relative;display:grid;place-items:center;border:1px solid var(--gold);transform:rotate(45deg);background:rgba(211,166,64,.06);box-shadow:0 0 18px rgba(211,166,64,.12)}.mind-orb::after{content:'A';transform:rotate(-45deg);color:var(--gold2);font-size:12px;font-weight:750}.mind-orb.thinking{animation:pulse 1.1s ease-in-out infinite}.chat-title{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--gold2)}.chat-sub{font-size:9px;color:var(--muted);margin-top:3px}.clear-chat{margin-left:auto;border:0;background:transparent;color:var(--muted);font-size:10px;cursor:pointer}.clear-chat:hover{color:var(--teal2)}.messages{min-height:0;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:13px}.message{max-width:88%;border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:10px 12px;font-size:12px;line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere;animation:arrive .2s ease-out}.message.aurum{align-self:flex-start;background:rgba(211,166,64,.07);border-color:var(--line)}.message.user{align-self:flex-end;background:rgba(19,198,202,.08);border-color:var(--line2)}.message.error{border-color:rgba(239,119,119,.45);color:#ffc1c1}.message.thinking{color:var(--muted)}.message.thinking::after{content:' ···';color:var(--teal2);animation:blink 1s steps(2,end) infinite}.receipt-stack{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.receipt{border:1px solid var(--line2);border-radius:999px;padding:4px 7px;color:var(--teal2);font-size:9px;background:rgba(19,198,202,.05)}.suggestions{padding:0 14px 14px;display:flex;flex-wrap:wrap;gap:6px}.suggestion{border:1px solid rgba(255,255,255,.08);border-radius:999px;background:#0a0e0c;color:var(--muted);font-size:9px;padding:6px 9px;cursor:pointer}.suggestion:hover{color:var(--gold2);border-color:var(--line)}@keyframes arrive{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}@keyframes pulse{50%{box-shadow:0 0 28px rgba(19,198,202,.5);border-color:var(--teal)}}@keyframes blink{50%{opacity:.2}}@media(max-width:1150px){.main{grid-template-columns:minmax(0,1fr) 340px}.grid{grid-template-columns:1fr}}@media(max-width:860px){.main{padding:18px;display:block;overflow:auto}.hero{margin-bottom:18px}.grid{grid-template-columns:1fr;overflow:visible}.chat-panel{position:fixed;inset:82px 14px 86px 14px;z-index:15}.gpt-chip{display:none}}
body::before{content:"";position:fixed;inset:0;pointer-events:none;background-image:linear-gradient(rgba(211,166,64,.018) 1px,transparent 1px),linear-gradient(90deg,rgba(19,198,202,.014) 1px,transparent 1px);background-size:42px 42px;mask-image:linear-gradient(to bottom,black,transparent 82%)}body::after{content:"";position:fixed;inset:0;pointer-events:none;opacity:.22;background:radial-gradient(circle at 82% 18%,rgba(19,198,202,.13),transparent 24rem),radial-gradient(circle at 14% 86%,rgba(211,166,64,.08),transparent 30rem)}.top,.rail,.dock,.main{position:relative;z-index:1}.top{background:linear-gradient(90deg,rgba(4,7,6,.985),rgba(6,10,9,.965));box-shadow:0 10px 40px #0007}.brand{min-width:224px}.brand-copy{display:flex;flex-direction:column;gap:2px}.brand-sub{font-size:8px;letter-spacing:.16em;text-transform:uppercase;color:var(--teal2);opacity:.72}.logo-life{position:relative;isolation:isolate;display:grid;place-items:center;flex:0 0 auto}.logo-life canvas{display:block;width:100%;height:100%;object-fit:contain;filter:drop-shadow(0 0 7px rgba(211,166,64,.24));position:relative;z-index:3}.logo-life::before,.logo-life::after{content:"";position:absolute;border-radius:50%;pointer-events:none}.logo-life::before{inset:6%;border:1px solid rgba(211,166,64,.30);box-shadow:inset 0 0 20px rgba(19,198,202,.05),0 0 20px rgba(211,166,64,.06);animation:logo-breathe 5s ease-in-out infinite}.logo-life::after{width:6px;height:6px;top:5%;left:50%;background:var(--teal);box-shadow:0 0 12px var(--teal);transform-origin:0 calc(var(--orbit-radius,26px));animation:logo-orbit 7s linear infinite}.logo-life--mini{width:46px;height:46px;--orbit-radius:19px}.logo-life--mini canvas{width:38px;height:38px}.hero{height:auto;min-height:150px;border:1px solid rgba(211,166,64,.16);border-radius:11px;padding:22px 25px;background:linear-gradient(112deg,rgba(12,18,16,.94) 0%,rgba(8,13,12,.86) 58%,rgba(8,16,15,.72) 100%);box-shadow:inset 0 1px rgba(255,255,255,.025),0 18px 55px #0005}.hero::before{content:"";position:absolute;inset:0;background:linear-gradient(90deg,transparent 0 56%,rgba(19,198,202,.035)),repeating-linear-gradient(135deg,transparent 0 22px,rgba(211,166,64,.012) 23px 24px);pointer-events:none}.hero-copy{position:relative;z-index:4;width:62%}.hero-kicker{display:flex;align-items:center;gap:8px;font-size:10px;letter-spacing:.18em}.hero-kicker::before{content:"";width:24px;height:1px;background:var(--teal);box-shadow:0 0 9px var(--teal)}.hero h1{font-size:31px;margin:10px 0 7px;letter-spacing:-.02em}.hero-status{display:flex;gap:8px;margin-top:16px;flex-wrap:wrap}.hero-status span{border:1px solid rgba(255,255,255,.08);border-radius:999px;padding:5px 9px;font-size:8px;letter-spacing:.12em;text-transform:uppercase;color:#aeb8b1;background:#080c0b99}.hero-status span:first-child{border-color:var(--line2);color:var(--teal2)}.hero-life{position:absolute;right:3.5%;top:50%;width:34%;height:138%;transform:translateY(-50%);display:grid;place-items:center}.logo-life--hero{width:152px;height:152px;--orbit-radius:68px}.logo-life--hero canvas{width:126px;height:126px;animation:logo-float 5.8s ease-in-out infinite}.logo-life--hero::before{inset:3%;border-color:rgba(211,166,64,.25);box-shadow:inset 0 0 42px rgba(19,198,202,.07),0 0 35px rgba(211,166,64,.08)}.orbit-ring{position:absolute;border:1px solid rgba(19,198,202,.16);border-radius:50%;pointer-events:none}.orbit-ring.one{inset:-9%;transform:rotate(14deg) scaleY(.72);animation:ring-turn 15s linear infinite}.orbit-ring.two{inset:-24%;border-color:rgba(211,166,64,.11);transform:rotate(-19deg) scaleY(.62);animation:ring-turn-reverse 22s linear infinite}.life-circuit{position:absolute;inset:0;width:100%;height:100%;opacity:.62;overflow:visible}.life-circuit path{fill:none;stroke:rgba(19,198,202,.50);stroke-width:1;stroke-dasharray:5 7;animation:circuit-flow 6s linear infinite}.life-circuit circle{fill:var(--gold2);filter:drop-shadow(0 0 4px var(--gold))}.card{border-color:rgba(211,166,64,.20);border-radius:10px;box-shadow:inset 0 1px rgba(255,255,255,.02),0 14px 32px #0003}.card::before{content:"";position:absolute;inset:0 auto auto 0;width:48%;height:1px;background:linear-gradient(90deg,var(--gold),transparent);opacity:.48}.card::after{content:"";position:absolute;width:90px;height:90px;right:-42px;top:-42px;border:1px solid rgba(19,198,202,.09);border-radius:50%;box-shadow:0 0 40px rgba(19,198,202,.025)}.card:nth-child(3n+2)::before{background:linear-gradient(90deg,var(--teal),transparent)}.card:hover{box-shadow:inset 0 1px rgba(255,255,255,.035),0 18px 38px #0006,0 0 26px rgba(211,166,64,.035)}.chat-panel{border-radius:12px;border-color:rgba(211,166,64,.24);box-shadow:inset 0 1px rgba(255,255,255,.025),0 24px 70px #0008}.chat-head{background:linear-gradient(90deg,rgba(211,166,64,.055),rgba(19,198,202,.035))}.mind-orb{width:40px;height:40px;transform:none;border:0;background:transparent;box-shadow:none;--orbit-radius:16px}.mind-orb::after{width:5px;height:5px;content:"";transform-origin:0 var(--orbit-radius);color:transparent;font-size:0}.mind-orb::before{inset:5%}.mind-orb canvas{width:34px;height:34px}.mind-orb.thinking{animation:none}.mind-orb.thinking::before,.aurum-thinking .logo-life::before{border-color:var(--teal);box-shadow:inset 0 0 24px rgba(19,198,202,.14),0 0 30px rgba(19,198,202,.28);animation:thinking-breathe .75s ease-in-out infinite}.mind-orb.thinking::after,.aurum-thinking .logo-life--hero::after{animation-duration:1.1s}.message{backdrop-filter:blur(7px)}.dock{box-shadow:0 -16px 42px #0005}.send{min-width:132px;font-weight:650;letter-spacing:.04em}@keyframes logo-breathe{0%,100%{opacity:.46;transform:scale(.98)}50%{opacity:.92;transform:scale(1.025)}}@keyframes logo-orbit{to{transform:rotate(360deg)}}@keyframes logo-float{0%,100%{transform:translateY(2px)}50%{transform:translateY(-4px)}}@keyframes ring-turn{to{transform:rotate(374deg) scaleY(.72)}}@keyframes ring-turn-reverse{to{transform:rotate(-379deg) scaleY(.62)}}@keyframes circuit-flow{to{stroke-dashoffset:-48}}@keyframes thinking-breathe{50%{opacity:1;transform:scale(1.07)}}@media(max-width:860px){.hero-copy{width:74%}.hero-life{right:-4%;opacity:.68}.logo-life--hero{width:126px;height:126px}.brand-sub{display:none}}@media(max-width:560px){.hero-copy{width:100%}.hero-life{opacity:.22;right:-18%}.search{display:none}.brand{min-width:0}.hero h1{font-size:27px}}@media(prefers-reduced-motion:reduce){.logo-life::before,.logo-life::after,.logo-life canvas,.orbit-ring,.life-circuit path,.mind-orb.thinking::before{animation:none!important}.card,.send{transition:none!important}}
.logo-crop{position:relative;overflow:hidden;isolation:isolate;background:#000;flex:0 0 auto}.logo-crop img{position:absolute;display:block;max-width:none;height:auto;filter:drop-shadow(0 0 8px rgba(211,166,64,.18));transition:filter .35s ease,transform .35s ease}.logo-crop--landscape{aspect-ratio:2.778/1}.logo-crop--landscape img{width:250.8%;left:-144%;top:-411.1%}.logo-crop--icon{aspect-ratio:1/1;border-radius:11px}.logo-crop--icon img{width:451.1%;left:-351.1%;top:-351.4%}.logo-crop.logo-ready img{filter:drop-shadow(0 0 11px rgba(211,166,64,.25))}.brand{min-width:190px}.logo-crop--header{width:170px;border-radius:3px}.hero-copy{width:56%}.hero-life{right:1.5%;width:42%;height:132%}.logo-life--hero{width:min(390px,92%);height:auto;aspect-ratio:2.778/1;--orbit-radius:62px}.logo-life--hero .logo-crop{width:100%;z-index:3;animation:logo-float 5.8s ease-in-out infinite}.logo-life--hero::before{inset:-7% -3%;border-radius:50%;border-color:rgba(211,166,64,.20)}.logo-life--hero::after{width:23%;height:1px;left:5%;top:50%;border-radius:0;background:linear-gradient(90deg,transparent,var(--teal),transparent);box-shadow:0 0 10px var(--teal);transform-origin:center;animation:logo-scan 4.8s ease-in-out infinite;z-index:5}.orbit-ring.one{inset:-12% -7%;transform:rotate(3deg) scaleY(.68)}.orbit-ring.two{inset:-25% -13%;transform:rotate(-4deg) scaleY(.55)}.mind-orb{overflow:visible}.mind-orb .logo-crop{width:36px;height:36px;z-index:3}.mind-orb::before{inset:-1%;border-radius:12px}.mind-orb::after{top:0;left:50%}.aurum-thinking .logo-crop img{filter:drop-shadow(0 0 17px rgba(19,198,202,.50)) brightness(1.08)}@keyframes logo-scan{0%,100%{transform:translateX(0);opacity:.2}50%{transform:translateX(290%);opacity:.9}}@media(max-width:1040px){.logo-crop--header{width:150px}.brand{min-width:165px}.hero-copy{width:58%}.logo-life--hero{width:min(340px,94%)}}@media(max-width:860px){.hero-copy{width:67%}.hero-life{right:-8%;width:46%;opacity:.7}.logo-life--hero{width:300px}.logo-crop--header{width:140px}}@media(max-width:560px){.hero-copy{width:100%}.hero-life{right:-30%;width:78%;opacity:.19}.logo-life--hero{width:300px}.logo-crop--header{width:128px}}@media(prefers-reduced-motion:reduce){.logo-life--hero .logo-crop,.logo-life--hero::after{animation:none!important}.logo-crop img{transition:none!important}}
.web-browser[hidden],.web-frame[hidden],.web-home[hidden]{display:none!important}.web-browser{position:absolute;inset:24px 28px 30px;min-width:0;min-height:0;z-index:12;border:1px solid rgba(211,166,64,.30);border-radius:13px;background:#070b0a;box-shadow:0 28px 90px #000b;overflow:hidden;display:grid;grid-template-rows:auto 1fr auto}.web-toolbar{min-height:58px;display:grid;grid-template-columns:auto minmax(230px,1fr) auto;gap:10px;align-items:center;padding:9px 12px;border-bottom:1px solid var(--line);background:linear-gradient(90deg,rgba(211,166,64,.07),rgba(19,198,202,.035))}.web-controls,.web-actions{display:flex;align-items:center;gap:6px}.web-button{height:38px;min-width:38px;border:1px solid rgba(255,255,255,.10);border-radius:8px;background:#0b100e;color:#b6bdb8;cursor:pointer;padding:0 11px}.web-button:hover,.web-button:focus-visible{border-color:var(--gold);color:var(--gold2);outline:none}.web-button.primary{border-color:var(--gold);color:var(--gold2);background:rgba(211,166,64,.10);font-weight:650}.web-button.close{font-size:18px;color:var(--muted)}.web-address{height:40px;min-width:0;display:flex;align-items:center;gap:10px;border:1px solid rgba(255,255,255,.11);border-radius:10px;background:#050807;padding:0 12px}.web-address:focus-within{border-color:var(--teal);box-shadow:0 0 0 2px rgba(19,198,202,.07)}.web-lock{color:var(--teal2);font-size:12px}.web-address input{width:100%;min-width:0;border:0;outline:0;background:transparent;color:var(--ink);font-size:13px}.web-home{min-height:0;display:grid;place-items:center;padding:34px;overflow:auto;background:radial-gradient(circle at 50% 18%,rgba(19,198,202,.09),transparent 24rem),radial-gradient(circle at 50% 92%,rgba(211,166,64,.07),transparent 26rem)}.web-welcome{width:min(650px,92%);text-align:center}.web-mark{width:min(360px,86%);margin:0 auto 30px;border-radius:5px;box-shadow:0 0 40px rgba(211,166,64,.08)}.web-welcome h2{margin:0;color:var(--gold2);font-size:29px;font-weight:430}.web-welcome p{color:var(--muted);font-size:13px;line-height:1.65;margin:10px auto 24px;max-width:520px}.web-search-home{display:flex;gap:8px;margin:auto;max-width:560px}.web-search-home input{flex:1;min-width:0;height:45px;border:1px solid var(--line);border-radius:9px;background:#090d0c;color:var(--ink);padding:0 14px;outline:none}.web-search-home input:focus{border-color:var(--teal)}.web-guardrails{display:flex;justify-content:center;gap:8px;flex-wrap:wrap;margin-top:22px}.web-guardrails span{border:1px solid rgba(255,255,255,.08);border-radius:999px;padding:6px 9px;color:#8f9993;font-size:9px;letter-spacing:.08em;text-transform:uppercase}.web-guardrails span:first-child{border-color:var(--line2);color:var(--teal2)}.web-frame{width:100%;height:100%;min-height:0;border:0;background:#fff}.web-foot{min-height:31px;padding:7px 12px;border-top:1px solid rgba(255,255,255,.07);display:flex;align-items:center;justify-content:space-between;gap:12px;color:#758079;font-size:9px;letter-spacing:.05em;background:#070a09}.web-foot strong{color:var(--teal2);font-weight:560}.web-browser.loading .web-foot strong::after{content:' · loading';color:var(--gold2)}@media(max-width:900px){.web-toolbar{grid-template-columns:auto 1fr}.web-actions{grid-column:1/3;justify-content:flex-end}.web-actions .web-open-label{display:none}}@media(max-width:650px){.web-toolbar{grid-template-columns:1fr}.web-controls{order:2}.web-address{order:1}.web-actions{grid-column:1;order:3}.web-button{padding:0 9px}.web-welcome{width:100%}}
.web-home{padding:24px}.web-mark{width:min(330px,82%);margin-bottom:20px}.web-welcome p{margin:8px auto 18px}.web-guardrails{margin-top:16px}
body{background:radial-gradient(circle at 50% -20%,rgba(19,198,202,.06),transparent 38rem),linear-gradient(180deg,var(--bg),var(--bg-end))}

.wifi-panel{grid-column:1;grid-row:2;min-height:0;border:1px solid var(--line);border-radius:9px;background:radial-gradient(circle at 90% 0,rgba(19,198,202,.08),transparent 45%),linear-gradient(160deg,rgba(13,19,17,.98),rgba(5,8,7,.98));padding:18px;overflow:auto}.wifi-panel[hidden],.grid[hidden]{display:none!important}.wifi-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding-bottom:14px;border-bottom:1px solid var(--line)}.wifi-head h2{margin:4px 0;color:var(--gold2);font-size:26px;font-weight:420}.wifi-head p{margin:0;color:var(--muted);font-size:11px}.wifi-layout{display:grid;grid-template-columns:340px minmax(0,1fr);gap:14px;margin-top:16px}.wifi-form,.wifi-results{border:1px solid var(--line);border-radius:8px;background:#0a0e0c;padding:14px}.wifi-form label{display:block;color:var(--muted);font-size:9px;letter-spacing:.08em;text-transform:uppercase;margin:10px 0 5px}.wifi-form input{width:100%;height:40px;border:1px solid rgba(255,255,255,.10);border-radius:6px;background:#070b09;color:var(--ink);padding:0 10px;outline:none}.wifi-form input:focus{border-color:var(--gold)}.wifi-actions{display:flex;flex-wrap:wrap;gap:7px;margin-top:13px}.wifi-button{border:1px solid var(--line);border-radius:6px;background:#0a0e0c;color:var(--ink);padding:8px 11px;cursor:pointer}.wifi-button:hover{border-color:var(--teal);color:var(--teal2)}.wifi-button.primary{border-color:var(--gold);color:var(--gold2);background:rgba(211,166,64,.10)}.wifi-detail{margin-top:12px;color:var(--muted);font-size:10px;line-height:1.45}.wifi-results-title{color:var(--gold2);font-size:11px;letter-spacing:.1em;text-transform:uppercase;margin-bottom:10px}.wifi-networks{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.wifi-network{border:1px solid rgba(255,255,255,.08);border-radius:6px;background:#070b09;color:var(--ink);padding:9px;text-align:left;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.wifi-network:hover{border-color:var(--teal);color:var(--teal2)}@media(max-width:1150px){.wifi-layout{grid-template-columns:1fr}.wifi-networks{grid-template-columns:1fr}}
</style>
</head>
<body data-hopper-profile="gen1-html">
<div class="shell">
<header class="top">
  <div class="brand"><div class="logo-crop logo-crop--landscape logo-crop--header" aria-label="Aurum"><img data-aurum-logo src="/assets/aurum-seven-leaf-logo.jpeg" alt=""></div></div>
  <div class="search"><input id="search" placeholder="Search Aurum systems…" aria-label="Search Aurum systems"></div>
  <div class="statusbar">
    <div class="mini"><span class="online-dot"></span><strong id="machine">Hopper</strong></div>
    <div class="mini hide-mid"><div class="wifi"><i></i><i></i><i></i></div><strong id="wifi">Unknown</strong></div>
    <div class="mini"><strong id="battery">—</strong></div>
    <div class="mini"><strong id="clock">Time</strong></div>
  </div>
</header>
<nav class="rail">
  <button class="nav active" data-nav="home"><span>⌂</span>Home</button>
  <button class="nav" data-nav="browser"><span>◎</span>Browser</button>
  <button class="nav" data-nav="wifi"><span>⌁</span>Wi-Fi</button>
  <button class="nav" data-nav="traits"><span>⌁</span>Traits</button>
  <button class="nav" data-nav="build"><span>◇</span>Build</button>
  <button class="nav" data-nav="hardware"><span>▣</span>Hardware</button>
  <button class="nav" data-nav="field"><span>⌬</span>Field</button>
  <button class="nav" data-nav="settings"><span>⚙</span>Settings</button>
  <div class="rail-foot">GEN1 POLISHED PHYSICAL SURFACE<br>HTML PROJECTION · PYGame fallback</div>
</nav>
<main class="main">
  <section class="hero">
    <div class="hero-copy"><div class="teal hero-kicker">LIVE MACHINE PROJECTION</div><h1 id="greeting">Good afternoon, Aurum User.</h1><p>Aurum adapts the human view. Machine truth stays underneath.</p><div class="hero-status"><span>HTML5 living surface</span><span>AinWeave · StateWeave · ComputeWeave</span></div></div>
    <div class="hero-life" aria-hidden="true"><svg class="life-circuit" viewBox="0 0 420 210"><path d="M0 55h78l28 25h67M14 164h94l24-21h73M252 34h70l23 25h75M274 174h53l27-24h66"/><circle cx="106" cy="80" r="3"/><circle cx="132" cy="143" r="3"/><circle cx="345" cy="59" r="3"/><circle cx="354" cy="150" r="3"/></svg><div class="logo-life logo-life--hero"><span class="orbit-ring one"></span><span class="orbit-ring two"></span><div class="logo-crop logo-crop--landscape"><img data-aurum-logo src="/assets/aurum-seven-leaf-logo.jpeg" alt=""></div></div></div>
  </section>
  <section class="grid">
    <article class="card"><h2>System Runtime</h2><div class="state"><span class="online-dot"></span><span id="runtime-state">Unknown</span></div><div class="metric"><span>Uptime</span><b id="uptime">—</b></div><div class="metric"><span>Desktop</span><b id="desktop">—</b></div><div class="metric"><span>Autonomy</span><b id="autonomy">—</b></div><button class="action" data-action="runtime-plan">View runtime plan →</button></article>
    <article class="card"><h2>Network</h2><div class="state"><span class="online-dot"></span><span id="net-state">Unknown</span></div><div class="metric"><span>Connection</span><b id="ssid">Unknown</b></div><div class="metric"><span>Interface</span><b id="net-if">Unknown</b></div><div class="metric"><span>Address</span><b id="net-ip">Unknown</b></div><button class="action" data-action="network-reconnect">Reconnect network →</button></article>
    <article class="card"><h2>Power & Battery</h2><div class="state"><span class="online-dot"></span><span id="power-state">Unknown</span></div><div class="big" id="battery-big">—</div><div class="sub" id="battery-sub">Battery state unknown</div><button class="action" data-action="status">Refresh power evidence →</button></article>
    <article class="card"><h2>GPT Trait</h2><div class="state"><span class="online-dot"></span><span id="gpt-state">Checking</span></div><div class="metric"><span>Control</span><b>Bounded</b></div><div class="metric"><span>Shell</span><b>Off</b></div><div class="metric"><span>Tools</span><b id="gpt-tools">—</b></div><button class="action" id="focus-gpt">Talk to GPT →</button></article>
    <article class="card"><h2>Build</h2><div class="state"><span class="online-dot"></span><span>Evidence first</span></div><div class="metric"><span>Generation</span><b>Gen1</b></div><div class="metric"><span>Projection</span><b>HTML5</b></div><div class="metric"><span>Fallback</span><b>Pygame</b></div><button class="action" data-action="runtime-sync">Apply verified runtime →</button></article>
    <article class="card"><h2>Hardware</h2><div class="state"><span class="online-dot"></span><span>Live metrics</span></div><div class="metric"><span>Memory</span><b id="memory">—</b></div><div class="bar"><i id="memory-bar"></i></div><div class="metric"><span>Storage</span><b id="storage">—</b></div><div class="bar"><i id="storage-bar"></i></div><button class="action" data-action="status">Refresh hardware →</button></article>
    <article class="card"><h2>Input & Recovery</h2><div class="state"><span class="online-dot"></span><span id="input-state">Unknown</span></div><div class="metric"><span>Human surface</span><b>HTML events</b></div><div class="metric"><span>Recovery</span><b>Pygame fallback</b></div><button class="action" data-action="input-recover">Recover input →</button></article>
    <article class="card"><h2>System Tools</h2><div class="state"><span class="online-dot"></span><span>Bounded actions</span></div><div class="metric"><span>Time</span><b id="time-state">Unknown</b></div><div class="metric"><span>Renderer</span><b>HTML5</b></div><button class="action" data-action="time-sync">Synchronize time →</button></article>
  </section>
  <aside class="chat-panel" aria-label="Aurum conversation">
    <div class="chat-head"><div id="mind-orb" class="mind-orb logo-life" aria-hidden="true"><div class="logo-crop logo-crop--icon"><img data-aurum-logo src="/assets/aurum-seven-leaf-logo.jpeg" alt=""></div></div><div><div class="chat-title">Aurum GPT</div><div class="chat-sub">Bounded tools · receipts visible · raw shell off</div></div><button id="clear-chat" class="clear-chat">Clear</button></div>
    <div id="messages" class="messages" aria-live="polite"><div class="message aurum">I’m connected to Hopper’s live Aurum state. Ask me to inspect the machine, explain what it sees, or use a bounded action. Any local action returns a receipt here.</div></div>
    <div class="suggestions"><button class="suggestion" data-prompt="Give me a plain-language Hopper health check.">Health check</button><button class="suggestion" data-prompt="Show what Aurum can safely control on Hopper.">What can you do?</button><button class="suggestion" data-prompt="Inspect the current seed state and tell me what should grow next.">What grows next?</button></div>
  </aside>
  <section id="wifi-panel" class="wifi-panel" aria-label="Wi-Fi controls" hidden>
    <div class="wifi-head"><div><div class="teal">WIRELESS NETWORK</div><h2>Wi-Fi</h2><p>Scan, select, connect, disconnect, or forget the saved network directly from TinySeed.</p></div><button id="wifi-scan" class="wifi-button" type="button">Scan</button></div>
    <div class="wifi-layout">
      <div class="wifi-form"><label>Network name (SSID)</label><input id="wifi-ssid" maxlength="32" autocomplete="off" placeholder="Select a network or type its SSID"><label>Password</label><input id="wifi-password" type="password" maxlength="128" autocomplete="new-password" placeholder="Blank for an open network"><div class="wifi-actions"><button id="wifi-connect" class="wifi-button primary" type="button">Connect</button><button id="wifi-disconnect" class="wifi-button" type="button">Disconnect</button><button id="wifi-forget" class="wifi-button" type="button">Forget saved</button></div><div id="wifi-detail" class="wifi-detail">Use Scan to discover nearby networks.</div></div>
      <div class="wifi-results"><div class="wifi-results-title">Available networks</div><div id="wifi-networks" class="wifi-networks"></div></div>
    </div>
  </section>
  <section id="web-browser" class="web-browser" aria-label="Aurum web browser" hidden>
    <div class="web-toolbar">
      <div class="web-controls"><button id="web-back" class="web-button" aria-label="Back">←</button><button id="web-forward" class="web-button" aria-label="Forward">→</button><button id="web-reload" class="web-button" aria-label="Reload">↻</button><button id="web-home-button" class="web-button" aria-label="Browser home">⌂</button></div>
      <form id="web-form" class="web-address"><span class="web-lock" aria-hidden="true">◇</span><input id="web-address" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="Web address or search" placeholder="Search the web or enter an HTTPS address"></form>
      <div class="web-actions"><button id="web-go" class="web-button primary" type="submit" form="web-form">Go</button><button id="web-open" class="web-button" type="button" title="Open this site in a separate browser window"><span class="web-open-label">Full page </span>↗</button><button id="web-close" class="web-button close" type="button" aria-label="Close browser">×</button></div>
    </div>
    <div id="web-home" class="web-home">
      <div class="web-welcome"><div class="logo-crop logo-crop--landscape web-mark"><img data-aurum-logo src="/assets/aurum-seven-leaf-logo.jpeg" alt="Aurum"></div><h2>Where do you want to go?</h2><p>A simple browser grown into Aurum’s HTML surface. Search the public web or enter a secure address. Local machine and private-network addresses stay outside this view.</p><form id="web-home-form" class="web-search-home"><input id="web-home-query" autocomplete="off" aria-label="Search the web" placeholder="Search the web"><button class="web-button primary" type="submit">Search</button></form><div class="web-guardrails"><span>HTTPS only</span><span>Local network blocked</span><span>No Aurum proxy</span><span>No shell</span></div></div>
    </div>
    <iframe id="web-frame" class="web-frame" title="Web page" sandbox="allow-forms allow-scripts" referrerpolicy="no-referrer" hidden></iframe>
    <div class="web-foot"><span id="web-status"><strong>Ready</strong> · browsing stays separate from GPT control</span><span>Some sites may require Full page ↗</span></div>
  </section>
</main>
<footer class="dock">
  <div class="prompt-wrap"><div id="gpt-chip" class="gpt-chip"><i></i><span>Connecting GPT</span></div><input id="prompt" type="text" maxlength="12000" autocomplete="off" placeholder="Ask Aurum about Hopper…" aria-label="Ask Aurum GPT"></div>
  <button id="send" class="send">Send to Aurum</button>
</footer>
</div>
<div id="toast" class="toast"></div>
<script nonce="{{NONCE}}">
const csrf=document.querySelector('meta[name="aurum-csrf"]').content;
const toast=document.getElementById('toast');
const prompt=document.getElementById('prompt');
const send=document.getElementById('send');
const messages=document.getElementById('messages');
const orb=document.getElementById('mind-orb');
const gptChip=document.querySelector('#gpt-chip span');
const webBrowser=document.getElementById('web-browser');
const webFrame=document.getElementById('web-frame');
const webHome=document.getElementById('web-home');
const webAddress=document.getElementById('web-address');
const webStatus=document.getElementById('web-status');
const wifiPanel=document.getElementById('wifi-panel');
const gridPanel=document.querySelector('.grid');
let webHistory=[],webIndex=-1,currentWebTarget='';
function logoReady(image){const crop=image.closest('.logo-crop');if(crop)crop.classList.add('logo-ready')}
document.querySelectorAll('[data-aurum-logo]').forEach(image=>{if(image.complete&&image.naturalWidth)logoReady(image);else image.addEventListener('load',()=>logoReady(image),{once:true})});
function show(message,seconds=6){toast.textContent=message;toast.classList.add('show');clearTimeout(show.t);show.t=setTimeout(()=>toast.classList.remove('show'),seconds*1000)}
function message(kind,text,extra=''){const node=document.createElement('div');node.className=`message ${kind} ${extra}`.trim();node.textContent=text;messages.appendChild(node);messages.scrollTop=messages.scrollHeight;return node}
function receipts(node,items){if(!Array.isArray(items)||!items.length)return;const stack=document.createElement('div');stack.className='receipt-stack';items.forEach((item,index)=>{const chip=document.createElement('span');chip.className='receipt';const action=item.action||item.tool||item.operation||`tool ${index+1}`;chip.textContent=`${action} · ${item.status||'receipted'}`;stack.appendChild(chip)});node.appendChild(stack)}
function pct(id,value){const node=document.getElementById(id);if(node)node.textContent=value==null?'—':`${value}%`;const bar=document.getElementById(`${id}-bar`);if(bar)bar.style.width=value==null?'0%':`${Math.max(0,Math.min(100,value))}%`}
function humanDuration(seconds){if(seconds==null)return'—';const h=Math.floor(seconds/3600),m=Math.floor((seconds%3600)/60);return `${h}h ${m}m`}
function first(obj,keys){for(const k of keys){if(obj&&obj[k]!=null&&obj[k]!=='' )return obj[k]}return null}
function privateWebHost(host){const value=host.toLowerCase().replace(/^\[|\]$/g,'');if(!value||value==='localhost'||value.endsWith('.localhost')||value.endsWith('.local')||value.endsWith('.internal')||value.includes(':'))return true;const parts=value.split('.');if(parts.length===4&&parts.every(part=>/^\d+$/.test(part))){const octets=parts.map(Number);if(octets.some(x=>x<0||x>255))return true;const[a,b]=octets;return a===0||a===10||a===127||(a===169&&b===254)||(a===172&&b>=16&&b<=31)||(a===192&&b===168)||(a===100&&b>=64&&b<=127)||(a===198&&(b===18||b===19))||a>=224}return false}
function normalizeWebTarget(raw){const value=String(raw||'').trim();if(!value)throw new Error('Enter a search or secure web address.');const looksLikeAddress=/^(https?:\/\/)/i.test(value)||(!/\s/.test(value)&&value.includes('.'));if(!looksLikeAddress)return `https://duckduckgo.com/?q=${encodeURIComponent(value)}`;const candidate=/^[a-z][a-z0-9+.-]*:\/\//i.test(value)?value:`https://${value}`;let target;try{target=new URL(candidate)}catch{throw new Error('That web address is not valid.')}if(target.protocol!=='https:')throw new Error('Aurum browsing uses HTTPS addresses only.');if(target.username||target.password)throw new Error('Web addresses cannot contain credentials.');if(privateWebHost(target.hostname))throw new Error('Local and private-network addresses stay outside the web browser.');target.hash=target.hash||'';return target.href}
function updateWebButtons(){document.getElementById('web-back').disabled=webIndex<=0;document.getElementById('web-forward').disabled=webIndex<0||webIndex>=webHistory.length-1}
function webNavigate(raw,{record=true}={}){let target;try{target=normalizeWebTarget(raw)}catch(error){show(error.message||String(error),5);webStatus.innerHTML='<strong>Navigation blocked</strong> · check the address and try again';return false}if(record){webHistory=webHistory.slice(0,webIndex+1);webHistory.push(target);webIndex=webHistory.length-1}currentWebTarget=target;webAddress.value=target;webHome.hidden=true;webFrame.hidden=false;webBrowser.classList.add('loading');webStatus.innerHTML='<strong>Secure page</strong> · isolated from Aurum controls';webFrame.src=target;updateWebButtons();return true}
function openWebBrowser(){webBrowser.hidden=false;document.getElementById('search').placeholder='Search Aurum systems…';if(!currentWebTarget){webHome.hidden=false;webFrame.hidden=true;setTimeout(()=>document.getElementById('web-home-query').focus(),0)}else setTimeout(()=>webAddress.focus(),0)}
function closeWebBrowser(){showScreen('home');document.getElementById('search').focus()}
function webBrowserHome(){currentWebTarget='';webAddress.value='';document.getElementById('web-home-query').value='';webFrame.src='about:blank';webFrame.hidden=true;webHome.hidden=false;webBrowser.classList.remove('loading');webStatus.innerHTML='<strong>Ready</strong> · browsing stays separate from GPT control';setTimeout(()=>document.getElementById('web-home-query').focus(),0)}
async function refresh(){try{const r=await fetch('/api/status',{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||'status unavailable');const h=d.hopper||{},t=h.telemetry||{},s=t.state||{},n=t.network||{},b=t.battery||{},tm=t.time||{},g=h.gpt||{};applyAppearance(h.appearance||{});document.getElementById('machine').textContent=s.machine||'Hopper';document.getElementById('runtime-state').textContent=s.runtime||'Unknown';document.getElementById('desktop').textContent=s.desktop_generation||s.desktop||'Unknown';document.getElementById('autonomy').textContent=s.autonomy||'Unknown';document.getElementById('input-state').textContent=s.input||'Unknown';document.getElementById('uptime').textContent=humanDuration(t.uptime_seconds);pct('memory',t.memory_percent);pct('storage',t.storage_percent);const connected=first(n,['online','connected','status']);document.getElementById('net-state').textContent=connected===true?'Connected':(connected||'Unknown');const ssid=first(n,['ssid','connection','network']);document.getElementById('ssid').textContent=ssid||'Unknown';document.getElementById('wifi').textContent=ssid||'Network';document.getElementById('net-if').textContent=first(n,['interface','device'])||'Unknown';document.getElementById('net-ip').textContent=first(n,['ip','address','ipv4'])||'Unknown';document.getElementById('battery').textContent=b.percent==null?'—':`${b.percent}%`;document.getElementById('battery-big').textContent=b.percent==null?'—':`${b.percent}%`;document.getElementById('battery-sub').textContent=b.status||'Unknown';document.getElementById('power-state').textContent=b.charging?'Charging':(b.status||'Unknown');document.getElementById('gpt-state').textContent=g.status==='ready'?'Ready':(g.status||'Unknown');document.getElementById('gpt-tools').textContent=g.function_tools?'Ready':'Unavailable';gptChip.textContent=g.status==='ready'?'GPT ready on Hopper':'Sealed credential pending';document.getElementById('time-state').textContent=tm.synchronized?'Server synchronized':'Local / unknown';if(tm.local_iso){const date=new Date(tm.local_iso);if(!Number.isNaN(date.valueOf()))document.getElementById('clock').textContent=date.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'})}}catch(e){show(`Status: ${e.message||e}`,4)}}
function applyAppearance(a){const color=/^#[0-9a-f]{6}$/i;const start=color.test(a.background_start||'')?a.background_start:'#050706';const end=color.test(a.background_end||'')?a.background_end:'#070b09';document.documentElement.style.setProperty('--bg',start);document.documentElement.style.setProperty('--bg-end',end);document.documentElement.dataset.appearanceTheme=a.theme||'default'}
async function action(name){try{show(`${name}…`,2);const r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-Aurum-CSRF':csrf},body:JSON.stringify({action:name})});const d=await r.json();if(!r.ok)throw new Error(d.error||'action failed');show(JSON.stringify(d.result||d,null,2),5);await refresh()}catch(e){show(e.message||String(e),6)}}
async function ask(){const text=prompt.value.trim();if(!text||send.disabled)return;message('user',text);prompt.value='';send.disabled=true;orb.classList.add('thinking');document.body.classList.add('aurum-thinking');const pending=message('aurum','Aurum is reasoning with Hopper','thinking');try{const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json','X-Aurum-CSRF':csrf},body:JSON.stringify({prompt:text})});const d=await r.json();if(!r.ok)throw new Error(d.error||'GPT unavailable');pending.classList.remove('thinking');pending.textContent=d.response||'Completed';receipts(pending,d.tool_receipts);await refresh()}catch(e){pending.classList.remove('thinking');pending.classList.add('error');pending.textContent=e.message||String(e)}finally{orb.classList.remove('thinking');document.body.classList.remove('aurum-thinking');send.disabled=false;prompt.focus();messages.scrollTop=messages.scrollHeight}}

function showScreen(name){
  document.querySelectorAll('[data-nav]').forEach(x=>x.classList.toggle('active',x.dataset.nav===name));
  webBrowser.hidden=true;wifiPanel.hidden=true;gridPanel.hidden=false;
  const cards=[...gridPanel.querySelectorAll('.card')];cards.forEach(card=>card.hidden=false);
  if(name==='home')return;
  if(name==='browser'){gridPanel.hidden=true;openWebBrowser();return}
  if(name==='wifi'){gridPanel.hidden=true;wifiPanel.hidden=false;wifiScan();return}
  const groups={traits:['GPT Trait'],build:['Build'],hardware:['Hardware','Input & Recovery'],field:['System Runtime','Build'],settings:['System Tools','Input & Recovery','Network']};
  const wanted=groups[name]||[];
  cards.forEach(card=>{const h=card.querySelector('h2');card.hidden=!h||!wanted.includes(h.textContent.trim())});
}
async function wifiCall(actionName,extra={}){const r=await fetch('/api/wifi',{method:'POST',headers:{'Content-Type':'application/json','X-Aurum-CSRF':csrf},body:JSON.stringify({action:actionName,...extra})});const d=await r.json();if(!r.ok)throw new Error(d.error||'Wi-Fi action failed');return d.result||d}
function wifiDetail(result){const detail=document.getElementById('wifi-detail');if(!detail)return;const bits=[result.status,result.interface,result.ip].filter(Boolean);detail.textContent=bits.join(' · ')||'Wi-Fi state updated.'}
function renderWifiNetworks(result){const root=document.getElementById('wifi-networks');root.replaceChildren();const ssids=Array.isArray(result.ssids)?result.ssids:[];if(!ssids.length){const empty=document.createElement('span');empty.className='sub';empty.textContent=result.status==='ready'?'No nearby networks found.':(result.status||'Scan unavailable');root.appendChild(empty);return}ssids.forEach(ssid=>{const b=document.createElement('button');b.className='wifi-network';b.type='button';b.textContent=ssid;b.addEventListener('click',()=>{document.getElementById('wifi-ssid').value=ssid;document.getElementById('wifi-password').focus()});root.appendChild(b)})}
async function wifiScan(){try{wifiDetail({status:'Scanning…'});const result=await wifiCall('scan');wifiDetail(result);renderWifiNetworks(result)}catch(e){wifiDetail({status:e.message||String(e)})}}
async function wifiConnect(){const ssid=document.getElementById('wifi-ssid').value.trim(),password=document.getElementById('wifi-password');if(!ssid){show('Select or enter a Wi-Fi network.',4);return}try{wifiDetail({status:`Connecting to ${ssid}…`});const result=await wifiCall('connect',{ssid,password:password.value});password.value='';wifiDetail(result);await refresh()}catch(e){password.value='';wifiDetail({status:e.message||String(e)})}}
async function wifiDisconnect(){try{const result=await wifiCall('disconnect');wifiDetail(result);await refresh()}catch(e){wifiDetail({status:e.message||String(e)})}}
async function wifiForget(){if(!confirm('Forget the saved Wi-Fi network on this seed?'))return;try{const result=await wifiCall('forget');document.getElementById('wifi-ssid').value='';document.getElementById('wifi-password').value='';wifiDetail(result);await refresh()}catch(e){wifiDetail({status:e.message||String(e)})}}
document.getElementById('wifi-scan').addEventListener('click',wifiScan);document.getElementById('wifi-connect').addEventListener('click',wifiConnect);document.getElementById('wifi-disconnect').addEventListener('click',wifiDisconnect);document.getElementById('wifi-forget').addEventListener('click',wifiForget);
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',()=>action(b.dataset.action)));document.querySelectorAll('[data-nav]').forEach(b=>b.addEventListener('click',()=>showScreen(b.dataset.nav)));document.getElementById('focus-gpt').addEventListener('click',()=>prompt.focus());document.getElementById('clear-chat').addEventListener('click',()=>{messages.replaceChildren();message('aurum','Conversation cleared. Hopper state and action receipts remain governed by Aurum.');prompt.focus()});document.querySelectorAll('[data-prompt]').forEach(b=>b.addEventListener('click',()=>{prompt.value=b.dataset.prompt;ask()}));send.addEventListener('click',ask);prompt.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();ask()}});document.getElementById('search').addEventListener('keydown',e=>{if(e.key==='Enter'){const q=e.target.value.trim();if(q){prompt.value=`Show me ${q} on Hopper`;ask();e.target.value=''}}});document.getElementById('web-form').addEventListener('submit',e=>{e.preventDefault();webNavigate(webAddress.value)});document.getElementById('web-home-form').addEventListener('submit',e=>{e.preventDefault();const input=document.getElementById('web-home-query');if(webNavigate(input.value))input.value=''});document.getElementById('web-back').addEventListener('click',()=>{if(webIndex>0){webIndex-=1;webNavigate(webHistory[webIndex],{record:false})}});document.getElementById('web-forward').addEventListener('click',()=>{if(webIndex<webHistory.length-1){webIndex+=1;webNavigate(webHistory[webIndex],{record:false})}});document.getElementById('web-reload').addEventListener('click',()=>{if(currentWebTarget){webBrowser.classList.add('loading');webFrame.src=currentWebTarget}});document.getElementById('web-home-button').addEventListener('click',webBrowserHome);document.getElementById('web-close').addEventListener('click',closeWebBrowser);document.getElementById('web-open').addEventListener('click',()=>{let target=currentWebTarget;try{target=target||normalizeWebTarget(webAddress.value)}catch(error){show(error.message||String(error),5);return}const opened=window.open('about:blank','aurum-web');if(!opened){show('The full-page window was blocked. The page is still available inside Aurum.',5);return}opened.opener=null;opened.location.replace(target)});webFrame.addEventListener('load',()=>{if(webFrame.hidden||!currentWebTarget)return;webBrowser.classList.remove('loading');webStatus.innerHTML='<strong>Page loaded</strong> · isolated from Aurum controls'});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!webBrowser.hidden)closeWebBrowser()});updateWebButtons();
refresh();setInterval(refresh,4000);
</script>
</body></html>'''


def _make_handler(gui):
    class HopperHandler(gui.AurumGuiHandler):
        frame_source_policy = "https:"

        def _status_payload(self) -> dict[str, Any]:
            try:
                payload = super()._status_payload()
            except Exception:
                payload = {"schema": SCHEMA, "console": {"identity": "Hopper"}}
            trait = _load_runtime_module("aurum_gpt_trait.py", "aurum_gpt_trait")
            try:
                candidate = trait.status() if trait else None
                safe_candidate = _json_safe_dict(candidate)
                gpt = safe_candidate or {"status": "unavailable", "detail": "invalid-trait-status"}
            except Exception as exc:
                gpt = {"status": "unavailable", "detail": f"{type(exc).__name__}:{exc}"}
            payload["schema"] = SCHEMA
            payload["hopper"] = {
                "telemetry": _telemetry(),
                "gpt": gpt,
                "appearance": _appearance(),
                "projection": {
                    "renderer": "html5",
                    "fallback": "pygame",
                    "primary": True,
                    "web_browser": {
                        "renderer": "html5-sandboxed-frame",
                        "navigation": "https-only",
                        "private_network": "blocked-in-surface",
                        "web_proxy": False,
                        "raw_shell": False,
                    },
                    "identity_mark": {
                        "scope": "aurum-native-seven-leaf",
                        "renderer": "html5-landscape-crop",
                        "source_sha256": LOGO_SHA256,
                        "source_verified": _verified_logo_bytes() is not None,
                    },
                },
            }
            payload["authority"] = {
                "dialogue_only": False,
                "host_actuation": "bounded",
                "raw_shell": False,
                "git_push": False,
                "api_key_persisted": False,
                "browser_credential": False,
                "credential_source": gpt.get("credential_source"),
            }
            return payload

        def do_GET(self) -> None:  # noqa: N802
            request_path = urlsplit(self.path).path
            if request_path != "/assets/aurum-seven-leaf-logo.jpeg":
                super().do_GET()
                return
            if not self._host_is_loopback():
                self._error(HTTPStatus.FORBIDDEN, "loopback host required")
                return
            payload = _verified_logo_bytes()
            if payload is None:
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "verified Aurum mark unavailable")
                return
            self.send_response(HTTPStatus.OK)
            self._security_headers()
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Aurum-Asset-SHA256", LOGO_SHA256)
            self.end_headers()
            self.wfile.write(payload)

        def _read_payload(self) -> dict[str, Any] | None:
            if not self._host_is_loopback() or not self._origin_is_loopback():
                self._error(HTTPStatus.FORBIDDEN, "loopback origin required")
                return None
            if not gui.secrets.compare_digest(self.headers.get("X-Aurum-CSRF", ""), self.server.csrf_token):
                self._error(HTTPStatus.FORBIDDEN, "request proof invalid")
                return None
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "application/json required")
                return None
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if not 1 <= length <= gui.MAX_REQUEST_BYTES:
                self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request size invalid")
                return None
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._error(HTTPStatus.BAD_REQUEST, "invalid JSON")
                return None
            if not isinstance(value, dict):
                self._error(HTTPStatus.BAD_REQUEST, "request object required")
                return None
            return value

        def do_POST(self) -> None:  # noqa: N802
            request_path = urlsplit(self.path).path
            if request_path == "/api/key-bootstrap":
                self._error(HTTPStatus.GONE, "Hopper uses a machine-sealed runtime credential")
                return
            if request_path not in {"/api/ask", "/api/action", "/api/wifi"}:
                super().do_POST()
                return
            payload = self._read_payload()
            if payload is None:
                return
            if request_path == "/api/wifi":
                action_name = str(payload.get("action") or "").strip().lower()
                allowed = {
                    "scan": {"action"},
                    "connect": {"action", "ssid", "password"},
                    "disconnect": {"action"},
                    "forget": {"action"},
                }
                if action_name not in allowed or not set(payload).issubset(allowed[action_name]):
                    self._error(HTTPStatus.BAD_REQUEST, "Wi-Fi action fields invalid")
                    return
                network = _load_runtime_module("aurum_network.py", "aurum_network_gui")
                if network is None:
                    self._error(HTTPStatus.SERVICE_UNAVAILABLE, "Aurum network module unavailable")
                    return
                try:
                    if action_name == "scan":
                        result = network.scan_networks()
                    elif action_name == "connect":
                        ssid = payload.get("ssid")
                        password = payload.get("password", "")
                        if not isinstance(ssid, str) or not ssid.strip():
                            raise ValueError("Wi-Fi SSID is required")
                        if not isinstance(password, str) or len(password) > 128:
                            raise ValueError("Wi-Fi password is invalid")
                        config = network._make_config(ssid.strip(), password)
                        password = ""
                        network._write_saved_config(config)
                        result = network.connect_saved()
                    else:
                        interfaces = network.wireless_interfaces()
                        selected = interfaces[0] if interfaces else None
                        if selected:
                            network._stop_owned_supplicant(selected)
                        if action_name == "forget":
                            network.SAVED_WIFI.unlink(missing_ok=True)
                        result = {"status": "saved-network-forgotten" if action_name == "forget" else "disconnected", **network.network_status(selected)}
                    if _json_safe_dict(result) is None:
                        raise TypeError("Wi-Fi result was not JSON-safe")
                except Exception as exc:
                    self._error(HTTPStatus.BAD_REQUEST, f"bounded Wi-Fi action failed: {type(exc).__name__}:{exc}")
                    return
                self._json(HTTPStatus.OK, {"schema": SCHEMA, "status": "completed", "result": result})
                return

            if request_path == "/api/action":
                if set(payload) != {"action"}:
                    self._error(HTTPStatus.BAD_REQUEST, "action fields invalid")
                    return
                executor = _load_runtime_module("aurum_gpt_executor.py", "aurum_gpt_executor")
                if executor is None:
                    self._error(HTTPStatus.SERVICE_UNAVAILABLE, "Aurum executor unavailable")
                    return
                try:
                    result = executor.execute_control(str(payload.get("action") or ""))
                    if _json_safe_dict(result) is None:
                        raise TypeError("Aurum executor result was not a JSON-safe object")
                except Exception as exc:
                    self._error(HTTPStatus.BAD_REQUEST, f"bounded action failed: {type(exc).__name__}:{exc}")
                    return
                self._json(HTTPStatus.OK, {"schema": SCHEMA, "status": "completed", "result": result})
                return

            if not set(payload).issubset({"prompt", "model"}):
                self._error(HTTPStatus.BAD_REQUEST, "GPT fields invalid")
                return
            prompt = payload.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                self._error(HTTPStatus.BAD_REQUEST, "prompt is empty")
                return
            trait = _load_runtime_module("aurum_gpt_trait.py", "aurum_gpt_trait")
            if trait is None:
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "GPT trait unavailable")
                return
            model = payload.get("model")
            kwargs: dict[str, Any] = {}
            if isinstance(model, str) and model.strip():
                kwargs["model"] = model.strip()

            lock = getattr(self.server, "hopper_gpt_lock", None)
            if lock is None:
                lock = threading.Lock()
                self.server.hopper_gpt_lock = lock
            with lock:
                try:
                    result = trait.ask(prompt.strip(), **kwargs)
                    if not isinstance(result, dict):
                        raise TypeError("GPT trait result was not an object")
                    response = result.get("text")
                    if not isinstance(response, str) or not response.strip():
                        raise ValueError("GPT trait result did not contain response text")
                    tool_receipts = result.get("tool_receipts") or []
                    if not isinstance(tool_receipts, list):
                        raise TypeError("GPT trait receipts were not a list")
                    if _json_safe_dict(result) is None:
                        raise TypeError("GPT trait result was not JSON-safe")
                except Exception as exc:
                    self._error(HTTPStatus.BAD_GATEWAY, f"GPT unavailable: {type(exc).__name__}:{exc}")
                    return
            self._json(
                HTTPStatus.OK,
                {
                    "schema": SCHEMA,
                    "status": result.get("status"),
                    "response": response,
                    "tool_receipts": tool_receipts,
                    "host_actuation": result.get("host_actuation"),
                    "raw_shell": False,
                    "api_key_persisted": False,
                    "browser_credential": False,
                },
            )

    return HopperHandler


def main() -> int:
    gui = _load_gui()
    gui.PAGE = PAGE
    gui.GUI_SCHEMA = SCHEMA
    gui.AurumGuiHandler = _make_handler(gui)
    server_main = gui.main
    return int(server_main())


if __name__ == "__main__":
    raise SystemExit(main())
