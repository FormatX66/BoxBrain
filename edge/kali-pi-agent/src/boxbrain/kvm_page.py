"""Browser keyboard and relative-mouse surface for the local HID broker."""

from __future__ import annotations

import json


def render_kvm_page(csrf_token: str) -> str:
    token = json.dumps(csrf_token)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>BoxBrain Morris PC controls</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
    body {{ margin: 0; background: #07100d; color: #e9fff5; }}
    main {{ width: min(900px, calc(100% - 28px)); margin: 28px auto; }}
    header {{ display:flex; align-items:center; justify-content:space-between; gap:16px; }}
    h1 {{ margin:.2rem 0; font-size:clamp(2rem,6vw,4rem); letter-spacing:-.05em; }}
    .eyebrow,.label {{ color:#62f5a7; text-transform:uppercase; letter-spacing:.12em; font-size:.78rem; font-weight:750; }}
    .panel {{ background:#0d1b16; border:1px solid #203b30; border-radius:18px; padding:20px; margin-top:14px; }}
    .status {{ border-radius:999px; padding:8px 13px; background:#26352f; color:#c8d2cd; }}
    .status.ready {{ background:#133d29; color:#8fffc0; }}
    .status.error {{ background:#5d1c25; color:#ffb7c0; }}
    .controls {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }}
    button {{ border:1px solid #2b7d55; border-radius:12px; background:#123323; color:#e9fff5; padding:12px 16px; font-weight:700; cursor:pointer; }}
    button.primary {{ background:#1d754b; }}
    button.danger {{ border-color:#88404a; background:#4a1c23; }}
    button:disabled {{ opacity:.45; cursor:not-allowed; }}
    #pad {{ min-height:300px; display:grid; place-items:center; border:2px dashed #2b7d55; border-radius:16px; margin-top:14px; background:#091510; user-select:none; touch-action:none; outline:none; }}
    #pad.armed {{ border-style:solid; background:#0d271c; box-shadow:inset 0 0 40px #0c4028; }}
    textarea {{ width:100%; box-sizing:border-box; min-height:90px; margin-top:10px; border:1px solid #315244; border-radius:12px; background:#07100d; color:#e9fff5; padding:12px; }}
    .note {{ color:#9bb1a7; line-height:1.5; }}
    a {{ color:#8fffc0; }}
    code {{ color:#c4ffe0; }}
  </style>
</head>
<body>
<main>
  <header>
    <div><div class="eyebrow">USB HID control</div><h1>Morris PC</h1></div>
    <div id="status" class="status">Checking</div>
  </header>
  <section class="panel">
    <div class="label">Keyboard + relative mouse</div>
    <p class="note">Arm only while Morris PC is the intended USB target. Click the pad to capture the mouse. Press <code>Ctrl+Alt+Esc</code> or the Release button to stop and release every key and button.</p>
    <div class="controls">
      <button id="arm" class="primary">Arm controls</button>
      <button id="release" class="danger">Release all</button>
      <button id="ctrlAltDel">Ctrl+Alt+Delete</button>
      <a href="/">Back to BoxBrain</a>
    </div>
    <div id="pad" tabindex="0"><strong>Click here for mouse and keyboard control</strong></div>
  </section>
  <section class="panel">
    <div class="label">Acknowledged single-character typing</div>
    <textarea id="text" maxlength="256" placeholder="Up to 256 US-keyboard characters"></textarea>
    <p class="note">Each character is sent as its own HID operation and must be acknowledged by the Pi before the next character is sent.</p>
    <div class="controls"><button id="sendText">Type one character at a time</button></div>
  </section>
  <p id="message" class="note">No input has been sent.</p>
</main>
<script>
const csrf = {token};
const pad = document.getElementById('pad');
const statusBadge = document.getElementById('status');
const message = document.getElementById('message');
let armed = false;
let buttons = 0;
let queue = Promise.resolve();
let pendingX = 0;
let pendingY = 0;
let pointerScheduled = false;

function request(payload) {{
  queue = queue.then(async () => {{
    const response = await fetch('/api/v1/hid-kvm/input', {{
      method: 'POST',
      credentials: 'same-origin',
      headers: {{'Content-Type':'application/json','X-BoxBrain-CSRF':csrf}},
      body: JSON.stringify(payload)
    }});
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || 'HID request failed');
    return result;
  }}).catch(error => {{
    statusBadge.textContent = 'Input error';
    statusBadge.className = 'status error';
    message.textContent = error.message;
    armed = false;
    pad.classList.remove('armed');
  }});
  return queue;
}}

async function refreshStatus() {{
  try {{
    const response = await fetch('/api/v1/hid-kvm/status', {{cache:'no-store'}});
    const result = await response.json();
    const ready = response.ok && result.ok && result.status.keyboard_ready && result.status.mouse_ready;
    statusBadge.textContent = ready ? (armed ? 'Armed' : 'Ready') : 'Unavailable';
    statusBadge.className = ready ? 'status ready' : 'status error';
    document.getElementById('arm').disabled = !ready;
  }} catch (_) {{
    statusBadge.textContent = 'Unavailable';
    statusBadge.className = 'status error';
  }}
}}

function releaseAll(reason='operator') {{
  armed = false;
  buttons = 0;
  pad.classList.remove('armed');
  if (document.pointerLockElement) document.exitPointerLock();
  message.textContent = `Controls released (${{reason}}).`;
  request({{action:'release'}}).then(refreshStatus);
}}

document.getElementById('arm').addEventListener('click', () => {{
  armed = true;
  pad.classList.add('armed');
  pad.focus();
  pad.requestPointerLock();
  message.textContent = 'Controls armed for Morris PC.';
  refreshStatus();
}});
document.getElementById('release').addEventListener('click', () => releaseAll());
pad.addEventListener('click', () => {{ if (armed) pad.requestPointerLock(); }});
pad.addEventListener('contextmenu', event => event.preventDefault());

window.addEventListener('keydown', event => {{
  if (!armed || ['TEXTAREA','INPUT','BUTTON'].includes(event.target.tagName)) return;
  if (event.ctrlKey && event.altKey && event.code === 'Escape') {{
    event.preventDefault();
    releaseAll('escape chord');
    return;
  }}
  event.preventDefault();
  if (!event.repeat) request({{action:'key',code:event.code,down:true}});
}});
window.addEventListener('keyup', event => {{
  if (!armed || ['TEXTAREA','INPUT'].includes(event.target.tagName)) return;
  event.preventDefault();
  request({{action:'key',code:event.code,down:false}});
}});

function buttonMask(button) {{ return button === 0 ? 1 : button === 2 ? 2 : button === 1 ? 4 : 0; }}
pad.addEventListener('mousedown', event => {{
  if (!armed) return;
  event.preventDefault();
  buttons |= buttonMask(event.button);
  request({{action:'pointer',dx:0,dy:0,wheel:0,buttons}});
}});
window.addEventListener('mouseup', event => {{
  if (!armed) return;
  buttons &= ~buttonMask(event.button);
  request({{action:'pointer',dx:0,dy:0,wheel:0,buttons}});
}});
document.addEventListener('mousemove', event => {{
  if (!armed || document.pointerLockElement !== pad) return;
  pendingX += event.movementX;
  pendingY += event.movementY;
  if (pointerScheduled) return;
  pointerScheduled = true;
  requestAnimationFrame(() => {{
    pointerScheduled = false;
    while (pendingX || pendingY) {{
      const dx = Math.max(-127, Math.min(127, pendingX));
      const dy = Math.max(-127, Math.min(127, pendingY));
      pendingX -= dx; pendingY -= dy;
      request({{action:'pointer',dx,dy,wheel:0,buttons}});
    }}
  }});
}});
pad.addEventListener('wheel', event => {{
  if (!armed) return;
  event.preventDefault();
  const wheel = event.deltaY > 0 ? -1 : 1;
  request({{action:'pointer',dx:0,dy:0,wheel,buttons}});
}}, {{passive:false}});

document.getElementById('sendText').addEventListener('click', async () => {{
  const text = document.getElementById('text').value;
  if (!text) return;
  const button = document.getElementById('sendText');
  button.disabled = true;
  let acknowledged = 0;
  try {{
    const released = await request({{action:'release'}});
    if (!released || !released.ok) throw new Error('Could not establish a released keyboard state.');
    for (const character of text) {{
      const result = await request({{action:'character',character}});
      if (!result || !result.acknowledged) throw new Error('The Pi did not acknowledge the character.');
      acknowledged += 1;
      message.textContent = `Acknowledged ${{acknowledged}} of ${{text.length}} characters.`;
    }}
    document.getElementById('text').value = '';
    message.textContent = `Typed and acknowledged ${{acknowledged}} characters; text was not logged.`;
  }} catch (error) {{
    message.textContent = `Stopped after ${{acknowledged}} acknowledged characters: ${{error.message}}`;
  }} finally {{
    button.disabled = false;
  }}
}});
document.getElementById('ctrlAltDel').addEventListener('click', async () => {{
  await request({{action:'key',code:'ControlLeft',down:true}});
  await request({{action:'key',code:'AltLeft',down:true}});
  await request({{action:'key',code:'Delete',down:true}});
  await request({{action:'release'}});
}});
window.addEventListener('blur', () => {{ if (armed) releaseAll('window blur'); }});
document.addEventListener('visibilitychange', () => {{ if (document.hidden && armed) releaseAll('page hidden'); }});
window.addEventListener('beforeunload', () => {{
  if (armed) fetch('/api/v1/hid-kvm/input', {{
    method:'POST', keepalive:true,
    headers:{{'Content-Type':'application/json','X-BoxBrain-CSRF':csrf}},
    body:JSON.stringify({{action:'release'}})
  }});
}});
refreshStatus();
setInterval(refreshStatus, 3000);
</script>
</body>
</html>"""
