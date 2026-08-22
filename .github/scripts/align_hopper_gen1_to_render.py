#!/usr/bin/env python3
"""Align Hopper's Gen1 physical surface with the approved Aurum render.

This migration changes presentation only. Every machine value remains measured
from Hopper or explicitly unknown. It also keeps controls bounded to existing
Aurum actions.
"""
from pathlib import Path
import re

PATH = Path("Projects/AurumPC/aurum_desktop.py")
text = PATH.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"missing migration anchor: {label}")
    text = text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Real runtime + hardware identity telemetry for the richer render cards.
# ---------------------------------------------------------------------------
if "def _runtime_activity()" not in text:
    marker = "\ndef _power_profile() -> str | None:\n"
    helper = r'''

def _runtime_activity() -> dict[str, Any]:
    uptime_seconds = None
    try:
        uptime_seconds = max(0, int(float(_text(Path("/proc/uptime"), "0").split()[0])))
    except (ValueError, IndexError):
        pass
    processes = 0
    threads = 0
    try:
        entries = [entry for entry in Path("/proc").iterdir() if entry.name.isdigit()]
    except OSError:
        entries = []
    for entry in entries:
        processes += 1
        try:
            threads += sum(1 for child in (entry / "task").iterdir() if child.name.isdigit())
        except OSError:
            continue
    return {
        "uptime_seconds": uptime_seconds,
        "processes": processes if entries else None,
        "threads": threads if entries else None,
    }


def _hardware_labels() -> dict[str, Any]:
    cpu_model = None
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                cpu_model = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass

    memory_total = None
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("MemTotal:"):
                memory_total = int(line.split()[1]) * 1024
                break
    except (OSError, ValueError, IndexError):
        pass

    storage_total = None
    try:
        storage_total = shutil.disk_usage("/").total
    except OSError:
        pass

    gpu_model = None
    lspci = shutil.which("lspci")
    if lspci:
        for line in _run_text([lspci], timeout=2).splitlines():
            lowered = line.lower()
            if "vga compatible controller" in lowered or "3d controller" in lowered:
                gpu_model = line.split(": ", 1)[-1].strip()
                break

    return {
        "cpu_model": cpu_model,
        "memory_total_bytes": memory_total,
        "storage_total_bytes": storage_total,
        "gpu_model": gpu_model,
    }


def _human_bytes(value: int | None) -> str | None:
    if value is None or value <= 0:
        return None
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    index = 0
    while amount >= 1024.0 and index < len(units) - 1:
        amount /= 1024.0
        index += 1
    precision = 0 if amount >= 10 or index < 3 else 1
    return f"{amount:.{precision}f} {units[index]}"
'''
    if marker not in text:
        raise SystemExit("missing _power_profile marker")
    text = text.replace(marker, helper + marker, 1)

replace_once(
    '        "gpu_percent": _gpu_percent(),\n        "power_profile": _power_profile(),',
    '        "gpu_percent": _gpu_percent(),\n        "runtime_activity": _runtime_activity(),\n        "hardware_labels": _hardware_labels(),\n        "power_profile": _power_profile(),',
    "snapshot telemetry",
)

# ---------------------------------------------------------------------------
# State for a real, bounded search box.
# ---------------------------------------------------------------------------
replace_once(
    '    detail_view: str | None = None\n    toast = ""',
    '    detail_view: str | None = None\n    search_active = False\n    search_query = ""\n    toast = ""',
    "search state",
)
replace_once(
    '        nonlocal selected, detail_view, toast, toast_until, confirm_action, last_refresh, snap',
    '        nonlocal selected, detail_view, search_active, search_query, toast, toast_until, confirm_action, last_refresh, snap',
    "handle_action nonlocal",
)
replace_once(
    '        if action == "nav":\n            nav_click(payload)',
    '        if action == "nav":\n            search_active = False\n            pygame.key.stop_text_input()\n            nav_click(payload)\n        elif action == "search":\n            search_active = True\n            pygame.key.start_text_input()\n            toast = "Search Hopper systems · Enter to open"\n            toast_until = time.monotonic() + 2',
    "search action",
)

