#!/usr/bin/env python3
from pathlib import Path

GUI = Path("Projects/AurumPC/aurum_hopper_gui.py")
SURFACE = Path("Projects/AurumPC/aurum_web_surface.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"patch anchor missing: {label}")
    return text.replace(old, new, 1)


def patch_gui() -> None:
    text = GUI.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '  <button class="nav" data-nav="browser"><span>◎</span>Browser</button>\n',
        '  <button class="nav" data-nav="browser"><span>◎</span>Browser</button>\n'
        '  <button class="nav" data-nav="wifi"><span>⌁</span>Wi-Fi</button>\n',
        "wifi nav",
    )
    text = replace_once(
        text,
        '.prompt-wrap textarea{height:48px;resize:none;flex:1;border:1px solid rgba(255,255,255,.10);border-radius:7px;background:#0a0e0c;color:var(--ink);padding:12px;outline:none}',
        '.prompt-wrap input{height:48px;flex:1;border:1px solid rgba(255,255,255,.10);border-radius:7px;background:#0a0e0c;color:var(--ink);padding:0 12px;outline:none}',
        "prompt css",
    )
    text = replace_once(
        text,
        '.prompt-wrap textarea:focus{border-color:var(--gold)}',
        '.prompt-wrap input:focus{border-color:var(--gold)}',
        "prompt focus css",
    )
    text = replace_once(
        text,
        '<textarea id="prompt" maxlength="12000" placeholder="Ask Aurum about Hopper…" aria-label="Ask Aurum GPT"></textarea>',
        '<input id="prompt" type="text" maxlength="12000" autocomplete="off" placeholder="Ask Aurum about Hopper…" aria-label="Ask Aurum GPT">',
        "single-line Aurum prompt",
    )
    text = replace_once(
        text,
        "prompt.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask()}});",
        "prompt.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();ask()}});",
        "enter submits",
    )

    wifi_panel = '''  <section id="wifi-panel" class="wifi-panel" aria-label="Wi-Fi controls" hidden>
    <div class="wifi-head"><div><div class="teal">WIRELESS NETWORK</div><h2>Wi-Fi</h2><p>Scan, select, connect, disconnect, or forget the saved network directly from TinySeed.</p></div><button id="wifi-scan" class="wifi-button" type="button">Scan</button></div>
    <div class="wifi-layout">
      <div class="wifi-form"><label>Network name (SSID)</label><input id="wifi-ssid" maxlength="32" autocomplete="off" placeholder="Select a network or type its SSID"><label>Password</label><input id="wifi-password" type="password" maxlength="128" autocomplete="new-password" placeholder="Blank for an open network"><div class="wifi-actions"><button id="wifi-connect" class="wifi-button primary" type="button">Connect</button><button id="wifi-disconnect" class="wifi-button" type="button">Disconnect</button><button id="wifi-forget" class="wifi-button" type="button">Forget saved</button></div><div id="wifi-detail" class="wifi-detail">Use Scan to discover nearby networks.</div></div>
      <div class="wifi-results"><div class="wifi-results-title">Available networks</div><div id="wifi-networks" class="wifi-networks"></div></div>
    </div>
  </section>
'''
    text = replace_once(
        text,
        '  <section id="web-browser" class="web-browser" aria-label="Aurum web browser" hidden>\n',
        wifi_panel + '  <section id="web-browser" class="web-browser" aria-label="Aurum web browser" hidden>\n',
        "wifi panel",
    )

    wifi_css = '''
.wifi-panel{grid-column:1;grid-row:2;min-height:0;border:1px solid var(--line);border-radius:9px;background:radial-gradient(circle at 90% 0,rgba(19,198,202,.08),transparent 45%),linear-gradient(160deg,rgba(13,19,17,.98),rgba(5,8,7,.98));padding:18px;overflow:auto}.wifi-panel[hidden],.grid[hidden]{display:none!important}.wifi-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding-bottom:14px;border-bottom:1px solid var(--line)}.wifi-head h2{margin:4px 0;color:var(--gold2);font-size:26px;font-weight:420}.wifi-head p{margin:0;color:var(--muted);font-size:11px}.wifi-layout{display:grid;grid-template-columns:340px minmax(0,1fr);gap:14px;margin-top:16px}.wifi-form,.wifi-results{border:1px solid var(--line);border-radius:8px;background:#0a0e0c;padding:14px}.wifi-form label{display:block;color:var(--muted);font-size:9px;letter-spacing:.08em;text-transform:uppercase;margin:10px 0 5px}.wifi-form input{width:100%;height:40px;border:1px solid rgba(255,255,255,.10);border-radius:6px;background:#070b09;color:var(--ink);padding:0 10px;outline:none}.wifi-form input:focus{border-color:var(--gold)}.wifi-actions{display:flex;flex-wrap:wrap;gap:7px;margin-top:13px}.wifi-button{border:1px solid var(--line);border-radius:6px;background:#0a0e0c;color:var(--ink);padding:8px 11px;cursor:pointer}.wifi-button:hover{border-color:var(--teal);color:var(--teal2)}.wifi-button.primary{border-color:var(--gold);color:var(--gold2);background:rgba(211,166,64,.10)}.wifi-detail{margin-top:12px;color:var(--muted);font-size:10px;line-height:1.45}.wifi-results-title{color:var(--gold2);font-size:11px;letter-spacing:.1em;text-transform:uppercase;margin-bottom:10px}.wifi-networks{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.wifi-network{border:1px solid rgba(255,255,255,.08);border-radius:6px;background:#070b09;color:var(--ink);padding:9px;text-align:left;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.wifi-network:hover{border-color:var(--teal);color:var(--teal2)}@media(max-width:1150px){.wifi-layout{grid-template-columns:1fr}.wifi-networks{grid-template-columns:1fr}}
'''
    text = replace_once(text, '</style>\n</head>', wifi_css + '</style>\n</head>', "wifi css")
    text = replace_once(
        text,
        "const webStatus=document.getElementById('web-status');\n",
        "const webStatus=document.getElementById('web-status');\nconst wifiPanel=document.getElementById('wifi-panel');\nconst gridPanel=document.querySelector('.grid');\n",
        "wifi js refs",
    )

    navigation_js = r'''
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
'''
    anchor = "document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',()=>action(b.dataset.action)));"
    text = replace_once(text, anchor, navigation_js + anchor, "functional navigation js")
    old_nav = "document.querySelectorAll('[data-nav]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-nav]').forEach(x=>x.classList.remove('active'));b.classList.add('active');if(b.dataset.nav==='browser'){openWebBrowser();return}webBrowser.hidden=true;show(`${b.textContent.trim()} is projected from the same verified Aurum state.`,3)}));"
    text = replace_once(
        text,
        old_nav,
        "document.querySelectorAll('[data-nav]').forEach(b=>b.addEventListener('click',()=>showScreen(b.dataset.nav)));",
        "nav listener",
    )
    text = replace_once(
        text,
        "function closeWebBrowser(){webBrowser.hidden=true;document.querySelectorAll('[data-nav]').forEach(x=>x.classList.toggle('active',x.dataset.nav==='home'));document.getElementById('search').focus()}",
        "function closeWebBrowser(){showScreen('home');document.getElementById('search').focus()}",
        "browser close",
    )
    text = replace_once(
        text,
        '            if request_path not in {"/api/ask", "/api/action"}:\n',
        '            if request_path not in {"/api/ask", "/api/action", "/api/wifi"}:\n',
        "wifi endpoint allowlist",
    )
    wifi_backend = '''            if request_path == "/api/wifi":
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

'''
    text = replace_once(
        text,
        '            if request_path == "/api/action":\n',
        wifi_backend + '            if request_path == "/api/action":\n',
        "wifi backend",
    )
    GUI.write_text(text, encoding="utf-8")


