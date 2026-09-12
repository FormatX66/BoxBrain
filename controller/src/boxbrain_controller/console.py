from fastapi.responses import HTMLResponse


def console_response() -> HTMLResponse:
    return HTMLResponse(_CONSOLE_HTML)


_CONSOLE_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover" />
<meta name="theme-color" content="#0b0f14" />
<title>BoxBrain One Console</title>
<style>
:root{color-scheme:dark;--bg:#0b0f14;--panel:#111820;--line:#24313d;--text:#e8f0f7;--muted:#8ea0b2;--ok:#61d095;--warn:#f2c14e;--bad:#ff6b6b;--accent:#67b7ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}button,input,textarea{font:inherit}
header{position:sticky;top:0;z-index:10;display:flex;gap:12px;align-items:center;justify-content:space-between;padding:12px 16px;background:#0b0f14e8;border-bottom:1px solid var(--line);backdrop-filter:blur(10px)}
.brand{font-weight:800;letter-spacing:.12em}.sub{color:var(--muted);font-size:12px}.status{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.pill{border:1px solid var(--line);border-radius:999px;padding:5px 8px}.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
main{padding:14px;display:grid;grid-template-columns:repeat(12,1fr);gap:12px;max-width:1600px;margin:auto}.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;min-width:0}.card h2{font-size:13px;margin:0 0 10px;color:var(--accent);text-transform:uppercase;letter-spacing:.08em}.span12{grid-column:span 12}.span8{grid-column:span 8}.span6{grid-column:span 6}.span4{grid-column:span 4}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.metric{border:1px solid var(--line);border-radius:9px;padding:10px}.metric b{display:block;font-size:22px}.metric small{color:var(--muted)}
.list{display:grid;gap:8px;max-height:340px;overflow:auto}.item{border:1px solid var(--line);border-radius:9px;padding:9px}.row{display:flex;gap:8px;align-items:center;justify-content:space-between}.meta{color:var(--muted);font-size:12px;overflow-wrap:anywhere}.actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}button{background:#16212b;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:7px 10px;cursor:pointer}button:hover{border-color:var(--accent)}button.danger{border-color:#6d2f35;color:#ffb1b1}button.primary{border-color:#2d6fa3;color:#b8dcff}
.command{display:grid;grid-template-columns:1fr auto auto;gap:8px}textarea,input{width:100%;background:#0c1218;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:9px}textarea{min-height:72px;resize:vertical}.token{display:grid;grid-template-columns:1fr auto;gap:8px}.console{background:#06090d;border:1px solid var(--line);border-radius:9px;padding:10px;max-height:420px;overflow:auto;white-space:pre-wrap;word-break:break-word}.event{padding:5px 0;border-bottom:1px dashed #1e2a34}.event:last-child{border:0}.stamp{color:var(--muted)}
footer{padding:16px;color:var(--muted);text-align:center;font-size:12px}@media(max-width:900px){.span8,.span6,.span4{grid-column:span 12}.metrics{grid-template-columns:repeat(2,1fr)}}@media(max-width:560px){header{align-items:flex-start;flex-direction:column}.status{justify-content:flex-start}.command{grid-template-columns:1fr 1fr}.command textarea{grid-column:1/-1}.metrics{grid-template-columns:1fr 1fr}main{padding:8px}.card{padding:10px}}
</style>
</head>
<body>
<header><div><div class="brand">BOXBRAIN ONE</div><div class="sub">Universal Control Console</div></div><div class="status"><span id="apiPill" class="pill">API: checking</span><span id="authPill" class="pill">AUTH: unknown</span><span id="stopPill" class="pill">E-STOP: unknown</span></div></header>
<main>
<section class="card span12"><h2>Access</h2><div class="token"><input id="token" type="password" autocomplete="off" placeholder="BoxBrain API token (stored only for this browser session)"/><button onclick="saveToken()">Use token</button></div><div class="meta" style="margin-top:7px">Console shell is public HTML; protected API data/actions still require X-BoxBrain-Token when enabled.</div></section>
<section class="card span12"><h2>Command Intake</h2><div class="command"><textarea id="command" placeholder="BoxBrain One… describe the task or status request"></textarea><button class="primary" onclick="submitCommand('chat')">Send</button><button onclick="voiceCommand()">🎙 Voice</button></div><div id="commandResult" class="meta" style="margin-top:8px"></div></section>
<section class="card span12"><h2>System Overview</h2><div class="metrics"><div class="metric"><b id="mTargets">—</b><small>remote targets</small></div><div class="metric"><b id="mMachines">—</b><small>fleet machines</small></div><div class="metric"><b id="mProjects">—</b><small>projects</small></div><div class="metric"><b id="mTasks">—</b><small>open agent tasks</small></div></div></section>
<section class="card span6"><h2>Connections / Remote Targets</h2><div id="remoteTargets" class="list"><div class="meta">Loading…</div></div></section>
<section class="card span6"><h2>Fleet / Logged Machines</h2><div id="fleet" class="list"><div class="meta">Loading…</div></div></section>
<section class="card span4"><h2>Edge Agents</h2><div id="edgeAgents" class="list"></div></section>
<section class="card span4"><h2>Agents & Runtime</h2><div id="agents" class="list"></div></section>
<section class="card span4"><h2>Tools / Plugins</h2><div id="plugins" class="list"></div></section>
<section class="card span6"><h2>Projects</h2><div id="projects" class="list"></div></section>
<section class="card span6"><h2>Recent Processing Runs</h2><div id="runs" class="list"></div></section>
<section class="card span12"><h2>Audit / Connection Log</h2><div id="events" class="console">Loading audit events…</div></section>
<section class="card span12"><h2>Safety</h2><div class="row"><div><b>Persistent emergency stop</b><div class="meta">Blocks remote sessions and Sandbox launch when engaged.</div></div><div class="actions"><button class="danger" onclick="engageStop()">ENGAGE STOP</button><button onclick="resetStop()">Reset (requires RESET)</button></div></div></section>
</main><footer>BoxBrain One • authenticated control-plane console • responsive browser UI</footer>
<script>
const $=id=>document.getElementById(id);let state={token:sessionStorage.getItem('boxbrain-token')||''};$('token').value=state.token;
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function authHeaders(json=false){const h={};if(state.token)h['X-BoxBrain-Token']=state.token;if(json)h['Content-Type']='application/json';return h}
async function api(path,opts={}){opts.headers={...authHeaders(!!opts.body),...(opts.headers||{})};const r=await fetch('/api/v1'+path,opts);if(!r.ok){const t=await r.text();throw new Error(r.status+' '+t)}if(r.status===204)return null;return r.json()}
function saveToken(){state.token=$('token').value.trim();if(state.token)sessionStorage.setItem('boxbrain-token',state.token);else sessionStorage.removeItem('boxbrain-token');refresh()}
function pill(id,text,kind=''){const el=$(id);el.textContent=text;el.className='pill '+kind}
function item(title,meta='',actions=''){return `<div class="item"><div class="row"><b>${esc(title)}</b></div><div class="meta">${esc(meta)}</div>${actions?`<div class="actions">${actions}</div>`:''}</div>`}
async function refresh(){
 try{const h=await api('/health');pill('apiPill','API: '+h.status,'ok');pill('authPill','AUTH: '+(h.authentication_required?'token':'open'),h.authentication_required?'warn':'ok')}catch(e){pill('apiPill','API: offline','bad');return}
 const calls=await Promise.allSettled([api('/remote-targets'),api('/fleet'),api('/edge-agents'),api('/agents'),api('/agents/runtime'),api('/plugins'),api('/projects'),api('/agent-dashboard'),api('/processing/runs?limit=20'),api('/events?limit=60'),api('/safety/emergency-stop')]);
 const val=i=>calls[i].status==='fulfilled'?calls[i].value:null;
 const rem=val(0)||[];$('mTargets').textContent=rem.length;$('remoteTargets').innerHTML=rem.length?rem.map(t=>item(`${t.name} • ${t.status}`,`${t.transport.toUpperCase()} ${t.host}:${t.port} • ${t.credential_mode||''} • checked ${t.last_checked_at||'never'}`,`<button onclick="probe('${t.id}')">Probe</button><button onclick="openSession('${t.id}')">Open session</button>`)).join(''):'<div class="meta">No registered remote targets.</div>';
 const fleet=val(1);const machines=fleet?.machines||fleet?.items||[];$('mMachines').textContent=machines.length;$('fleet').innerHTML=machines.length?machines.map(m=>item(m.name||m.machine_identity,`${m.kind||''} • ${m.status||m.state||'registered'} • ${m.machine_identity||''}`)).join(''):'<div class="meta">No logged fleet machines.</div>';
 const edge=val(2)||[];$('edgeAgents').innerHTML=edge.length?edge.map(a=>item(`${a.name} • ${a.connected?'connected':'offline'}`,`${a.transport} • ${a.mode} • ${a.hostname||'hostname unknown'} • targets ${a.target_count}`)).join(''):'<div class="meta">No edge agents.</div>';
 const agents=val(3)||[],rt=val(4);$('agents').innerHTML=(rt?item(`Model runtime • ${rt.ready||rt.model_ready?'ready':'not ready'}`,`${rt.model||''}`):'')+agents.slice(0,12).map(a=>item(a.name,`${a.id} • ${a.execution_mode} • ${a.enabled?'enabled':'disabled'}`)).join('');
 const plugins=val(5)||[];$('plugins').innerHTML=plugins.length?plugins.map(p=>item(p.name||p.id,`${p.id||''} • ${p.status||p.mode||'discovered'}`)).join(''):'<div class="meta">No discovered plugins.</div>';
 const projects=val(6)||[];$('mProjects').textContent=projects.length;$('projects').innerHTML=projects.length?projects.map(p=>item(p.name,`${p.open_task_count} open tasks • ${p.memory_count} memory items • last ${p.last_activity_at}`)).join(''):'<div class="meta">No projects.</div>';
 const dash=val(7);$('mTasks').textContent=dash?.open_task_count??'—';
 const runs=val(8)||[];$('runs').innerHTML=runs.length?runs.map(r=>item(`${r.project} • ${r.status}`,`${r.intent} • ${r.source} • ${r.created_at}`)).join(''):'<div class="meta">No processing runs.</div>';
 const ev=val(9)||[];$('events').innerHTML=ev.length?ev.map(e=>`<div class="event"><span class="stamp">#${esc(e.sequence)} ${esc(e.created_at||e.timestamp||'')}</span> ${esc(e.event_type)} — ${esc(e.message)}</div>`).join(''):'No events logged.';
 const stop=val(10);if(stop)pill('stopPill','E-STOP: '+(stop.engaged?'ENGAGED':'clear'),stop.engaged?'bad':'ok');
 const authFailure=calls.some(x=>x.status==='rejected'&&String(x.reason).includes('401'));if(authFailure)pill('authPill','AUTH: token required','warn');
}
async function probe(id){try{await api(`/remote-targets/${id}/probe`,{method:'POST'});await refresh()}catch(e){alert('Probe failed: '+e.message)}}
async function openSession(id){if(!confirm('Open the registered operator-authorized remote session?'))return;try{const r=await api(`/remote-targets/${id}/session`,{method:'POST',body:JSON.stringify({confirmation:'OPEN'})});alert(r.message||'Session opened');await refresh()}catch(e){alert('Session failed: '+e.message)}}
async function submitCommand(source){const content=$('command').value.trim();if(!content)return;try{$('commandResult').textContent='Processing…';const r=await api('/processing/runs',{method:'POST',body:JSON.stringify({content,source,project_hint:'BoxBrain',external_access_allowed:false})});$('commandResult').textContent=`${r.status}: ${r.project} / ${r.intent}`;await refresh()}catch(e){$('commandResult').textContent='Failed: '+e.message}}
function voiceCommand(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){alert('Speech recognition is not available in this browser.');return}const r=new SR();r.lang='en-US';r.interimResults=false;r.onresult=e=>{$('command').value=e.results[0][0].transcript;submitCommand('voice')};r.onerror=e=>alert('Voice error: '+e.error);r.start()}
async function engageStop(){const reason=prompt('Emergency stop reason:');if(!reason)return;try{await api('/safety/emergency-stop/engage',{method:'POST',body:JSON.stringify({reason})});await refresh()}catch(e){alert(e.message)}}
async function resetStop(){const c=prompt('Type RESET to clear the emergency stop:');if(c!=='RESET')return;try{await api('/safety/emergency-stop/reset',{method:'POST',body:JSON.stringify({confirmation:'RESET'})});await refresh()}catch(e){alert(e.message)}}
refresh();setInterval(refresh,10000);
</script>
</body></html>'''