# Search keyboard handling: text input is deliberately restricted to known
# system surfaces, so it cannot become an arbitrary command field.
old_key = '''            elif event.type == pygame.KEYDOWN:\n                ctrl = bool(event.mod & pygame.KMOD_CTRL)\n                alt = bool(event.mod & pygame.KMOD_ALT)\n                if ctrl and alt and event.key == pygame.K_F1:\n                    handle_action("recovery")\n                elif event.key == pygame.K_F5:\n                    handle_action("refresh")\n                elif event.key == pygame.K_F12:\n                    STOP_REQUESTED = True\n                elif pygame.K_1 <= event.key <= pygame.K_6:\n                    nav_click(event.key - pygame.K_1)'''
new_key = '''            elif event.type == pygame.KEYDOWN:\n                ctrl = bool(event.mod & pygame.KMOD_CTRL)\n                alt = bool(event.mod & pygame.KMOD_ALT)\n                if search_active:\n                    if event.key == pygame.K_ESCAPE:\n                        search_active = False\n                        search_query = ""\n                        pygame.key.stop_text_input()\n                    elif event.key == pygame.K_BACKSPACE:\n                        search_query = search_query[:-1]\n                    elif event.key == pygame.K_RETURN:\n                        query = search_query.strip().casefold()\n                        destinations = [\n                            (("network", "wifi"), (5, "Network")),\n                            (("power", "battery"), (5, "Power")),\n                            (("time", "clock", "ntp"), (5, "Time")),\n                            (("recover", "recovery"), (5, "Recovery")),\n                            (("runtime", "update", "sync"), (2, "Runtime")),\n                            (("build",), (2, None)),\n                            (("hardware", "cpu", "memory", "gpu", "storage"), (3, None)),\n                            (("trait",), (1, None)),\n                            (("field",), (4, None)),\n                            (("setting",), (5, None)),\n                        ]\n                        found = None\n                        for words, destination in destinations:\n                            if any(word in query for word in words):\n                                found = destination\n                                break\n                        search_active = False\n                        pygame.key.stop_text_input()\n                        if found is None:\n                            toast = f"No bounded system match for {search_query!r}"\n                            toast_until = time.monotonic() + 3\n                        elif found[1] is None:\n                            nav_click(found[0])\n                        else:\n                            selected, detail_view = found\n                        search_query = ""\n                elif ctrl and alt and event.key == pygame.K_F1:\n                    handle_action("recovery")\n                elif event.key == pygame.K_F5:\n                    handle_action("refresh")\n                elif event.key == pygame.K_F12:\n                    STOP_REQUESTED = True\n                elif pygame.K_1 <= event.key <= pygame.K_6:\n                    nav_click(event.key - pygame.K_1)\n            elif event.type == pygame.TEXTINPUT and search_active:\n                if len(search_query) < 48:\n                    search_query += event.text'''
replace_once(old_key, new_key, "search keyboard")

