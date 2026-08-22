#!/usr/bin/env python3
"""Gen1 HTML projection for Hopper.

Aurum owns state, policy, execution, verification, and receipts.  This module
projects those semantics into HTML/CSS/JS for human interaction.  It reuses the
existing loopback-only Aurum GUI server and extends it with bounded Hopper
telemetry, direct-control actions, and the resident GPT trait.  No raw shell is
exposed through the browser surface.
"""
from __future__ import annotations

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
</style>
</head>
<body>
<div class="shell">
<header class="top">
  <div class="brand"><div class="sigil"><b>A</b></div><div class="brand-name">AURUM</div></div>
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
    <div class="teal">LIVE MACHINE PROJECTION</div>
    <h1 id="greeting">Good afternoon, Aurum User.</h1>
    <p>Aurum adapts the human view. Machine truth stays underneath.</p>
    <svg class="canopy" viewBox="0 0 700 160" aria-hidden="true"><g fill="none" stroke="#cba044" stroke-width="2"><path d="M10 145 C95 128 110 50 190 18"/><path d="M95 104 l42 -20 M112 84 l-30 -22 M140 58 l40 -18 M158 38 l-28 -20"/></g><g fill="#d9ae4b"><ellipse cx="125" cy="85" rx="15" ry="5" transform="rotate(-28 125 85)"/><ellipse cx="92" cy="64" rx="14" ry="5" transform="rotate(28 92 64)"/><ellipse cx="175" cy="41" rx="14" ry="5" transform="rotate(-22 175 41)"/><ellipse cx="133" cy="20" rx="13" ry="5" transform="rotate(25 133 20)"/></g><g fill="none" stroke="#19bfc4" stroke-width="1.4" opacity=".75"><path d="M200 22 H310 l25 18 h120 l30 -22 h160"/><path d="M200 48 H285 l25 20 h180 l35 -19 h120"/><path d="M184 76 H350 l22 18 h95 l30 -16 h150"/><path d="M150 105 H260 l20 18 h170 l32 -17 h175"/></g><g fill="#e5ba55"><circle cx="200" cy="22" r="4"/><circle cx="200" cy="48" r="4"/><circle cx="184" cy="76" r="4"/><circle cx="150" cy="105" r="4"/></g></svg>
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
</main>
<footer class="dock">
  <div class="prompt-wrap"><textarea id="prompt" maxlength="12000" placeholder="Ask GPT to inspect or change Hopper…" aria-label="Ask GPT"></textarea><input id="apiKey" class="key" type="password" maxlength="512" autocomplete="off" placeholder="API key if needed"></div>
  <button id="send" class="send">Send to Aurum</button>
