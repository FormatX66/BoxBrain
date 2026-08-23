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
SCHEMA = "aurum.hopper-projection.gen1-html"
LOGO_PATH = (
    DEFAULT_WORKSPACE
    / "Projects"
    / "Codelation"
    / "assets"
    / "identity"
    / "bruce-aurum-personal-logo-selected.png"
)
LOGO_SHA256 = "cc6f724146cee4df50146cf9ab4d78e3ccdc6b2a62b3c72116ded90bb24b304d"


def _verified_logo_bytes(path: Path = LOGO_PATH) -> bytes | None:
    """Return the selected identity mark only when its geometry authority matches."""
    try:
        payload = path.read_bytes()
    except OSError:
        return None
    if hashlib.sha256(payload).hexdigest() != LOGO_SHA256:
        return None
    return payload


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
    seed_text = str(SEED_DIR)
    if seed_text not in sys.path:
        sys.path.insert(0, seed_text)
    module = _load_path(GUI_PATH, "aurum_hopper_gui_base")
    if module is None:
        raise RuntimeError(f"Aurum GUI source unavailable: {GUI_PATH}")
    return module


def _load_runtime_module(filename: str, prefix: str):
    for path in (
        DEFAULT_RUNTIME / filename,
        DEFAULT_WORKSPACE / "Projects" / "AurumPC" / filename,
    ):
        module = _load_path(path, prefix)
        if module is not None:
            return module
    return None


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
    state = executor.status_snapshot() if executor and hasattr(executor, "status_snapshot") else {}

    network_module = _load_runtime_module("aurum_network.py", "aurum_network")
    try:
        network = network_module.network_status() if network_module else {}
    except Exception:
        network = {}

    time_module = _load_runtime_module("aurum_time.py", "aurum_time")
    try:
        clock = time_module.time_status() if time_module else {}
    except Exception:
        clock = {}

    return {
        "state": state,
        "network": network if isinstance(network, dict) else {},
        "time": clock if isinstance(clock, dict) else {},
        "battery": _battery(),
        "memory_percent": _memory_percent(),
        "storage_percent": _storage_percent(),
        "uptime_seconds": _uptime(),
        "renderer": "html5",
        "projection": "primary-human-surface",
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
:root{--bg:#050706;--panel:#0b100f;--panel2:#0f1514;--gold:#d3a640;--gold2:#f1ca65;--gold3:#70551f;--teal:#13c6ca;--teal2:#78ece7;--ink:#f2eee2;--muted:#8c948f;--line:rgba(211,166,64,.28);--line2:rgba(19,198,202,.25);--bad:#ef7777;--good:#69d6ae}
*{box-sizing:border-box}html,body{height:100%;margin:0}body{background:radial-gradient(circle at 50% -20%,rgba(19,198,202,.06),transparent 38rem),linear-gradient(180deg,#050706,#070b09);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;overflow:hidden}button,input,textarea{font:inherit}.shell{height:100vh;display:grid;grid-template-columns:174px 1fr;grid-template-rows:68px 1fr 74px}.top{grid-column:1/3;border-bottom:1px solid var(--line);display:flex;align-items:center;padding:0 24px;gap:28px;background:rgba(4,7,6,.96)}.brand{display:flex;align-items:center;gap:12px;min-width:210px}.sigil{width:38px;height:38px;border:1px solid var(--gold);display:grid;place-items:center;transform:rotate(45deg);box-shadow:0 0 22px rgba(211,166,64,.16)}.sigil b{transform:rotate(-45deg);font-size:19px;color:var(--gold2)}.brand-name{letter-spacing:.29em;color:var(--gold2);font-weight:720}.search{flex:1;max-width:560px;position:relative}.search input{width:100%;border:1px solid rgba(255,255,255,.09);background:#0a0e0d;color:var(--ink);border-radius:9px;padding:11px 15px;outline:none}.search input:focus{border-color:var(--gold)}.statusbar{margin-left:auto;display:flex;align-items:center;gap:18px;font-size:12px}.mini{display:flex;align-items:center;gap:8px;color:var(--muted)}.mini strong{color:var(--ink);font-weight:600}.online-dot{width:7px;height:7px;border-radius:50%;background:var(--good);box-shadow:0 0 12px var(--good)}.wifi{width:28px;height:18px;position:relative}.wifi i{position:absolute;left:50%;bottom:0;transform:translateX(-50%);border:1.8px solid var(--teal);border-radius:50%;opacity:.28}.wifi i:nth-child(1){width:6px;height:3px;opacity:1}.wifi i:nth-child(2){width:16px;height:8px;opacity:.75}.wifi i:nth-child(3){width:27px;height:14px;opacity:.48}.rail{grid-row:2/4;border-right:1px solid var(--line);padding:18px 12px;background:#070a08;display:flex;flex-direction:column;gap:7px}.nav{height:43px;border:1px solid transparent;border-radius:7px;background:transparent;color:#9fa59f;text-align:left;padding:0 13px;cursor:pointer;display:flex;align-items:center;gap:11px}.nav span:first-child{width:19px;color:var(--gold)}.nav:hover,.nav.active{color:var(--gold2);border-color:var(--line);background:linear-gradient(90deg,rgba(211,166,64,.12),transparent)}.rail-foot{margin-top:auto;border-top:1px solid var(--line);padding-top:14px;font-size:10px;line-height:1.5;color:#66706a}.main{grid-column:2;grid-row:2;overflow:auto;padding:24px 28px 30px}.hero{height:150px;border-bottom:1px solid var(--line);position:relative;overflow:hidden;margin-bottom:20px}.hero h1{font-weight:420;font-size:32px;margin:6px 0;color:var(--gold2)}.hero p{margin:0;color:var(--muted);font-size:13px}.canopy{position:absolute;right:0;top:0;width:58%;height:145px;opacity:.86}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.card{min-height:174px;border:1px solid var(--line);background:linear-gradient(145deg,rgba(13,19,17,.94),rgba(6,9,8,.96));border-radius:7px;padding:15px;position:relative;overflow:hidden;transition:.16s ease}.card:hover{border-color:rgba(241,202,101,.55);transform:translateY(-1px)}.card h2{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--gold2);margin:0 0 10px}.state{display:flex;align-items:center;gap:7px;color:var(--good);font-size:11px;margin-bottom:18px}.metric{display:flex;align-items:center;justify-content:space-between;margin:9px 0;font-size:12px}.metric span:first-child{color:var(--muted)}.metric b{font-weight:600}.bar{height:4px;border-radius:9px;background:#202823;overflow:hidden;margin-top:5px}.bar>i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--gold),var(--teal));transition:width .4s ease}.big{font-size:35px;color:var(--gold2);font-weight:320;line-height:1}.sub{font-size:10px;color:var(--muted);margin-top:7px}.action{position:absolute;left:12px;right:12px;bottom:11px;border:1px solid rgba(211,166,64,.2);background:#0b0e0c;color:#d7d0bc;border-radius:5px;padding:7px 9px;cursor:pointer;font-size:10px;text-align:left}.action:hover{border-color:var(--teal);color:var(--teal2)}.dock{grid-column:2;grid-row:3;border-top:1px solid var(--line);background:rgba(5,8,6,.98);padding:10px 28px;display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center}.prompt-wrap{display:flex;gap:9px}.prompt-wrap textarea{height:48px;resize:none;flex:1;border:1px solid rgba(255,255,255,.10);border-radius:7px;background:#0a0e0c;color:var(--ink);padding:12px;outline:none}.prompt-wrap textarea:focus{border-color:var(--gold)}.key{width:160px;border:1px solid rgba(255,255,255,.09);border-radius:7px;background:#0a0e0c;color:var(--ink);padding:0 10px;outline:none}.send{height:48px;border:1px solid var(--gold);background:rgba(211,166,64,.10);color:var(--gold2);border-radius:7px;padding:0 20px;cursor:pointer}.send:hover{background:rgba(211,166,64,.18)}.toast{position:fixed;right:24px;bottom:92px;max-width:560px;border:1px solid var(--line);background:#0b100e;padding:14px 16px;border-radius:8px;box-shadow:0 18px 60px #0008;font-size:12px;line-height:1.5;white-space:pre-wrap;display:none;z-index:20}.toast.show{display:block}.teal{color:var(--teal2)}.unknown{color:#817864}@media(max-width:1150px){.grid{grid-template-columns:repeat(2,1fr)}.statusbar .hide-mid{display:none}}@media(max-width:720px){body{overflow:auto}.shell{display:block}.top{position:sticky;top:0;z-index:10}.rail{display:none}.main{padding:18px}.grid{grid-template-columns:1fr}.dock{position:sticky;bottom:0;grid-template-columns:1fr}.key{display:none}.canopy{opacity:.35;width:100%}}
.main{display:grid;grid-template-columns:minmax(0,1fr) 390px;grid-template-rows:150px minmax(0,1fr);gap:20px;overflow:hidden}.hero{grid-column:1/3;margin:0}.grid{grid-column:1;grid-row:2;grid-template-columns:repeat(2,minmax(0,1fr));overflow:auto;padding-right:5px;align-content:start}.dock{grid-template-columns:minmax(0,1fr) auto}.prompt-wrap{align-items:center;min-width:0}.key{display:none}.gpt-chip{height:32px;display:flex;align-items:center;gap:8px;border:1px solid var(--line2);border-radius:999px;padding:0 11px;color:var(--teal2);font-size:10px;letter-spacing:.08em;text-transform:uppercase;white-space:nowrap;background:rgba(19,198,202,.06)}.gpt-chip i{width:6px;height:6px;border-radius:50%;background:var(--teal);box-shadow:0 0 11px var(--teal)}.send{background:linear-gradient(135deg,rgba(211,166,64,.18),rgba(19,198,202,.08));transition:.18s ease}.send:hover{background:linear-gradient(135deg,rgba(211,166,64,.28),rgba(19,198,202,.14));box-shadow:0 0 26px rgba(211,166,64,.12)}.send:disabled{opacity:.45;cursor:wait}.chat-panel{grid-column:2;grid-row:2;min-height:0;border:1px solid var(--line);border-radius:9px;background:radial-gradient(circle at 90% 0,rgba(19,198,202,.09),transparent 45%),linear-gradient(160deg,rgba(13,19,17,.98),rgba(5,8,7,.98));display:grid;grid-template-rows:auto 1fr auto;overflow:hidden;box-shadow:0 22px 70px #0006}.chat-head{padding:14px 15px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:10px}.mind-orb{width:30px;height:30px;position:relative;display:grid;place-items:center;border:1px solid var(--gold);transform:rotate(45deg);background:rgba(211,166,64,.06);box-shadow:0 0 18px rgba(211,166,64,.12)}.mind-orb::after{content:'A';transform:rotate(-45deg);color:var(--gold2);font-size:12px;font-weight:750}.mind-orb.thinking{animation:pulse 1.1s ease-in-out infinite}.chat-title{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--gold2)}.chat-sub{font-size:9px;color:var(--muted);margin-top:3px}.clear-chat{margin-left:auto;border:0;background:transparent;color:var(--muted);font-size:10px;cursor:pointer}.clear-chat:hover{color:var(--teal2)}.messages{min-height:0;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:13px}.message{max-width:88%;border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:10px 12px;font-size:12px;line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere;animation:arrive .2s ease-out}.message.aurum{align-self:flex-start;background:rgba(211,166,64,.07);border-color:var(--line)}.message.user{align-self:flex-end;background:rgba(19,198,202,.08);border-color:var(--line2)}.message.error{border-color:rgba(239,119,119,.45);color:#ffc1c1}.message.thinking{color:var(--muted)}.message.thinking::after{content:' ···';color:var(--teal2);animation:blink 1s steps(2,end) infinite}.receipt-stack{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.receipt{border:1px solid var(--line2);border-radius:999px;padding:4px 7px;color:var(--teal2);font-size:9px;background:rgba(19,198,202,.05)}.suggestions{padding:0 14px 14px;display:flex;flex-wrap:wrap;gap:6px}.suggestion{border:1px solid rgba(255,255,255,.08);border-radius:999px;background:#0a0e0c;color:var(--muted);font-size:9px;padding:6px 9px;cursor:pointer}.suggestion:hover{color:var(--gold2);border-color:var(--line)}@keyframes arrive{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}@keyframes pulse{50%{box-shadow:0 0 28px rgba(19,198,202,.5);border-color:var(--teal)}}@keyframes blink{50%{opacity:.2}}@media(max-width:1150px){.main{grid-template-columns:minmax(0,1fr) 340px}.grid{grid-template-columns:1fr}}@media(max-width:860px){.main{padding:18px;display:block;overflow:auto}.hero{margin-bottom:18px}.grid{grid-template-columns:1fr;overflow:visible}.chat-panel{position:fixed;inset:82px 14px 86px 14px;z-index:15}.gpt-chip{display:none}}
body::before{content:"";position:fixed;inset:0;pointer-events:none;background-image:linear-gradient(rgba(211,166,64,.018) 1px,transparent 1px),linear-gradient(90deg,rgba(19,198,202,.014) 1px,transparent 1px);background-size:42px 42px;mask-image:linear-gradient(to bottom,black,transparent 82%)}body::after{content:"";position:fixed;inset:0;pointer-events:none;opacity:.22;background:radial-gradient(circle at 82% 18%,rgba(19,198,202,.13),transparent 24rem),radial-gradient(circle at 14% 86%,rgba(211,166,64,.08),transparent 30rem)}.top,.rail,.dock,.main{position:relative;z-index:1}.top{background:linear-gradient(90deg,rgba(4,7,6,.985),rgba(6,10,9,.965));box-shadow:0 10px 40px #0007}.brand{min-width:224px}.brand-copy{display:flex;flex-direction:column;gap:2px}.brand-sub{font-size:8px;letter-spacing:.16em;text-transform:uppercase;color:var(--teal2);opacity:.72}.logo-life{position:relative;isolation:isolate;display:grid;place-items:center;flex:0 0 auto}.logo-life canvas{display:block;width:100%;height:100%;object-fit:contain;filter:drop-shadow(0 0 7px rgba(211,166,64,.24));position:relative;z-index:3}.logo-life::before,.logo-life::after{content:"";position:absolute;border-radius:50%;pointer-events:none}.logo-life::before{inset:6%;border:1px solid rgba(211,166,64,.30);box-shadow:inset 0 0 20px rgba(19,198,202,.05),0 0 20px rgba(211,166,64,.06);animation:logo-breathe 5s ease-in-out infinite}.logo-life::after{width:6px;height:6px;top:5%;left:50%;background:var(--teal);box-shadow:0 0 12px var(--teal);transform-origin:0 calc(var(--orbit-radius,26px));animation:logo-orbit 7s linear infinite}.logo-life--mini{width:46px;height:46px;--orbit-radius:19px}.logo-life--mini canvas{width:38px;height:38px}.hero{height:auto;min-height:150px;border:1px solid rgba(211,166,64,.16);border-radius:11px;padding:22px 25px;background:linear-gradient(112deg,rgba(12,18,16,.94) 0%,rgba(8,13,12,.86) 58%,rgba(8,16,15,.72) 100%);box-shadow:inset 0 1px rgba(255,255,255,.025),0 18px 55px #0005}.hero::before{content:"";position:absolute;inset:0;background:linear-gradient(90deg,transparent 0 56%,rgba(19,198,202,.035)),repeating-linear-gradient(135deg,transparent 0 22px,rgba(211,166,64,.012) 23px 24px);pointer-events:none}.hero-copy{position:relative;z-index:4;width:62%}.hero-kicker{display:flex;align-items:center;gap:8px;font-size:10px;letter-spacing:.18em}.hero-kicker::before{content:"";width:24px;height:1px;background:var(--teal);box-shadow:0 0 9px var(--teal)}.hero h1{font-size:31px;margin:10px 0 7px;letter-spacing:-.02em}.hero-status{display:flex;gap:8px;margin-top:16px;flex-wrap:wrap}.hero-status span{border:1px solid rgba(255,255,255,.08);border-radius:999px;padding:5px 9px;font-size:8px;letter-spacing:.12em;text-transform:uppercase;color:#aeb8b1;background:#080c0b99}.hero-status span:first-child{border-color:var(--line2);color:var(--teal2)}.hero-life{position:absolute;right:3.5%;top:50%;width:34%;height:138%;transform:translateY(-50%);display:grid;place-items:center}.logo-life--hero{width:152px;height:152px;--orbit-radius:68px}.logo-life--hero canvas{width:126px;height:126px;animation:logo-float 5.8s ease-in-out infinite}.logo-life--hero::before{inset:3%;border-color:rgba(211,166,64,.25);box-shadow:inset 0 0 42px rgba(19,198,202,.07),0 0 35px rgba(211,166,64,.08)}.orbit-ring{position:absolute;border:1px solid rgba(19,198,202,.16);border-radius:50%;pointer-events:none}.orbit-ring.one{inset:-9%;transform:rotate(14deg) scaleY(.72);animation:ring-turn 15s linear infinite}.orbit-ring.two{inset:-24%;border-color:rgba(211,166,64,.11);transform:rotate(-19deg) scaleY(.62);animation:ring-turn-reverse 22s linear infinite}.life-circuit{position:absolute;inset:0;width:100%;height:100%;opacity:.62;overflow:visible}.life-circuit path{fill:none;stroke:rgba(19,198,202,.50);stroke-width:1;stroke-dasharray:5 7;animation:circuit-flow 6s linear infinite}.life-circuit circle{fill:var(--gold2);filter:drop-shadow(0 0 4px var(--gold))}.card{border-color:rgba(211,166,64,.20);border-radius:10px;box-shadow:inset 0 1px rgba(255,255,255,.02),0 14px 32px #0003}.card::before{content:"";position:absolute;inset:0 auto auto 0;width:48%;height:1px;background:linear-gradient(90deg,var(--gold),transparent);opacity:.48}.card::after{content:"";position:absolute;width:90px;height:90px;right:-42px;top:-42px;border:1px solid rgba(19,198,202,.09);border-radius:50%;box-shadow:0 0 40px rgba(19,198,202,.025)}.card:nth-child(3n+2)::before{background:linear-gradient(90deg,var(--teal),transparent)}.card:hover{box-shadow:inset 0 1px rgba(255,255,255,.035),0 18px 38px #0006,0 0 26px rgba(211,166,64,.035)}.chat-panel{border-radius:12px;border-color:rgba(211,166,64,.24);box-shadow:inset 0 1px rgba(255,255,255,.025),0 24px 70px #0008}.chat-head{background:linear-gradient(90deg,rgba(211,166,64,.055),rgba(19,198,202,.035))}.mind-orb{width:40px;height:40px;transform:none;border:0;background:transparent;box-shadow:none;--orbit-radius:16px}.mind-orb::after{width:5px;height:5px;content:"";transform-origin:0 var(--orbit-radius);color:transparent;font-size:0}.mind-orb::before{inset:5%}.mind-orb canvas{width:34px;height:34px}.mind-orb.thinking{animation:none}.mind-orb.thinking::before,.aurum-thinking .logo-life::before{border-color:var(--teal);box-shadow:inset 0 0 24px rgba(19,198,202,.14),0 0 30px rgba(19,198,202,.28);animation:thinking-breathe .75s ease-in-out infinite}.mind-orb.thinking::after,.aurum-thinking .logo-life--hero::after{animation-duration:1.1s}.message{backdrop-filter:blur(7px)}.dock{box-shadow:0 -16px 42px #0005}.send{min-width:132px;font-weight:650;letter-spacing:.04em}@keyframes logo-breathe{0%,100%{opacity:.46;transform:scale(.98)}50%{opacity:.92;transform:scale(1.025)}}@keyframes logo-orbit{to{transform:rotate(360deg)}}@keyframes logo-float{0%,100%{transform:translateY(2px)}50%{transform:translateY(-4px)}}@keyframes ring-turn{to{transform:rotate(374deg) scaleY(.72)}}@keyframes ring-turn-reverse{to{transform:rotate(-379deg) scaleY(.62)}}@keyframes circuit-flow{to{stroke-dashoffset:-48}}@keyframes thinking-breathe{50%{opacity:1;transform:scale(1.07)}}@media(max-width:860px){.hero-copy{width:74%}.hero-life{right:-4%;opacity:.68}.logo-life--hero{width:126px;height:126px}.brand-sub{display:none}}@media(max-width:560px){.hero-copy{width:100%}.hero-life{opacity:.22;right:-18%}.search{display:none}.brand{min-width:0}.hero h1{font-size:27px}}@media(prefers-reduced-motion:reduce){.logo-life::before,.logo-life::after,.logo-life canvas,.orbit-ring,.life-circuit path,.mind-orb.thinking::before{animation:none!important}.card,.send{transition:none!important}}
</style>
</head>
<body>
<div class="shell">
<header class="top">
  <div class="brand"><div class="logo-life logo-life--mini" aria-hidden="true"><canvas data-aurum-mark></canvas></div><div class="brand-copy"><div class="brand-name">AURUM</div><div class="brand-sub">Hopper · living seed</div></div></div>
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
    <div class="hero-life" aria-hidden="true"><svg class="life-circuit" viewBox="0 0 420 210"><path d="M0 55h78l28 25h67M14 164h94l24-21h73M252 34h70l23 25h75M274 174h53l27-24h66"/><circle cx="106" cy="80" r="3"/><circle cx="132" cy="143" r="3"/><circle cx="345" cy="59" r="3"/><circle cx="354" cy="150" r="3"/></svg><div class="logo-life logo-life--hero"><span class="orbit-ring one"></span><span class="orbit-ring two"></span><canvas data-aurum-mark></canvas></div></div>
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
    <div class="chat-head"><div id="mind-orb" class="mind-orb logo-life" aria-hidden="true"><canvas data-aurum-mark></canvas></div><div><div class="chat-title">Aurum GPT</div><div class="chat-sub">Bounded tools · receipts visible · raw shell off</div></div><button id="clear-chat" class="clear-chat">Clear</button></div>
    <div id="messages" class="messages" aria-live="polite"><div class="message aurum">I’m connected to Hopper’s live Aurum state. Ask me to inspect the machine, explain what it sees, or use a bounded action. Any local action returns a receipt here.</div></div>
    <div class="suggestions"><button class="suggestion" data-prompt="Give me a plain-language Hopper health check.">Health check</button><button class="suggestion" data-prompt="Show what Aurum can safely control on Hopper.">What can you do?</button><button class="suggestion" data-prompt="Inspect the current seed state and tell me what should grow next.">What grows next?</button></div>
  </aside>
</main>
<footer class="dock">
  <div class="prompt-wrap"><div id="gpt-chip" class="gpt-chip"><i></i><span>Connecting GPT</span></div><textarea id="prompt" maxlength="12000" placeholder="Ask Aurum about Hopper…" aria-label="Ask Aurum GPT"></textarea></div>
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
let preparedMark=null;
function paintLivingMarks(source){document.querySelectorAll('[data-aurum-mark]').forEach(canvas=>{const box=canvas.getBoundingClientRect(),dpr=Math.min(window.devicePixelRatio||1,2),w=Math.max(1,Math.round(box.width*dpr)),h=Math.max(1,Math.round(box.height*dpr));canvas.width=w;canvas.height=h;const ctx=canvas.getContext('2d'),scale=Math.min(w/source.width,h/source.height),dw=source.width*scale,dh=source.height*scale;ctx.clearRect(0,0,w,h);ctx.drawImage(source,(w-dw)/2,(h-dh)/2,dw,dh);canvas.dataset.markReady='true'})}
async function renderLivingMarks(){try{const image=new Image();image.decoding='async';image.src='/assets/aurum-mark.png';await image.decode();const stage=document.createElement('canvas');stage.width=image.naturalWidth;stage.height=image.naturalHeight;const ctx=stage.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0);const frame=ctx.getImageData(0,0,stage.width,stage.height),pixels=frame.data,total=stage.width*stage.height,seen=new Uint8Array(total),queue=new Int32Array(total);let head=0,tail=0;const eligible=index=>{const at=index*4,r=pixels[at],g=pixels[at+1],b=pixels[at+2],bright=(r+g+b)/3,chroma=Math.max(r,g,b)-Math.min(r,g,b);return pixels[at+3]>0&&bright>=184&&chroma<=16};const seed=index=>{if(!seen[index]&&eligible(index)){seen[index]=1;queue[tail++]=index}};for(let x=0;x<stage.width;x++){seed(x);seed((stage.height-1)*stage.width+x)}for(let y=1;y<stage.height-1;y++){seed(y*stage.width);seed(y*stage.width+stage.width-1)}while(head<tail){const index=queue[head++],x=index%stage.width,y=Math.floor(index/stage.width);pixels[index*4+3]=0;if(x>0)seed(index-1);if(x+1<stage.width)seed(index+1);if(y>0)seed(index-stage.width);if(y+1<stage.height)seed(index+stage.width)}ctx.putImageData(frame,0,0);preparedMark=stage;paintLivingMarks(stage);document.body.classList.add('aurum-mark-ready')}catch(error){document.body.classList.add('aurum-mark-unavailable')}}
function show(message,seconds=6){toast.textContent=message;toast.classList.add('show');clearTimeout(show.t);show.t=setTimeout(()=>toast.classList.remove('show'),seconds*1000)}
function message(kind,text,extra=''){const node=document.createElement('div');node.className=`message ${kind} ${extra}`.trim();node.textContent=text;messages.appendChild(node);messages.scrollTop=messages.scrollHeight;return node}
function receipts(node,items){if(!Array.isArray(items)||!items.length)return;const stack=document.createElement('div');stack.className='receipt-stack';items.forEach((item,index)=>{const chip=document.createElement('span');chip.className='receipt';const action=item.action||item.tool||item.operation||`tool ${index+1}`;chip.textContent=`${action} · ${item.status||'receipted'}`;stack.appendChild(chip)});node.appendChild(stack)}
function pct(id,value){const node=document.getElementById(id);if(node)node.textContent=value==null?'—':`${value}%`;const bar=document.getElementById(`${id}-bar`);if(bar)bar.style.width=value==null?'0%':`${Math.max(0,Math.min(100,value))}%`}
function humanDuration(seconds){if(seconds==null)return'—';const h=Math.floor(seconds/3600),m=Math.floor((seconds%3600)/60);return `${h}h ${m}m`}
function first(obj,keys){for(const k of keys){if(obj&&obj[k]!=null&&obj[k]!=='' )return obj[k]}return null}
async function refresh(){try{const r=await fetch('/api/status',{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||'status unavailable');const h=d.hopper||{},t=h.telemetry||{},s=t.state||{},n=t.network||{},b=t.battery||{},tm=t.time||{},g=h.gpt||{};document.getElementById('machine').textContent=s.machine||'Hopper';document.getElementById('runtime-state').textContent=s.runtime||'Unknown';document.getElementById('desktop').textContent=s.desktop_generation||s.desktop||'Unknown';document.getElementById('autonomy').textContent=s.autonomy||'Unknown';document.getElementById('input-state').textContent=s.input||'Unknown';document.getElementById('uptime').textContent=humanDuration(t.uptime_seconds);pct('memory',t.memory_percent);pct('storage',t.storage_percent);const connected=first(n,['online','connected','status']);document.getElementById('net-state').textContent=connected===true?'Connected':(connected||'Unknown');const ssid=first(n,['ssid','connection','network']);document.getElementById('ssid').textContent=ssid||'Unknown';document.getElementById('wifi').textContent=ssid||'Network';document.getElementById('net-if').textContent=first(n,['interface','device'])||'Unknown';document.getElementById('net-ip').textContent=first(n,['ip','address','ipv4'])||'Unknown';document.getElementById('battery').textContent=b.percent==null?'—':`${b.percent}%`;document.getElementById('battery-big').textContent=b.percent==null?'—':`${b.percent}%`;document.getElementById('battery-sub').textContent=b.status||'Unknown';document.getElementById('power-state').textContent=b.charging?'Charging':(b.status||'Unknown');document.getElementById('gpt-state').textContent=g.status==='ready'?'Ready':(g.status||'Unknown');document.getElementById('gpt-tools').textContent=g.function_tools?'Ready':'Unavailable';gptChip.textContent=g.status==='ready'?'GPT ready on Hopper':'Sealed credential pending';document.getElementById('time-state').textContent=tm.synchronized?'Server synchronized':'Local / unknown';if(tm.local_iso){const date=new Date(tm.local_iso);if(!Number.isNaN(date.valueOf()))document.getElementById('clock').textContent=date.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'})}}catch(e){show(`Status: ${e.message||e}`,4)}}
async function action(name){try{show(`${name}…`,2);const r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-Aurum-CSRF':csrf},body:JSON.stringify({action:name})});const d=await r.json();if(!r.ok)throw new Error(d.error||'action failed');show(JSON.stringify(d.result||d,null,2),5);await refresh()}catch(e){show(e.message||String(e),6)}}
async function ask(){const text=prompt.value.trim();if(!text||send.disabled)return;message('user',text);prompt.value='';send.disabled=true;orb.classList.add('thinking');document.body.classList.add('aurum-thinking');const pending=message('aurum','Aurum is reasoning with Hopper','thinking');try{const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json','X-Aurum-CSRF':csrf},body:JSON.stringify({prompt:text})});const d=await r.json();if(!r.ok)throw new Error(d.error||'GPT unavailable');pending.classList.remove('thinking');pending.textContent=d.response||'Completed';receipts(pending,d.tool_receipts);await refresh()}catch(e){pending.classList.remove('thinking');pending.classList.add('error');pending.textContent=e.message||String(e)}finally{orb.classList.remove('thinking');document.body.classList.remove('aurum-thinking');send.disabled=false;prompt.focus();messages.scrollTop=messages.scrollHeight}}
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',()=>action(b.dataset.action)));document.querySelectorAll('[data-nav]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-nav]').forEach(x=>x.classList.remove('active'));b.classList.add('active');show(`${b.textContent.trim()} is projected from the same verified Aurum state.`,3)}));document.getElementById('focus-gpt').addEventListener('click',()=>prompt.focus());document.getElementById('clear-chat').addEventListener('click',()=>{messages.replaceChildren();message('aurum','Conversation cleared. Hopper state and action receipts remain governed by Aurum.');prompt.focus()});document.querySelectorAll('[data-prompt]').forEach(b=>b.addEventListener('click',()=>{prompt.value=b.dataset.prompt;ask()}));send.addEventListener('click',ask);prompt.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask()}});document.getElementById('search').addEventListener('keydown',e=>{if(e.key==='Enter'){const q=e.target.value.trim();if(q){prompt.value=`Show me ${q} on Hopper`;ask();e.target.value=''}}});
renderLivingMarks();let markResize;window.addEventListener('resize',()=>{clearTimeout(markResize);markResize=setTimeout(()=>{if(preparedMark)paintLivingMarks(preparedMark)},120)});refresh();setInterval(refresh,4000);
</script>
</body></html>'''


def _make_handler(gui):
    class HopperHandler(gui.AurumGuiHandler):
        def _status_payload(self) -> dict[str, Any]:
            try:
                payload = super()._status_payload()
            except Exception:
                payload = {"schema": SCHEMA, "console": {"identity": "Hopper"}}
            trait = _load_runtime_module("aurum_gpt_trait.py", "aurum_gpt_trait")
            try:
                gpt = trait.status() if trait else {"status": "unavailable"}
            except Exception as exc:
                gpt = {"status": "unavailable", "detail": f"{type(exc).__name__}:{exc}"}
            payload["schema"] = SCHEMA
            payload["hopper"] = {
                "telemetry": _telemetry(),
                "gpt": gpt,
                "projection": {
                    "renderer": "html5",
                    "fallback": "pygame",
                    "primary": True,
                    "identity_mark": {
                        "scope": "bruce-hopper-personal",
                        "renderer": "html5-canvas",
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
            if request_path != "/assets/aurum-mark.png":
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
            self.send_header("Content-Type", "image/png")
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
            if request_path not in {"/api/ask", "/api/action"}:
                super().do_POST()
                return
            payload = self._read_payload()
            if payload is None:
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
                except Exception as exc:
                    self._error(HTTPStatus.BAD_GATEWAY, f"GPT unavailable: {type(exc).__name__}:{exc}")
                    return
            self._json(
                HTTPStatus.OK,
                {
                    "schema": SCHEMA,
                    "status": result.get("status"),
                    "response": result.get("text"),
                    "tool_receipts": result.get("tool_receipts") or [],
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