# ---------------------------------------------------------------------------
# Render-specific iconography and canopy.
# ---------------------------------------------------------------------------
if "def draw_nav_icon(" not in text:
    marker = "\n    def wifi_icon(cx: int, cy: int, strength: int | None):\n"
    helpers = r'''

    def draw_nav_icon(name: str, cx: int, cy: int, active: bool = False):
        color = gold_hi if active else gold
        teal_color = teal_hi if active else teal
        w = max(1, S(2))
        if name == "Home":
            pygame.draw.lines(screen, color, False, [(cx-S(9),cy),(cx,cy-S(9)),(cx+S(9),cy)], w)
            pygame.draw.rect(screen, color, pygame.Rect(cx-S(7),cy,S(14),S(10)), width=w, border_radius=S(1))
        elif name == "Traits":
            pygame.draw.line(screen, color, (cx-S(6),cy+S(9)), (cx+S(7),cy-S(9)), w)
            leaf(cx-S(2), cy-S(1), S(8), S(14), -42, color)
            leaf(cx+S(5), cy-S(6), S(7), S(12), 38, color)
        elif name == "Build":
            pygame.draw.lines(screen, color, False, [(cx-S(10),cy),(cx-S(4),cy-S(6)),(cx-S(4),cy+S(6))], w)
            pygame.draw.lines(screen, color, False, [(cx+S(10),cy),(cx+S(4),cy-S(6)),(cx+S(4),cy+S(6))], w)
        elif name == "Hardware":
            pygame.draw.rect(screen, teal_color, pygame.Rect(cx-S(7),cy-S(7),S(14),S(14)), width=w, border_radius=S(2))
            for d in (-10, 10):
                pygame.draw.line(screen, teal_color, (cx+d,cy-S(4)), (cx+d//2,cy-S(4)), w)
                pygame.draw.line(screen, teal_color, (cx+d,cy+S(4)), (cx+d//2,cy+S(4)), w)
        elif name == "Field":
            pts=[(cx-S(8),cy+S(5)),(cx,cy-S(7)),(cx+S(9),cy+S(2))]
            pygame.draw.lines(screen, teal_color, False, pts, w)
            for p in pts: pygame.draw.circle(screen, teal_color, p, max(2,S(3)))
        else:
            pygame.draw.circle(screen, color, (cx,cy), S(8), width=w)
            pygame.draw.circle(screen, teal_color, (cx,cy), S(3), width=w)
            for angle in range(0,360,45):
                dx=int(math.cos(math.radians(angle))*S(12)); dy=int(math.sin(math.radians(angle))*S(12))
                pygame.draw.line(screen,color,(cx+int(dx*.65),cy+int(dy*.65)),(cx+dx,cy+dy),w)

    def circuit_canopy(rect):
        # Botanical branch on the left side of the canopy.
        base=(rect.x+S(18), rect.bottom-S(10))
        tip=(rect.x+S(160), rect.y+S(8))
        pygame.draw.line(screen, gold, base, tip, max(1,S(2)))
        for i in range(7):
            t=(i+1)/8
            x=int(base[0]+(tip[0]-base[0])*t); y=int(base[1]+(tip[1]-base[1])*t)
            leaf(x-S(10),y-S(3),S(15),S(27),-55,gold_hi)
            if i not in {0,6}: leaf(x+S(10),y+S(2),S(13),S(24),45,gold)
        # Circuit traces flow out to the right, echoing the approved render.
        start_x=rect.x+S(170)
        for i in range(5):
            yy=rect.y+S(18)+i*S(12)
            pts=[(start_x,yy),(start_x+S(48),yy),(start_x+S(72),yy-S(8)),(rect.right-S(52),yy-S(8)),(rect.right-S(25),yy-S(20))]
            pygame.draw.lines(screen, teal if i%2==0 else gold_dim, False, pts, max(1,S(2)))
            pygame.draw.circle(screen, gold_hi, pts[0], max(2,S(3)))
            pygame.draw.circle(screen, gold_hi, pts[-1], max(2,S(3)))

    def medallion(cx: int, cy: int, radius: int, percent: int | None = None, teal_ring: bool = False):
        ring = teal if teal_ring else gold
        pygame.draw.circle(screen, (7,11,13), (cx,cy), radius)
        pygame.draw.circle(screen, gold_dim, (cx,cy), radius, width=max(1,S(2)))
        pygame.draw.circle(screen, ring, (cx,cy), radius-S(7), width=max(1,S(2)))
        if percent is not None:
            pygame.draw.arc(screen, gold_hi, pygame.Rect(cx-radius,cy-radius,radius*2,radius*2), -math.pi/2, -math.pi/2+math.tau*max(0,min(100,percent))/100, width=max(2,S(4)))

    def format_uptime(seconds: int | None) -> str:
        if seconds is None:
            return "Unknown"
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        if days:
            return f"{days}d {hours}h {minutes}m"
        if hours:
            return f"{hours}h {minutes}m {secs}s"
        return f"{minutes}m {secs}s"
'''
    if marker not in text:
        raise SystemExit("missing wifi helper marker")
    text = text.replace(marker, helpers + marker, 1)