</footer>
</div>
<div id="toast" class="toast"></div>
<script nonce="{{NONCE}}">
const csrf=document.querySelector('meta[name="aurum-csrf"]').content;
const toast=document.getElementById('toast');
const prompt=document.getElementById('prompt');
const key=document.getElementById('apiKey');
const send=document.getElementById('send');
function show(message,seconds=6){toast.textContent=message;toast.classList.add('show');clearTimeout(show.t);show.t=setTimeout(()=>toast.classList.remove('show'),seconds*1000)}
function pct(id,value){const node=document.getElementById(id);if(node)node.textContent=value==null?'—':`${value}%`;const bar=document.getElementById(`${id}-bar`);if(bar)bar.style.width=value==null?'0%':`${Math.max(0,Math.min(100,value))}%`}
function humanDuration(seconds){if(seconds==null)return'—';const h=Math.floor(seconds/3600),m=Math.floor((seconds%3600)/60);return `${h}h ${m}m`}
function first(obj,keys){for(const k of keys){if(obj&&obj[k]!=null&&obj[k]!=='' )return obj[k]}return null}
async function refresh(){try{const r=await fetch('/api/status',{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||'status unavailable');const h=d.hopper||{},t=h.telemetry||{},s=t.state||{},n=t.network||{},b=t.battery||{},tm=t.time||{},g=h.gpt||{};document.getElementById('machine').textContent=s.machine||'Hopper';document.getElementById('runtime-state').textContent=s.runtime||'Unknown';document.getElementById('desktop').textContent=s.desktop_generation||s.desktop||'Unknown';document.getElementById('autonomy').textContent=s.autonomy||'Unknown';document.getElementById('input-state').textContent=s.input||'Unknown';document.getElementById('uptime').textContent=humanDuration(t.uptime_seconds);pct('memory',t.memory_percent);pct('storage',t.storage_percent);const connected=first(n,['online','connected','status']);document.getElementById('net-state').textContent=connected===true?'Connected':(connected||'Unknown');const ssid=first(n,['ssid','connection','network']);document.getElementById('ssid').textContent=ssid||'Unknown';document.getElementById('wifi').textContent=ssid||'Network';document.getElementById('net-if').textContent=first(n,['interface','device'])||'Unknown';document.getElementById('net-ip').textContent=first(n,['ip','address','ipv4'])||'Unknown';document.getElementById('battery').textContent=b.percent==null?'—':`${b.percent}%`;document.getElementById('battery-big').textContent=b.percent==null?'—':`${b.percent}%`;document.getElementById('battery-sub').textContent=b.status||'Unknown';document.getElementById('power-state').textContent=b.charging?'Charging':(b.status||'Unknown');document.getElementById('gpt-state').textContent=g.status||'Unknown';document.getElementById('gpt-tools').textContent=g.function_tools?'Ready':'Unavailable';document.getElementById('time-state').textContent=tm.synchronized?'Server synchronized':'Local / unknown';if(tm.local_iso){const date=new Date(tm.local_iso);if(!Number.isNaN(date.valueOf()))document.getElementById('clock').textContent=date.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'})}}catch(e){show(`Status: ${e.message||e}`,4)}}
async function action(name){try{show(`${name}…`,2);const r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-Aurum-CSRF':csrf},body:JSON.stringify({action:name})});const d=await r.json();if(!r.ok)throw new Error(d.error||'action failed');show(JSON.stringify(d.result||d,null,2),5);await refresh()}catch(e){show(e.message||String(e),6)}}
async function ask(){const text=prompt.value.trim();if(!text)return;send.disabled=true;show('GPT is working directly with Hopper…',20);try{const body={prompt:text};if(key.value.trim())body.api_key=key.value.trim();const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json','X-Aurum-CSRF':csrf},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw new Error(d.error||'GPT unavailable');show(d.response||'Completed',12);prompt.value='';await refresh()}catch(e){show(e.message||String(e),8)}finally{send.disabled=false}}
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',()=>action(b.dataset.action)));document.querySelectorAll('[data-nav]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-nav]').forEach(x=>x.classList.remove('active'));b.classList.add('active');show(`${b.textContent.trim()} projection is adaptive; detailed panel coming from the same Aurum state model.`,3)}));document.getElementById('focus-gpt').addEventListener('click',()=>prompt.focus());send.addEventListener('click',ask);prompt.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask()}});document.getElementById('search').addEventListener('keydown',e=>{if(e.key==='Enter'){const q=e.target.value.trim();if(q){prompt.value=`Show me ${q} on Hopper`;ask();e.target.value=''}}});
async function bootstrapKey(){try{const r=await fetch('/api/key-bootstrap',{method:'POST',headers:{'Content-Type':'application/json','X-Aurum-CSRF':csrf},body:JSON.stringify({action:'consume'})});const d=await r.json();if(r.ok&&d.available&&typeof d.api_key==='string'){key.value=d.api_key;d.api_key='';key.placeholder='API key loaded in page memory'}}catch(_){}}
bootstrapKey();refresh();setInterval(refresh,4000);
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
                "projection": {"renderer": "html5", "fallback": "pygame", "primary": True},
            }
            payload["authority"] = {
                "dialogue_only": False,
                "host_actuation": "bounded",
                "raw_shell": False,
                "git_push": False,
                "api_key_persisted": False,
            }
            return payload

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

            if not set(payload).issubset({"prompt", "api_key", "model"}):
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
            supplied_key = payload.get("api_key")
            if supplied_key is not None and (not isinstance(supplied_key, str) or len(supplied_key) > gui.MAX_API_KEY_CHARS):
                self._error(HTTPStatus.BAD_REQUEST, "API key invalid")
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
                old_key = os.environ.get("OPENAI_API_KEY")
                try:
                    if isinstance(supplied_key, str) and supplied_key.strip():
                        os.environ["OPENAI_API_KEY"] = supplied_key.strip()
                    result = trait.ask(prompt.strip(), **kwargs)
                except Exception as exc:
                    self._error(HTTPStatus.BAD_GATEWAY, f"GPT unavailable: {type(exc).__name__}:{exc}")
                    return
                finally:
                    if old_key is None:
                        os.environ.pop("OPENAI_API_KEY", None)
                    else:
                        os.environ["OPENAI_API_KEY"] = old_key
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
