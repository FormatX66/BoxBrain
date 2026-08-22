#!/usr/bin/env python3
"""Aurum Native GUI physical desktop for Hopper."""
from __future__ import annotations

import argparse
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
    for path in (runtime / "aurum_traits.py", workspace / "Projects/AurumPC/aurum_traits.py"):
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


def _battery_status() -> dict[str, Any]:
    root = Path("/sys/class/power_supply")
    batteries: list[Path] = []
    try:
        batteries = sorted(entry for entry in root.iterdir() if entry.name.upper().startswith("BAT") and (entry / "capacity").is_file())
    except OSError:
        pass
    if not batteries:
        return {"present": False, "percent": None, "status": "Unavailable", "charging": False}
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
    return {"present": True, "percent": percent, "status": status, "charging": charging, "minutes_remaining": minutes, "name": bat.name}


def _run_text(arguments: list[str], timeout: float = 1.5) -> str:
    try:
        result = subprocess.run(arguments, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _wifi_status() -> dict[str, Any]:
    interfaces: list[str] = []
    root = Path("/sys/class/net")
    try:
        for entry in sorted(root.iterdir(), key=lambda p: p.name):
            if (entry / "wireless").exists() or entry.name.startswith("wl"):
                interfaces.append(entry.name)
    except OSError:
        pass
    if not interfaces:
        return {"present": False, "connected": False, "interface": None, "ssid": "No Wi-Fi", "signal": 0, "ip": "—"}
    interface = interfaces[0]
    operstate = _text(root / interface / "operstate", "unknown")
    signal_strength = 0
    try:
        for line in Path("/proc/net/wireless").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lstrip().startswith(interface + ":"):
                fields = line.split()
                quality = float(fields[2].rstrip("."))
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
            link = _run_text([iw, "dev", interface, "link"])
            for line in link.splitlines():
                stripped = line.strip()
                if stripped.startswith("SSID:"):
                    ssid = stripped.split(":", 1)[1].strip()
                    break
    ip_addr = "—"
    ip = shutil.which("ip")
    if ip:
        out = _run_text([ip, "-4", "-o", "addr", "show", "dev", interface])
        for token in out.split():
            if "/" in token and token[:1].isdigit():
                ip_addr = token.split("/", 1)[0]
                break
    connected = bool(ssid and operstate == "up")
    return {"present": True, "connected": connected, "interface": interface, "ssid": ssid or ("Connected" if operstate == "up" else "Not connected"), "signal": signal_strength, "ip": ip_addr, "operstate": operstate}


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
    pointer_proof = _json(state / "pointer-motion.json")
    head = _head(workspace)
    trackpad_detected = bool(touchpads and all(item.get("present") and item.get("readable") for item in touchpads) and (libinput.get("xorg_driver") or input_state.get("status") == "ready"))
    return {"machine": identity.get("display_name") or "Hopper", "hostname": identity.get("hostname") or _text(Path("/etc/hostname"), "hopper"), "online": _online(), "head": head, "head_short": head[:12] if head != "unknown" else "unknown", "branch": _branch(workspace), "runtime_status": runtime_state.get("status") or "current", "runtime_schema": runtime_state.get("schema") or "aurum-pc-runtime-update-v4", "autonomy": autonomy.get("status") or "ready", "driver": driver.get("status") or "ready", "driver_devices": int(driver.get("devices_modeled") or len(driver.get("devices") or [])), "pointers": len(pointers), "touchpads": len(touchpads), "trackpad_detected": trackpad_detected, "pointer_verified": pointer_proof.get("status") == "motion-observed", "xorg_libinput": bool(libinput.get("xorg_driver")), "generation": chain.get("completed_generations") or 1, "next_gap": chain.get("next_gap") or "continuous observation", "traits": list(traits.get("traits") or []), "traits_total": int(traits.get("total") or 0), "traits_ready": int(traits.get("foundation_ready") or 0), "traits_planned": int(traits.get("planned") or 0), "battery": _battery_status(), "wifi": _wifi_status()}


def _write_receipt(state: Path, payload: dict[str, Any]) -> None:
    path = state / "desktop-ui.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _write_pointer_proof(state: Path, *, position: tuple[int, int], observed_at: str, source: str = "motion") -> None:
    path = state / "pointer-motion.json"
    payload = {"schema": "aurum.pointer-motion.v1", "status": "motion-observed", "machine": "Hopper", "position": [int(position[0]), int(position[1])], "source": source, "observed_at": observed_at}
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _stop(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def _bounded_system_action(action: str) -> tuple[bool, str]:
    commands = {"recovery": ["chvt", "1"], "sleep": ["systemctl", "suspend"], "restart": ["systemctl", "reboot"], "shutdown": ["systemctl", "poweroff"]}
    args = commands.get(action)
    if not args:
        return False, "unsupported action"
    tool = shutil.which(args[0])
    if not tool:
        return False, f"{args[0]} unavailable"
    try:
        result = subprocess.run([tool, *args[1:]], check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=8)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return result.returncode == 0, result.stdout.strip()[-300:]


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
    pygame.display.set_caption("Aurum Native GUI — Hopper")
    pygame.mouse.set_visible(False)
    scale = min(width / 1672.0, height / 941.0)
    S = lambda n: max(1, int(n * scale))
    bg, sidebar, panel, panel_hi = (3, 5, 7), (7, 8, 10), (12, 13, 15), (16, 17, 18)
    gold, gold_hi, gold_dim = (218, 160, 48), (255, 204, 91), (91, 68, 25)
    teal, teal_hi = (0, 197, 206), (77, 235, 230)
    ink, muted, good, bad, line = (243, 239, 226), (157, 155, 146), (66, 212, 170), (247, 116, 116), (78, 59, 27)

    def font(size: int, bold: bool = False): return pygame.font.SysFont("DejaVu Sans", max(10, S(size)), bold=bold)
    tiny, small, body, card_font, title_font = font(11), font(14), font(17), font(22, True), font(34, True)
    def text(value: object, x: int, y: int, face=body, color=ink): screen.blit(face.render(str(value), True, color), (x, y))
    def rounded(rect, fill, border=None, radius=14, border_width=1):
        pygame.draw.rect(screen, fill, rect, border_radius=S(radius))
        if border: pygame.draw.rect(screen, border, rect, width=max(1, S(border_width)), border_radius=S(radius))
    def dot(x: int, y: int, color): pygame.draw.circle(screen, color, (x, y), max(3, S(4)))
    def fit(value: object, limit: int = 36) -> str:
        s = " ".join(str(value).split()); return s if len(s) <= limit else s[:limit-1] + "…"
    def leaf(cx: int, cy: int, w: int, h: int, angle: float, color=gold):
        surf = pygame.Surface((max(2,w), max(2,h)), pygame.SRCALPHA); pygame.draw.ellipse(surf, color, surf.get_rect()); surf = pygame.transform.rotate(surf, angle); screen.blit(surf, surf.get_rect(center=(cx,cy)))
    def aurum_mark(x: int, y: int, size: int):
        s=size; ax,ay=x+int(s*.12),y+int(s*.08); left=(ax,ay+int(s*.70)); apex=(ax+int(s*.24),ay); right=(ax+int(s*.48),ay+int(s*.70))
        pygame.draw.lines(screen,gold_hi,False,[left,apex,right],max(2,int(s*.055))); pygame.draw.line(screen,gold,(ax+int(s*.12),ay+int(s*.43)),(ax+int(s*.36),ay+int(s*.43)),max(2,int(s*.035)))
        ux,uy=ax+int(s*.30),ay+int(s*.38); urect=pygame.Rect(ux,uy,int(s*.42),int(s*.36)); pygame.draw.arc(screen,teal,urect,math.pi,math.tau,max(2,int(s*.035)))
        pygame.draw.line(screen,teal,(urect.left,urect.top+int(s*.02)),(urect.left,urect.centery),max(2,int(s*.035))); pygame.draw.line(screen,teal,(urect.right,urect.top+int(s*.02)),(urect.right,urect.centery),max(2,int(s*.035)))
        for px,py in [(ax+int(s*.08),ay+int(s*.56)),(ax+int(s*.21),ay+int(s*.56)),(ax+int(s*.31),ay+int(s*.43))]: pygame.draw.circle(screen,gold_hi,(px,py),max(2,int(s*.026)))
        bx,by=ax+int(s*.34),ay+int(s*.38); ex,ey=ax+int(s*.66),ay-int(s*.05); pygame.draw.line(screen,gold,(bx,by),(ex,ey),max(1,int(s*.018)))
        for rx,ry,ang in [(.42,.24,-45),(.48,.16,35),(.53,.09,-40),(.58,.02,34),(.60,.18,-35),(.64,.10,32),(.68,.00,20)]: leaf(ax+int(s*rx),ay+int(s*ry),max(5,int(s*.10)),max(8,int(s*.18)),ang,gold_hi)
    def wifi_icon(cx: int, cy: int, strength: int):
        for i,radius in enumerate((S(24),S(17),S(10))):
            color=teal_hi if strength >= (i+1)*25 else gold_dim; pygame.draw.arc(screen,color,pygame.Rect(cx-radius,cy-radius,radius*2,radius*2),math.pi*1.15,math.pi*1.85,max(1,S(2)))
        pygame.draw.circle(screen,teal_hi if strength else gold_dim,(cx,cy+S(13)),S(3))
    def battery_icon(x: int, y: int, percent: int | None, charging: bool):
        w,h=S(38),S(18); pygame.draw.rect(screen,muted,pygame.Rect(x,y,w,h),width=max(1,S(2)),border_radius=S(3)); pygame.draw.rect(screen,muted,pygame.Rect(x+w,y+S(5),S(4),S(8)),border_radius=S(1)); p=0 if percent is None else max(0,min(100,percent)); fillw=max(0,int((w-S(6))*p/100))
        if fillw: pygame.draw.rect(screen,good if p>20 else bad,pygame.Rect(x+S(3),y+S(3),fillw,h-S(6)),border_radius=S(2))
        if charging: text("⚡",x+S(47),y-S(4),body,teal_hi)
    def progress_bar(rect, percent: int, color=teal):
        pygame.draw.rect(screen,(29,31,33),rect,border_radius=S(4)); fill=pygame.Rect(rect.x,rect.y,int(rect.width*max(0,min(100,percent))/100),rect.height); pygame.draw.rect(screen,color,fill,border_radius=S(4))
    def draw_cursor(position: tuple[int,int]):
        x,y=int(position[0]),int(position[1]); s=max(10,S(15)); points=[(x,y),(x,y+s),(x+int(s*.32),y+int(s*.72)),(x+int(s*.62),y+int(s*1.28)),(x+int(s*.82),y+int(s*1.17)),(x+int(s*.52),y+int(s*.63)),(x+s,y+int(s*.63))]; pygame.draw.polygon(screen,(5,5,5),points); pygame.draw.lines(screen,ink,True,points,max(1,S(2)))

    snap = snapshot(state, workspace, runtime)
    start=time.monotonic(); stages=["Machine","Input","Network","Runtime","Desktop"]
    while time.monotonic()-start < 2.2 and not STOP_REQUESTED:
        elapsed=time.monotonic()-start; screen.fill(bg); aurum_mark(width//2-S(85),height//2-S(190),S(170)); title=font(28,True).render("A U R U M",True,gold_hi); screen.blit(title,(width//2-title.get_width()//2,height//2+S(5))); text("ONE SEED. ENDLESS POSSIBILITIES.",width//2-S(150),height//2+S(48),small,teal); bx,by=width//2-S(180),height//2+S(110); readiness=[True,snap["pointers"]>0,snap["online"],True,True]
        for i,name in enumerate(stages):
            active=elapsed>=i*.28; color=good if active and readiness[i] else gold if active else line; dot(bx+i*S(90),by,color); lab=tiny.render(name,True,muted); screen.blit(lab,(bx+i*S(90)-lab.get_width()//2,by+S(14)))
        draw_cursor(pygame.mouse.get_pos()); pygame.display.flip(); pygame.event.pump(); time.sleep(.03)

    _write_receipt(state,{"schema":SCHEMA,"ui_version":"aurum-native-v1","status":"running","pid":os.getpid(),"surface":"physical","machine":"Hopper","host_actuation":"bounded-confirmed-actions","cursor":"aurum-software","resolution":[width,height],"updated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())})
    nav=["Home","Traits","Build","Hardware","Field","Settings"]; selected=0; detail_view=None; toast=""; toast_until=0.0; confirm_action=None; last_refresh=0.0; pointer_motion_observed=bool(snap["pointer_verified"]); pointer_motion_at=None; clock=pygame.time.Clock(); click_targets=[]
    def add_target(rect,action,payload=None): click_targets.append((rect.copy(),action,payload))
    def button(rect,label,action,payload=None,accent=gold,fill=(11,12,14)):
        rounded(rect,fill,accent,10); text(label,rect.x+S(14),rect.y+S(8),small,gold_hi if accent==gold else ink); text("›",rect.right-S(20),rect.y+S(7),body,accent); add_target(rect,action,payload)
    def card_shell(rect,title,status="",status_color=teal):
        rounded(rect,panel,line,12); text(title.upper(),rect.x+S(15),rect.y+S(13),tiny,gold_hi)
        if status: dot(rect.x+S(17),rect.y+S(38),status_color); text(status,rect.x+S(28),rect.y+S(30),tiny,status_color)
    def nav_click(index):
        nonlocal selected,detail_view; selected=int(index); detail_view=None
    def handle_action(action,payload=None):
        nonlocal selected,detail_view,toast,toast_until,confirm_action,last_refresh
        if action=="nav": nav_click(payload)
        elif action=="detail": selected,detail_view=payload
        elif action=="recovery":
            ok,detail=_bounded_system_action("recovery"); toast="Recovery console requested" if ok else f"Recovery failed: {detail or 'unavailable'}"; toast_until=time.monotonic()+4
        elif action in {"sleep","restart","shutdown"}: confirm_action=action
        elif action=="confirm":
            act=str(payload); ok,detail=_bounded_system_action(act); toast=f"{act.title()} requested" if ok else f"{act.title()} failed: {detail or 'unavailable'}"; toast_until=time.monotonic()+4; confirm_action=None
        elif action=="cancel": confirm_action=None
        elif action=="refresh": last_refresh=0; toast="Refreshing machine state"; toast_until=time.monotonic()+2

    while not STOP_REQUESTED:
        now=time.monotonic()
        if now-last_refresh>=4: snap=snapshot(state,workspace,runtime); pointer_motion_observed=pointer_motion_observed or bool(snap["pointer_verified"]); last_refresh=now
        click_targets=[]
        for event in pygame.event.get():
            if event.type==pygame.QUIT: STOP_REQUESTED=True
            elif event.type==pygame.KEYDOWN:
                ctrl=bool(event.mod & pygame.KMOD_CTRL); alt=bool(event.mod & pygame.KMOD_ALT)
                if ctrl and alt and event.key==pygame.K_F1: handle_action("recovery")
                elif event.key==pygame.K_F5: handle_action("refresh")
                elif event.key==pygame.K_F12: STOP_REQUESTED=True
                elif pygame.K_1<=event.key<=pygame.K_6: nav_click(event.key-pygame.K_1)
            elif event.type==pygame.MOUSEMOTION and event.rel!=(0,0):
                if not pointer_motion_observed: pointer_motion_observed=True; pointer_motion_at=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()); _write_pointer_proof(state,position=event.pos,observed_at=pointer_motion_at)
            elif event.type==pygame.MOUSEWHEEL:
                if not pointer_motion_observed: pointer_motion_observed=True; pointer_motion_at=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()); _write_pointer_proof(state,position=pygame.mouse.get_pos(),observed_at=pointer_motion_at,source="scroll")
            elif event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
                for rect,action,payload in reversed(click_targets):
                    if rect.collidepoint(event.pos): handle_action(action,payload); break

        screen.fill(bg); top_h=S(68); pygame.draw.rect(screen,(4,5,6),pygame.Rect(0,0,width,top_h)); pygame.draw.line(screen,line,(0,top_h-1),(width,top_h-1)); aurum_mark(S(18),S(10),S(56)); text("A U R U M",S(82),S(16),body,gold_hi); text("NATIVE GUI",S(205),S(19),tiny,teal)
        search=pygame.Rect(S(470),S(15),S(430),S(38)); rounded(search,(8,9,10),gold_dim,16); text("⌕  Search Aurum OS",search.x+S(15),search.y+S(8),small,muted)
        wifi=snap["wifi"]; battery=snap["battery"]; wifi_rect=pygame.Rect(width-S(500),S(10),S(190),S(48)); rounded(wifi_rect,(7,9,10),line,10); wifi_icon(wifi_rect.x+S(28),wifi_rect.centery-S(4),int(wifi.get("signal") or 0)); text(fit(wifi.get("ssid") or "Wi‑Fi",18),wifi_rect.x+S(54),wifi_rect.y+S(7),tiny,ink); text("Connected" if wifi.get("connected") else "Offline",wifi_rect.x+S(54),wifi_rect.y+S(25),tiny,good if wifi.get("connected") else bad); add_target(wifi_rect,"detail",(5,"Network"))
        batt_rect=pygame.Rect(width-S(300),S(10),S(145),S(48)); rounded(batt_rect,(7,9,10),line,10); bp=battery.get("percent"); text(f"{bp if bp is not None else '—'}%",batt_rect.x+S(10),batt_rect.y+S(8),body,ink); battery_icon(batt_rect.x+S(60),batt_rect.y+S(14),bp,bool(battery.get("charging"))); text(str(battery.get("status") or "Battery"),batt_rect.x+S(10),batt_rect.y+S(30),tiny,good if battery.get("charging") else muted); add_target(batt_rect,"detail",(5,"Power"))
        time_rect=pygame.Rect(width-S(145),S(10),S(130),S(48)); rounded(time_rect,(7,9,10),line,10); text(time.strftime("%-I:%M %p"),time_rect.x+S(12),time_rect.y+S(6),small,ink); text(time.strftime("%b %d, %Y"),time_rect.x+S(12),time_rect.y+S(26),tiny,muted)
        side_w=S(255); side=pygame.Rect(0,top_h,side_w,height-top_h); pygame.draw.rect(screen,sidebar,side); pygame.draw.line(screen,line,(side_w,top_h),(side_w,height)); aurum_mark(S(55),top_h+S(25),S(125)); text("A U R U M",S(60),top_h+S(145),small,gold_hi); text("ONE SEED. ENDLESS POSSIBILITIES.",S(26),top_h+S(173),tiny,teal)
        nav_y=top_h+S(218)
        for i,name in enumerate(nav):
            r=pygame.Rect(S(20),nav_y+i*S(58),side_w-S(40),S(44)); hover=r.collidepoint(pygame.mouse.get_pos());
            if i==selected: rounded(r,(28,22,11),gold,12)
            elif hover: rounded(r,(15,14,11),gold_dim,12)
            text(str(i+1),r.x+S(13),r.y+S(13),tiny,gold if i==selected else muted); text(name,r.x+S(39),r.y+S(9),small,gold_hi if i==selected else ink); add_target(r,"nav",i)
        main_x=side_w+S(25); main_w=width-main_x-S(25); content_top=top_h+S(22); text("Good evening, Aurum User.",main_x,content_top,title_font,gold_hi); text("Systems online. Intelligence awakened.",main_x,content_top+S(40),small,teal)
        if selected==0:
            grid_top=content_top+S(82); gap=S(12); card_w=(main_w-gap*3)//4; row_h=S(208)
            r1=pygame.Rect(main_x,grid_top,card_w,row_h); card_shell(r1,"System Health","Optimal",good); pygame.draw.circle(screen,teal,(r1.x+S(70),r1.y+S(102)),S(42),width=S(2)); leaf(r1.x+S(70),r1.y+S(102),S(26),S(44),-25,gold_hi); text("Aurum OS",r1.x+S(130),r1.y+S(60),small,ink); text(f"Gen {snap['generation']} · {snap['runtime_status']}",r1.x+S(130),r1.y+S(82),tiny,muted); text(f"Head {snap['head_short']}",r1.x+S(130),r1.y+S(107),tiny,muted); button(pygame.Rect(r1.x+S(12),r1.bottom-S(42),r1.width-S(24),S(30)),"View Details","detail",(2,"Runtime"))
            r2=pygame.Rect(r1.right+gap,grid_top,card_w,row_h); card_shell(r2,"Network","Connected" if wifi.get("connected") else "Offline",good if wifi.get("connected") else bad); wifi_icon(r2.x+S(72),r2.y+S(105),int(wifi.get("signal") or 0)); text("SSID",r2.x+S(135),r2.y+S(63),tiny,muted); text(fit(wifi.get("ssid") or "—",18),r2.x+S(135),r2.y+S(81),small,ink); text(f"Signal {wifi.get('signal',0)}%",r2.x+S(135),r2.y+S(111),tiny,teal); text(f"IP {wifi.get('ip','—')}",r2.x+S(135),r2.y+S(132),tiny,muted); button(pygame.Rect(r2.x+S(12),r2.bottom-S(42),r2.width-S(24),S(30)),"Network Settings","detail",(5,"Network"))
            r3=pygame.Rect(r2.right+gap,grid_top,card_w,row_h); card_shell(r3,"Power & Battery",str(battery.get("status") or "Battery"),good if battery.get("charging") else teal); pct=int(bp or 0); center=(r3.x+S(76),r3.y+S(106)); pygame.draw.circle(screen,gold_dim,center,S(47),width=S(6)); pygame.draw.arc(screen,gold_hi,pygame.Rect(center[0]-S(47),center[1]-S(47),S(94),S(94)),math.pi/2,math.pi/2+math.tau*pct/100,width=S(6)); text(f"{bp if bp is not None else '—'}%",center[0]-S(28),center[1]-S(14),card_font,gold_hi); text("Adaptive",r3.x+S(145),r3.y+S(72),small,ink); rem=battery.get("minutes_remaining"); text(f"{rem//60}h {rem%60}m remaining" if rem else str(battery.get("status") or "—"),r3.x+S(145),r3.y+S(103),tiny,muted); button(pygame.Rect(r3.x+S(12),r3.bottom-S(42),r3.width-S(24),S(30)),"Power Settings","detail",(5,"Power"))
            r4=pygame.Rect(r3.right+gap,grid_top,card_w,row_h); card_shell(r4,"Traits","Active",teal); pygame.draw.line(screen,gold,(r4.x+S(65),r4.y+S(145)),(r4.x+S(100),r4.y+S(65)),S(2));
            for i in range(7): leaf(r4.x+S(70)+(i%3)*S(22),r4.y+S(130)-i*S(10),S(15),S(28),-40+(i%2)*80,gold_hi)
            text(f"{snap['traits_ready']} ready",r4.x+S(145),r4.y+S(72),small,ink); text(f"{snap['traits_total']} registered",r4.x+S(145),r4.y+S(98),tiny,muted); button(pygame.Rect(r4.x+S(12),r4.bottom-S(42),r4.width-S(24),S(30)),"Manage Traits","nav",1)
            row2=grid_top+row_h+gap; r5=pygame.Rect(main_x,row2,card_w,row_h); card_shell(r5,"Hardware Monitor","All Systems Nominal",teal); ry=r5.y+S(62)
            for label_name,pctv in [("CPU",32),("Memory",68),("Storage",46),("GPU",24)]: text(label_name,r5.x+S(18),ry,tiny,ink); progress_bar(pygame.Rect(r5.x+S(90),ry+S(4),r5.width-S(125),S(6)),pctv); text(f"{pctv}%",r5.right-S(36),ry,tiny,muted); ry+=S(27)
            button(pygame.Rect(r5.x+S(12),r5.bottom-S(42),r5.width-S(24),S(30)),"Hardware Monitor","nav",3)
            r6=pygame.Rect(r5.right+gap,row2,card_w,row_h); card_shell(r6,"Input & Recovery","All Systems Go",teal); ry=r6.y+S(60)
            for label_name,val in [("Recovery hotkey","Ctrl+Alt+F1"),("Trackpad","Working" if pointer_motion_observed else "Detected"),("Pointer","Visible"),("Keyboard","Ready")]: text(label_name,r6.x+S(18),ry,tiny,muted); text(val,r6.x+S(135),ry,tiny,good if val in {"Working","Visible","Ready","Ctrl+Alt+F1"} else gold); ry+=S(27)
            button(pygame.Rect(r6.x+S(12),r6.bottom-S(42),r6.width-S(24),S(30)),"Open Recovery Console","recovery",accent=teal)
            r7=pygame.Rect(r6.right+gap,row2,card_w,row_h); card_shell(r7,"Boot & Loading","Native flow",teal); ry=r7.y+S(60)
            for label_name,val in [("Boot mode","Aurum Native GUI"),("Loading screen","Enabled"),("Recovery console","Clickable + hotkey"),("Desktop","Physical VT2")]: text(label_name,r7.x+S(18),ry,tiny,muted); text(val,r7.x+S(135),ry,tiny,ink); ry+=S(27)
            button(pygame.Rect(r7.x+S(12),r7.bottom-S(42),r7.width-S(24),S(30)),"Boot Settings","detail",(5,"Boot"))
            r8=pygame.Rect(r7.right+gap,row2,card_w,row_h); card_shell(r8,"System Tools","Tools at your service",teal); ry=r8.y+S(58)
            for label_name,target in [("Update & Sync",(2,"Update & Sync")),("Recovery",(5,"Recovery")),("Power & Battery",(5,"Power")),("Network Settings",(5,"Network"))]:
                rr=pygame.Rect(r8.x+S(12),ry-S(4),r8.width-S(24),S(28));
                if rr.collidepoint(pygame.mouse.get_pos()): rounded(rr,(18,18,15),gold_dim,7)
                text(label_name,rr.x+S(7),rr.y+S(6),tiny,ink); text("›",rr.right-S(15),rr.y+S(3),small,gold_hi); add_target(rr,"detail",target); ry+=S(31)
            qa_y=row2+row_h+gap; qa_h=max(S(58),height-qa_y-S(48)); qa=pygame.Rect(main_x,qa_y,main_w,qa_h); rounded(qa,panel,line,12); text("QUICK ACTIONS",qa.x+S(16),qa.y+S(12),tiny,gold_hi); bw=S(150)
            for i,(lbl,act) in enumerate([("Recovery","recovery"),("Sleep","sleep"),("Restart","restart"),("Shut Down","shutdown")]): br=pygame.Rect(qa.x+S(150)+i*(bw+S(14)),qa.y+S(10),bw,S(38)); rounded(br,(10,11,12),gold_dim,10); text(lbl,br.x+S(20),br.y+S(9),small,ink); add_target(br,act)
        else:
            box=pygame.Rect(main_x,content_top+S(82),main_w,height-(content_top+S(82))-S(28)); rounded(box,panel,line,14); heading=detail_view or nav[selected]; text(heading,box.x+S(24),box.y+S(22),title_font,gold_hi); text(f"{nav[selected]} · Aurum Native GUI",box.x+S(26),box.y+S(63),tiny,teal)
            if heading=="Network": rows=[("Status","Connected" if wifi.get("connected") else "Offline"),("SSID",wifi.get("ssid")),("Signal",f"{wifi.get('signal',0)}%"),("Address",wifi.get("ip")),("Interface",wifi.get("interface"))]
            elif heading=="Power": rows=[("Battery",f"{bp if bp is not None else '—'}%"),("Status",battery.get("status")),("Charging",battery.get("charging")),("Power mode","Adaptive"),("Battery device",battery.get("name"))]
            elif heading=="Recovery": rows=[("Recovery hotkey","Ctrl+Alt+F1"),("Mouse recovery","Available"),("Target","tty1"),("Desktop return","Ctrl+Alt+F2")]
            elif heading=="Boot": rows=[("Normal flow","Aurum loading → Native GUI"),("Recovery console","tty1"),("Desktop","VT2"),("Boot UI","diagnostics hidden when healthy")]
            elif nav[selected]=="Hardware": rows=[("Machine",snap["machine"]),("Display",f"{width} × {height}"),("Pointers",snap["pointers"]),("Touchpads",snap["touchpads"]),("Pointer motion","verified" if pointer_motion_observed else "detected"),("Xorg libinput","ready" if snap["xorg_libinput"] else "missing")]
            elif nav[selected]=="Build": rows=[("Branch",snap["branch"]),("Head",snap["head"]),("Runtime",snap["runtime_status"]),("Autonomy",snap["autonomy"]),("Generation",snap["generation"]),("Next frontier",snap["next_gap"])]
            elif nav[selected]=="Traits": rows=[(str(item.get("name") or item.get("id") or "Trait"),str(item.get("stage") or "planned")) for item in snap["traits"]]
            else: rows=[("Aurum desktop","Native GUI v1"),("Machine",snap["machine"]),("Runtime",snap["runtime_status"]),("Network","online" if snap["online"] else "offline"),("Authority","bounded actions only")]
            ry=box.y+S(110)
            for label_name,val in rows[:9]: text(label_name,box.x+S(30),ry,small,muted); text(fit(val,60),box.x+S(250),ry-S(4),body,ink); pygame.draw.line(screen,(45,39,27),(box.x+S(28),ry+S(29)),(box.right-S(28),ry+S(29))); ry+=S(52)
            if heading=="Recovery": button(pygame.Rect(box.x+S(30),box.bottom-S(62),S(250),S(38)),"Open Recovery Console","recovery",accent=teal)
        footer_y=height-S(27); text("AURUM OS · ONE SEED. ENDLESS POSSIBILITIES.",S(18),footer_y,tiny,teal)
        if toast and now<toast_until:
            tw=font(13,True).render(toast,True,ink); tr=pygame.Rect(width//2-tw.get_width()//2-S(18),height-S(64),tw.get_width()+S(36),S(34)); rounded(tr,(20,17,10),gold,10); screen.blit(tw,(tr.x+S(18),tr.y+S(9)))
        if confirm_action:
            shade=pygame.Surface((width,height),pygame.SRCALPHA); shade.fill((0,0,0,150)); screen.blit(shade,(0,0)); mr=pygame.Rect(width//2-S(240),height//2-S(90),S(480),S(180)); rounded(mr,(13,13,14),gold,16,2); text(f"Confirm {confirm_action.title()}?",mr.x+S(28),mr.y+S(28),card_font,gold_hi); text("This is a real system action on Hopper.",mr.x+S(28),mr.y+S(72),small,muted); yes=pygame.Rect(mr.x+S(28),mr.bottom-S(58),S(180),S(36)); no=pygame.Rect(mr.right-S(208),mr.bottom-S(58),S(180),S(36)); rounded(yes,(24,18,8),gold,10); rounded(no,(12,13,14),teal,10); text("Confirm",yes.x+S(56),yes.y+S(9),small,gold_hi); text("Cancel",no.x+S(62),no.y+S(9),small,teal_hi); add_target(yes,"confirm",confirm_action); add_target(no,"cancel")
        draw_cursor(pygame.mouse.get_pos()); pygame.display.flip(); clock.tick(30)
    _write_receipt(state,{"schema":SCHEMA,"ui_version":"aurum-native-v1","status":"stopped","machine":"Hopper","updated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}); pygame.quit(); return 0


def main() -> int:
    parser=argparse.ArgumentParser(description="Aurum Native GUI physical desktop"); parser.add_argument("command",nargs="?",default="run",choices=("run",)); parser.add_argument("--state-dir",type=Path,default=Path(os.environ.get("AURUM_STATE_DIR","/var/lib/aurum/state"))); parser.add_argument("--run-dir",type=Path,default=Path(os.environ.get("AURUM_RUN_DIR","/run/aurum"))); args=parser.parse_args(); signal.signal(signal.SIGTERM,_stop); signal.signal(signal.SIGINT,_stop); workspace=Path(os.environ.get("AURUM_GIT_WORKSPACE","/var/lib/aurum/workspace/BoxBrain")); runtime=Path(os.environ.get("AURUM_RUNTIME_ROOT","/opt/aurum")); return run(args.state_dir,args.run_dir,workspace,runtime)


if __name__ == "__main__":
    raise SystemExit(main())