# ---------------------------------------------------------------------------
# Replace the main shell/chrome. Detail pages below remain intact.
# ---------------------------------------------------------------------------
start = text.index("        click_targets.clear()\n        screen.fill(bg)\n")
home = text.index("        if selected == 0:\n", start)
new_chrome = r'''        click_targets.clear()
        screen.fill((2, 4, 6))
        outer = pygame.Rect(S(8), S(8), width-S(16), height-S(16))
        rounded(outer, (2,4,6), gold_dim, 14, 1)

        top_h = S(70)
        pygame.draw.line(screen, gold_dim, (S(9),top_h), (width-S(9),top_h), max(1,S(1)))
        aurum_mark(S(28), S(13), S(48))
        text("A U R U M", S(86), S(20), body, gold_hi)
        text("NATIVE GUI", S(220), S(23), tiny, teal)

        search_rect = pygame.Rect(S(470), S(18), S(445), S(36))
        rounded(search_rect, (5,8,10), teal if search_active else gold_dim, 16, 1)
        text("⌕", search_rect.x+S(14), search_rect.y+S(5), body, muted)
        text(search_query if search_active and search_query else "Search Aurum OS", search_rect.x+S(42), search_rect.y+S(8), small, ink if search_active else muted)
        add_target(search_rect, "search")

        wifi = snap["wifi"]
        battery = snap["battery"]
        time_state = snap["time"]
        bp = battery.get("percent")

        machine_x = width-S(570)
        draw_nav_icon("Traits", machine_x, S(34), True)
        text(fit(snap["machine"],16), machine_x+S(24), S(19), small, ink)
        text(fit(snap["hostname"],18), machine_x+S(24), S(38), tiny, muted)
        pygame.draw.line(screen,line,(machine_x+S(150),S(14)),(machine_x+S(150),S(56)))

        wifi_icon(machine_x+S(190), S(34), wifi.get("signal"))
        signal_label = f"{wifi.get('signal')}%" if wifi.get("signal") is not None else "—"
        text(signal_label, machine_x+S(218), S(25), small, ink)
        pygame.draw.line(screen,line,(machine_x+S(274),S(14)),(machine_x+S(274),S(56)))

        text(f"{bp}%" if bp is not None else "—", machine_x+S(292), S(24), small, ink)
        battery_icon(machine_x+S(334), S(26), bp, bool(battery.get("charging")))
        pygame.draw.line(screen,line,(machine_x+S(396),S(14)),(machine_x+S(396),S(56)))

        try:
            display_dt = dt.datetime.fromisoformat(str(time_state.get("local_iso")))
            time_label = display_dt.strftime("%-I:%M %p")
            date_label = display_dt.strftime("%a, %b %d, %Y")
        except (TypeError, ValueError):
            time_label, date_label = "Time unknown", "Not synchronized"
        text(time_label, machine_x+S(414), S(17), small, ink)
        text(date_label, machine_x+S(414), S(38), tiny, muted)
        if not time_state.get("synchronized"):
            text("LOCAL", width-S(48), S(18), tiny, warn)
        add_target(pygame.Rect(machine_x+S(404),S(12),S(155),S(45)), "detail", (5,"Time"))

        side_w = S(218)
        pygame.draw.line(screen, gold_dim, (side_w,top_h), (side_w,height-S(9)), max(1,S(1)))
        aurum_mark(S(45), top_h+S(28), S(118))

        nav_y = top_h+S(174)
        for i,name in enumerate(nav):
            rect=pygame.Rect(S(18),nav_y+i*S(58),side_w-S(36),S(46))
            hover=rect.collidepoint(pygame.mouse.get_pos())
            if i==selected:
                rounded(rect,(25,19,9),gold,14,1)
            elif hover:
                rounded(rect,(10,13,15),gold_dim,14,1)
            draw_nav_icon(name, rect.x+S(31), rect.centery, i==selected)
            text(name,rect.x+S(62),rect.y+S(11),small,gold_hi if i==selected else ink)
            add_target(rect,"nav",i)

        user_rect=pygame.Rect(S(18),height-S(90),side_w-S(36),S(64))
        rounded(user_rect,(6,9,11),gold_dim,16,1)
        medallion(user_rect.x+S(29),user_rect.centery,S(19),teal_ring=True)
        leaf(user_rect.x+S(29),user_rect.centery,S(10),S(18),-25,gold_hi)
        text("Aurum User",user_rect.x+S(57),user_rect.y+S(15),small,ink)
        text("Hopper",user_rect.x+S(57),user_rect.y+S(37),tiny,muted)
        text("›",user_rect.right-S(20),user_rect.y+S(21),body,gold_hi)
        add_target(user_rect,"nav",5)

        main_x=side_w+S(30)
        main_w=width-main_x-S(28)
        content_top=top_h+S(34)
        hour=dt.datetime.now().hour
        greeting="Good morning" if hour<12 else ("Good afternoon" if hour<18 else "Good evening")
        text(f"{greeting}, Aurum User.",main_x,content_top,title_font,gold_hi)
        text("Systems online. Intelligence awakened.",main_x,content_top+S(39),small,teal)
        canopy=pygame.Rect(main_x+main_w-S(620),content_top-S(8),S(610),S(92))
        circuit_canopy(canopy)
'''
text = text[:start] + new_chrome + text[home:]