def patch_surface() -> None:
    text = SURFACE.read_text(encoding="utf-8")
    text = replace_once(text, "import pwd\n", "import pwd\nimport re\n", "re import")
    helper = r'''
def _display_geometry(text: str):
    match = re.search(r"^(\S+)\s+connected(?:\s+primary)?(?:\s+(\d+)x(\d+)\+\d+\+\d+)?(?:\s+(normal|left|right|inverted))?", text, re.MULTILINE)
    if not match or not match.group(2) or not match.group(3):
        return None
    return {"output": match.group(1), "width": int(match.group(2)), "height": int(match.group(3)), "rotation": match.group(4) or "normal"}


def _force_landscape() -> dict[str, Any]:
    xrandr = shutil.which("xrandr")
    if not xrandr:
        return {"status": "unavailable", "reason": "xrandr-unavailable"}
    def query():
        result = subprocess.run([xrandr, "--query"], check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=8)
        return result.returncode, result.stdout
    try:
        code, raw = query()
        if code != 0:
            return {"status": "failed", "reason": "xrandr-query-failed", "detail": raw[-600:]}
        before = _display_geometry(raw)
        if before is None:
            return {"status": "unavailable", "reason": "active-output-unavailable"}
        if before["rotation"] != "normal" or before["width"] < before["height"]:
            subprocess.run([xrandr, "--output", before["output"], "--rotate", "normal"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
        _, raw = query()
        after = _display_geometry(raw)
        if after and after["width"] < after["height"]:
            subprocess.run([xrandr, "--output", after["output"], "--rotate", "right"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            _, raw = query()
            after = _display_geometry(raw)
        if after and after["width"] >= after["height"]:
            return {"status": "landscape", **after, "changed": after != before}
        return {"status": "degraded", "reason": "landscape-not-confirmed", "before": before, "after": after}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "failed", "reason": f"{type(exc).__name__}:{exc}"}


'''
    text = replace_once(text, "def main() -> int:\n", helper + "def main() -> int:\n", "landscape helper")
    text = replace_once(text, "    home = Path(account.pw_dir)\n", "    orientation = _force_landscape()\n\n    home = Path(account.pw_dir)\n", "landscape activation")
    text = replace_once(text, '        "--kiosk",\n', '        "--kiosk",\n        "--start-fullscreen",\n', "fullscreen flag")
    text = replace_once(text, '        "renderer": "html5",\n        "url": args.url,\n', '        "renderer": "html5",\n        "orientation": orientation,\n        "url": args.url,\n', "orientation receipt")
    SURFACE.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_gui()
    patch_surface()
    print("TinySeed physical GUI patch applied")