# ---------------------------------------------------------------------------
# Replace the whole Home dashboard with render-aligned cards.
# ---------------------------------------------------------------------------
pattern = re.compile(r'(?ms)^        if selected == 0:\n.*?^        else:\n            box = pygame\.Rect\(')
match = pattern.search(text)
if not match:
    raise SystemExit("home dashboard block not found")
new_home = r'''        if selected == 0:
            grid_top=content_top+S(92)
            gap=S(12)
            card_w=(main_w-gap*3)//4
            row_h=S(218)
            runtime_activity=snap.get("runtime_activity") or {}
            hardware_labels=snap.get("hardware_labels") or {}

            # RUNTIME STATUS
            r1=pygame.Rect(main_x,grid_top,card_w,row_h)
            card_shell(r1,"Runtime Status",fit(snap.get("runtime_status"),18),good if snap.get("runtime_status") not in {None,"unknown","failed"} else warn)
            medallion(r1.x+S(85),r1.y+S(112),S(48),teal_ring=True)
            leaf(r1.x+S(85),r1.y+S(112),S(23),S(43),-24,gold_hi)
            tx=r1.x+S(150)
            text("Aurum Runtime",tx,r1.y+S(57),small,ink)
            text(GENERATION_NAME,tx,r1.y+S(78),tiny,muted)
            text("Uptime",tx,r1.y+S(103),tiny,muted)
            text(format_uptime(runtime_activity.get("uptime_seconds")),tx,r1.y+S(119),small,ink)
            text(f"Processes  {runtime_activity.get('processes') if runtime_activity.get('processes') is not None else '—'}",tx,r1.y+S(145),tiny,muted)
            text(f"Threads    {runtime_activity.get('threads') if runtime_activity.get('threads') is not None else '—'}",tx,r1.y+S(162),tiny,muted)
            button(pygame.Rect(r1.x+S(12),r1.bottom-S(40),r1.width-S(24),S(28)),"View Details","detail",(2,"Runtime"))

            # NETWORK
            r2=pygame.Rect(r1.right+gap,grid_top,card_w,row_h)
            card_shell(r2,"Network","Connected" if wifi.get("connected") else "Offline",good if wifi.get("connected") else bad)
            wifi_icon(r2.x+S(74),r2.y+S(112),wifi.get("signal"))
            tx=r2.x+S(140)
            text("SSID",tx,r2.y+S(60),tiny,muted); text(fit(wifi.get("ssid"),18),tx,r2.y+S(79),small,ink)
            text("Signal Strength",tx,r2.y+S(106),tiny,muted)
            strength=wifi.get("signal")
            text(f"{strength}%" if strength is not None else "Unknown",tx,r2.y+S(124),small,teal if strength is not None else warn)
            for i in range(10):
                bh=S(3+i); bx=tx+i*S(10); by=r2.y+S(154)
                pygame.draw.rect(screen,teal if strength is not None and strength >= (i+1)*10 else (28,39,42),pygame.Rect(bx,by-bh,S(5),bh),border_radius=S(1))
            text(f"IP {wifi.get('ip') or 'Unknown'}",tx,r2.y+S(164),tiny,muted)
            button(pygame.Rect(r2.x+S(12),r2.bottom-S(40),r2.width-S(24),S(28)),"Network Settings","detail",(5,"Network"))

            # POWER
            r3=pygame.Rect(r2.right+gap,grid_top,card_w,row_h)
            card_shell(r3,"Power",fit(battery.get("status"),18),good if battery.get("charging") else teal)
            medallion(r3.x+S(82),r3.y+S(111),S(50),int(bp) if bp is not None else None)
            text(f"{bp}%" if bp is not None else "—",r3.x+S(55),r3.y+S(95),card_font,gold_hi)
            text("Battery",r3.x+S(61),r3.y+S(124),tiny,muted)
            tx=r3.x+S(150)
            text("Power Mode",tx,r3.y+S(60),tiny,muted); text(fit(snap.get("power_profile"),16),tx,r3.y+S(80),small,ink)
            remaining=battery.get("minutes_remaining")
            text("Time Remaining",tx,r3.y+S(108),tiny,muted)
            text(f"{remaining//60}h {remaining%60}m" if remaining is not None else "Unknown",tx,r3.y+S(127),small,ink)
            text("Health",tx,r3.y+S(154),tiny,muted); text("Charging" if battery.get("charging") else fit(battery.get("status"),16),tx,r3.y+S(171),tiny,good if battery.get("charging") else muted)
            button(pygame.Rect(r3.x+S(12),r3.bottom-S(40),r3.width-S(24),S(28)),"Power & Battery","detail",(5,"Power"))

            # TRAITS
            r4=pygame.Rect(r3.right+gap,grid_top,card_w,row_h)
            card_shell(r4,"Traits",f"{snap['traits_ready']} ready" if snap["traits_total"] else "No evidence",teal if snap["traits_total"] else muted)
            pygame.draw.line(screen,gold,(r4.x+S(50),r4.y+S(165)),(r4.x+S(112),r4.y+S(67)),max(1,S(2)))
            for i in range(7):
                leaf(r4.x+S(62)+(i%3)*S(22),r4.y+S(151)-i*S(12),S(14),S(27),-42+(i%2)*82,gold_hi)
            tx=r4.x+S(155)
            text("Registered Traits",tx,r4.y+S(57),tiny,muted)
            trait_items=list(snap.get("traits") or [])[:5]
            for i,item in enumerate(trait_items):
                yy=r4.y+S(80)+i*S(19); dot(tx+S(4),yy+S(4),gold_hi); text(fit(item.get("name"),17),tx+S(16),yy,tiny,ink)
            if not trait_items: text("Unknown",tx,r4.y+S(84),small,warn)
            button(pygame.Rect(r4.x+S(12),r4.bottom-S(40),r4.width-S(24),S(28)),"Manage Traits","nav",1)

            row2=grid_top+row_h+gap

            # BUILD STATUS
            r5=pygame.Rect(main_x,row2,card_w,row_h)
            card_shell(r5,"Build Status",fit(snap.get("runtime_status"),18),good if snap.get("runtime_status") not in {None,"unknown","failed"} else warn)
            medallion(r5.x+S(82),r5.y+S(112),S(46),teal_ring=True)
            pygame.draw.lines(screen,gold_hi,False,[(r5.x+S(63),r5.y+S(113)),(r5.x+S(77),r5.y+S(127)),(r5.x+S(104),r5.y+S(94))],max(2,S(3)))
            tx=r5.x+S(145)
            text("Aurum OS",tx,r5.y+S(59),small,ink)
            text(f"Generation {snap.get('generation') if snap.get('generation') is not None else 'Unknown'}",tx,r5.y+S(82),tiny,muted)
            text("Branch",tx,r5.y+S(108),tiny,muted); text(fit(snap.get("branch"),20),tx,r5.y+S(125),tiny,ink)
            text("Head",tx,r5.y+S(148),tiny,muted); text(fit(snap.get("head_short"),18),tx,r5.y+S(165),tiny,ink)
            button(pygame.Rect(r5.x+S(12),r5.bottom-S(40),r5.width-S(24),S(28)),"Build Details","detail",(2,"Runtime"))

            # HARDWARE
            r6=pygame.Rect(r5.right+gap,row2,card_w,row_h)
            metrics=[("CPU",snap.get("cpu_percent"),hardware_labels.get("cpu_model")),("Memory",snap.get("memory_percent"),_human_bytes(hardware_labels.get("memory_total_bytes"))),("Storage",snap.get("storage_percent"),_human_bytes(hardware_labels.get("storage_total_bytes"))),("GPU",snap.get("gpu_percent"),hardware_labels.get("gpu_model"))]
            card_shell(r6,"Hardware",f"{sum(v is not None for _,v,_ in metrics)}/4 live",teal)
            yy=r6.y+S(62)
            for label_name,value,identity in metrics:
                draw_nav_icon("Hardware",r6.x+S(29),yy+S(7),False)
                text(label_name,r6.x+S(48),yy,tiny,ink)
                text(fit(identity,21),r6.x+S(103),yy,tiny,muted)
                progress_bar(pygame.Rect(r6.right-S(96),yy+S(5),S(58),S(5)),value)
                text(f"{value}%" if value is not None else "—",r6.right-S(34),yy,tiny,muted)
                yy+=S(31)
            button(pygame.Rect(r6.x+S(12),r6.bottom-S(40),r6.width-S(24),S(28)),"Hardware Monitor","nav",3)

            # INPUTS
            r7=pygame.Rect(r6.right+gap,row2,card_w,row_h)
            card_shell(r7,"Inputs","Pointer verified" if pointer_motion_observed else "Detected",good if pointer_motion_observed else warn)
            pad=pygame.Rect(r7.x+S(25),r7.y+S(65),S(116),S(84)); rounded(pad,(8,12,15),teal,10,1)
            pygame.draw.circle(screen,teal_hi,(pad.centerx,pad.bottom-S(15)),max(2,S(3)))
            text("Trackpad",r7.x+S(165),r7.y+S(66),small,ink); text("Working" if pointer_motion_observed else ("Detected" if snap.get("trackpad_detected") else "Unknown"),r7.x+S(165),r7.y+S(88),tiny,good if pointer_motion_observed else muted)
            text("Keyboard",r7.x+S(165),r7.y+S(120),small,ink); text(f"{snap.get('keyboards')} detected" if snap.get("keyboards") else "Unknown",r7.x+S(165),r7.y+S(142),tiny,muted)
            button(pygame.Rect(r7.x+S(12),r7.bottom-S(40),r7.width-S(24),S(28)),"Input Settings","detail",(5,"Recovery"),accent=teal)

            # SYSTEM TOOLS
            r8=pygame.Rect(r7.right+gap,row2,card_w,row_h)
            card_shell(r8,"System Tools","Bounded actions",teal)
            tools=[("Update & Sync",(2,"Runtime")),("Recovery",(5,"Recovery")),("Time Server",(5,"Time")),("Network",(5,"Network"))]
            yy=r8.y+S(58)
            for label_name,target in tools:
                rr=pygame.Rect(r8.x+S(12),yy-S(3),r8.width-S(24),S(30))
                if rr.collidepoint(pygame.mouse.get_pos()): rounded(rr,(15,17,17),gold_dim,7)
                draw_nav_icon("Settings",rr.x+S(16),rr.centery,False)
                text(label_name,rr.x+S(36),rr.y+S(7),tiny,ink); text("›",rr.right-S(16),rr.y+S(4),small,gold_hi)
                add_target(rr,"detail",target); yy+=S(32)

            # QUICK ACTIONS
            qa_y=row2+row_h+gap
            qa_h=S(86)
            qa=pygame.Rect(main_x,qa_y,main_w,qa_h); rounded(qa,(5,8,10),gold_dim,12,1)
            text("QUICK ACTIONS",qa.x+S(16),qa.y+S(13),tiny,gold_hi)
            actions=[("Refresh","refresh"),("Recovery","recovery"),("Sleep","sleep"),("Restart","restart"),("Shut Down","shutdown")]
            bw=(qa.width-S(230))//len(actions)
            for i,(label_name,action) in enumerate(actions):
                br=pygame.Rect(qa.x+S(135)+i*(bw+S(10)),qa.y+S(18),bw,S(50))
                rounded(br,(8,11,13),teal if action=="refresh" else gold_dim,10,1)
                text(label_name,br.x+S(18),br.y+S(15),small,ink); add_target(br,action)

            # BOTTOM DOCK — every item is a real navigation target.
            dock_w=S(560); dock_h=S(58); dock=pygame.Rect(width//2-dock_w//2,height-S(72),dock_w,dock_h)
            rounded(dock,(6,8,10),gold_dim,18,1)
            slots=[("Home",0),("Field",4),("Traits",1),("Build",2),("Hardware",3),("Settings",5)]
            sw=(dock.width-S(20))//len(slots)
            for i,(name,index) in enumerate(slots):
                sr=pygame.Rect(dock.x+S(10)+i*sw,dock.y+S(7),sw-S(4),dock.height-S(14))
                if index==selected: rounded(sr,(22,17,9),gold_dim,10)
                draw_nav_icon(name,sr.centerx,sr.centery,index==selected); add_target(sr,"nav",index)
            text(GENERATION_NAME,S(28),height-S(45),tiny,gold_hi)
            text("ONE SEED. ENDLESS POSSIBILITIES.",S(28),height-S(27),tiny,teal)

        else:
            box = pygame.Rect('''
text = text[:match.start()] + new_home + text[match.end():]

# Footer on Home would overlap the render-style dock. Keep it for detail pages only.
text = text.replace(
    '        footer_y = height - S(27)\n        text(\n            "AURUM OS · LIVE VALUES ARE MEASURED; MISSING VALUES ARE SHOWN AS UNKNOWN.",\n            S(18),\n            footer_y,\n            tiny,\n            teal,\n        )',
    '        if selected != 0:\n            footer_y = height - S(27)\n            text(\n                "AURUM OS · LIVE VALUES ARE MEASURED; MISSING VALUES ARE SHOWN AS UNKNOWN.",\n                S(18),\n                footer_y,\n                tiny,\n                teal,\n            )',
    1,
)

PATH.write_text(text, encoding="utf-8")
print("Aligned Hopper Gen1 physical surface to approved render")
