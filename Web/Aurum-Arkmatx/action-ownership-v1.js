/* AURUM_ACTION_OWNERSHIP_V1_6_CANONICAL
 * AURUM_ACTION_OWNERSHIP_V1_1_CANONICAL compatibility marker.
 * Canonical website owner: FormatX66/ClusterSites.
 * Separates confirmed human-only work from Aurum/system work using structured evidence.
 * Uses timestamps to resolve newer transport evidence and now refuses stale voice/action
 * mirrors as a source of human assignments.
 * Unknown or unavailable evidence never creates a human task.
 * Unknown evidence never becomes your task.
 */
(()=>{
'use strict';
if(window.__aurumActionOwnershipV16)return;
window.__aurumActionOwnershipV16=true;
const HOSTED='/aurum/voice-status.json';
const STATIC='https://raw.githubusercontent.com/FormatX66/BoxBrain/main/Web/Aurum-Arkmatx/voice-status.json';
const NATIVE='https://api.github.com/repos/FormatX66/BoxBrain/contents/Projects/Codelation/autobuild/native_chain_state.json?ref=aurum%2Ftrunk-v0.01';
const REFRESH=5*60*1000;
const VOICE_MAX_AGE=6*60*60*1000;
const state={voice:null,voiceFresh:false,native:null,route:window.__aurumControlRouteState||null,seed:window.__aurumSeedDeliveryState||null,reach:window.__aurumPi4ReachabilityState||null,voiceSource:'unknown',updated:0,lastRender:''};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const words=v=>String(v??'unknown').replace(/[_-]+/g,' ').replace(/\s+/g,' ').trim();
function decode(v){const raw=atob(String(v||'').replace(/\s+/g,''));try{return decodeURIComponent([...raw].map(c=>'%'+c.charCodeAt(0).toString(16).padStart(2,'0')).join(''))}catch{return raw}}
function isHumanAction(text){const t=String(text||'').trim();if(!t||/^none\b/i.test(t)||/unknown|unavailable|checking|could not|waiting for evidence|stale/i.test(t))return false;return true}
function ageText(ms){if(!Number.isFinite(Number(ms)))return'timestamp unknown';const min=Math.max(0,Math.floor(Number(ms||0)/60000));if(min<=0)return'beyond its grace window';if(min<60)return`${min} min`;const h=Math.floor(min/60),rest=min%60;return rest?`${h}h ${rest}m`:`${h}h`}
function time(v){return Date.parse(v||'')||0}
function voiceFreshness(p){const t=time(p?.generated_at_utc);if(!t)return{fresh:false,ageMs:Infinity};const ageMs=Date.now()-t;return{fresh:ageMs>=-5*60*1000&&ageMs<=VOICE_MAX_AGE,ageMs}}
function combinedPiBoundary(s,r){return s?.phase==='failed'&&r?.phase==='failed'&&r?.result?.state==='BOXBRAIN_SSH_UNREACHABLE'}
function seedAllRoutes(s){if(s?.reachabilityScope==='all-approved-routes')return true;const reason=String(s?.receipt?.data?.reason||'').toLowerCase();return /not reachable|unreachable/.test(reason)&&/(^|\W)ap(\W|$)/.test(reason)&&/usb-c/.test(reason)&&/(^|\W)lan(\W|$)/.test(reason)}
function routeAttempts(r){const a=r?.result?.ssh_attempts;if(!Array.isArray(a)||!a.length)return'candidate addresses not recorded';return a.map(x=>`${x.address||'unknown'} (${x.host_key||'host key unknown'})`).join(', ')}
function reachAddresses(q){return(q?.tcp22Addresses||[]).join(', ')||(q?.pingAddresses||[]).join(', ')||'an address not recorded'}
function reachSupersedesSeed(q,s){const qms=Number(q?.observedMs||0),sms=time(s?.receipt?.observed_at);return Boolean(q?.phase==='route-found'&&qms&&sms&&qms>sms)}
function routeAfterReach(r,q){const rms=time(r?.result?.observed_at),qms=Number(q?.observedMs||0);return Boolean(rms&&qms&&rms>qms)}
function systemItems(){
 const out=[],v=state.voice,n=state.native,r=state.route,s=state.seed,q=state.reach;
 if(v&&!state.voiceFresh){out.push({title:'Voice/action evidence freshness',detail:`The ${state.voiceSource} mirror is readable but older than the six-hour operator-action window. Refresh voice-status truth before using it for Your Actions. Stale evidence remains Aurum/system work and cannot assign a human task.`})}
 if(state.voiceFresh&&(v?.overall?.state==='awaiting-boot-proof'||v?.live_evidence?.pc_seed_with_human_traits?.state==='pending'))out.push({title:'Human-capability boot proof',detail:'Build and verify a fresh PC seed containing all seven everyday capabilities, then boot a generation that already contains them. Fresh voice evidence says this remains automated build work.'});
 if(n?.blocked_reason==='external-prerequisite-blocked'){const gen=Number(n?.completed_generations||0),reason=words(n?.external_evidence?.reason||'external prerequisite'),local=/candidate-verified/i.test(String(n?.blocked_output||''))?' Local candidate is already verified.':'';out.push({title:`Native self-build generation ${gen}`,detail:`Refresh the ${reason} evidence so the verified native frontier can continue.${local}`})}else if(n?.failed_attempt)out.push({title:'Native self-build recovery',detail:'Diagnose the current failed native attempt and restore a verified checkpoint before promotion.'});
 const combined=combinedPiBoundary(s,r),newerReach=reachSupersedesSeed(q,s);
 if(newerReach&&r?.phase==='failed'&&r?.result?.state==='BOXBRAIN_SSH_UNREACHABLE'){const later=routeAfterReach(r,q);out.push({title:'BBPI4 LAN route rediscovered; SSH path unstable',detail:`A newer dynamic diagnostic superseded the older seed receipt as current transport context: ${reachAddresses(q)} answered ${q.tcp22Addresses?.length?'ping/TCP22':'ping'} at ${q.result?.observed_at||'the recorded time'}. ${later?'A still-newer':'The'} end-to-end route proof then could not obtain an SSH host key on ${routeAttempts(r)}. Treat this as layered/intermittent reachability: LAN transport has existed, while SSH identity/service stability and Hopper access remain unresolved. Do not infer that the Pi is powered off or create a human task from this evidence.`})}
 else if(newerReach&&s?.phase==='failed'){out.push({title:'BBPI4 seed delivery after route rediscovery',detail:`The latest seed receipt failed before the newer dynamic diagnostic found a BBPI4 route at ${reachAddresses(q)}. Retry or diagnose seed reconciliation using the rediscovered transport context; the old all-routes-unreachable statement is no longer the newest reachability evidence. This remains Aurum/system work.`})}
 else if(combined&&seedAllRoutes(s)){out.push({title:'BBPI4 unreachable across approved routes',detail:`Seed delivery reports BBPI4 unreachable over AP, USB-C, and LAN SSH, while the read-only Hopper route proof failed before SSH on ${routeAttempts(r)}. No newer dynamic route discovery currently supersedes that boundary. Root cause remains unproven, and human action requires separate physical evidence.`})}
 else if(combined){const d=s?.receipt?.data||{};out.push({title:'BBPI4 delivery / reachability boundary',detail:`Latest Pi4 seed delivery failed (${d.reason||'seed verification failure'}) and the separate read-only route proof could not obtain an SSH host key from any BBPI4 candidate address. Inspect Pi reachability, USB-C SSH transport, runner routing, and seed reconciliation logs before escalating. This is system evidence, not a human task.`})}
 else if(s?.phase==='failed'){const d=s?.receipt?.data||{};out.push({title:'BBPI4 seed delivery',detail:`Latest physical seed delivery failed: ${d.reason||words(s?.receipt?.state||'unresolved seed failure')}. Transport: ${d.transport||'unknown'}. Diagnose reconciliation/verification in the system before requesting physical action.`})}
 else if(s?.phase==='unknown')out.push({title:'BBPI4 seed-delivery evidence',detail:'The latest Pi4 seed-delivery receipt is unreadable or unavailable. Restore the evidence path; unknown evidence does not become a human task.'});
 if(!combined&&!newerReach){if(r?.phase==='stalled')out.push({title:'BoxBrain → Hopper route dispatch stall',detail:`The read-only route request has waited ${ageText(r?.requestAgeMs)} without a recorded result, past twice the 10-minute route-test window. Inspect the self-hosted runner / workflow dispatch; do not assign a physical task unless separate verified evidence names one.`});else if(r?.phase==='pending')out.push({title:'BoxBrain → Hopper control-route proof',detail:'A read-only GitHub → main PC → BBPI4 → Hopper proof is waiting for a recorded result inside its dispatch grace window. This is Aurum/system work.'});else if(r?.phase==='failed')out.push({title:'BoxBrain → Hopper route diagnosis',detail:`Latest read-only route proof returned ${words(r?.result?.state||'an unresolved state')}. Diagnose the first failed route boundary in the build/control system; do not assign a physical task unless separate verified evidence names one.`});else if(r?.phase==='unknown')out.push({title:'BoxBrain → Hopper route evidence',detail:'The control-route evidence is currently unreadable. Restore/read the evidence path; unknown evidence does not become a human task.'})}
 if(q?.phase==='failed'&&!combined)out.push({title:'BBPI4 dynamic reachability',detail:'The newest dynamic Pi4 diagnostic found no usable route. Diagnose naming, adapter, route, neighbor, ping, and TCP/22 evidence in the system before asking for physical intervention.'});
 return out;
}
function render(){
 const gate=document.querySelector('#humanGate');if(!gate)return;
 const rawAction=state.voice?.overall?.human_action||'Human-action evidence is unavailable.';
 const human=state.voiceFresh&&isHumanAction(rawAction);
 const action=state.voiceFresh?rawAction:(state.voice?'Human-action evidence is stale; no human task is inferred until the mirror is refreshed.':'Human-action evidence is unavailable; no human task is inferred.');
 const work=systemItems();
 const fingerprint=JSON.stringify([human,action,work,state.voiceFresh,state.voiceSource,state.route?.phase,state.route?.result?.observed_at,state.seed?.phase,state.seed?.receipt?.observed_at,state.reach?.phase,state.reach?.observedMs]);
 if(fingerprint===state.lastRender)return;state.lastRender=fingerprint;
 gate.className=`gate ${human?'':'ok'}`;gate.dataset.actionContract='verified';gate.dataset.humanActionCount=human?'1':'0';gate.dataset.systemWorkCount=String(work.length);gate.dataset.voiceEvidenceFresh=String(state.voiceFresh);
 gate.innerHTML=`<b>${human?'Human-only action confirmed.':state.voiceFresh?'No action needed from you right now.':'No confirmed action from you; action evidence is stale or unavailable.'}</b><p>${esc(action)}</p><div class="ao-grid"><div class="ao-box ${human?'human':'clear'}"><span class="ao-label">YOU</span><strong>${human?'1 confirmed':'0 confirmed'}</strong><small>${human?esc(rawAction):state.voiceFresh?'Nothing is currently assigned to you.':'Stale/unknown voice evidence is blocked from assigning you work.'}</small></div><div class="ao-box system"><span class="ao-label">AURUM</span><strong>${work.length} system ${work.length===1?'item':'items'}</strong>${work.length?`<ul>${work.map(x=>`<li><b>${esc(x.title)}</b><br>${esc(x.detail)}</li>`).join('')}</ul>`:'<small>No structured system work found in these evidence sources.</small>'}</div></div><div class="ao-source">Action ownership uses ${esc(state.voiceSource)} voice evidence, native-chain state, seed receipts, dynamic BBPI4 reachability diagnostics, and end-to-end Hopper route proof. Voice/action evidence must be fresh (≤6h) before it can create a human assignment. Newer evidence may refine an older boundary without inventing a root cause or a human task.</div>`;
 if(!document.querySelector('#aoStyle')){const st=document.createElement('style');st.id='aoStyle';st.textContent='.ao-grid{display:grid;grid-template-columns:.75fr 1.25fr;gap:8px;margin-top:10px}.ao-box{border:1px solid #2b3140;border-radius:12px;background:#10141c;padding:10px}.ao-box strong{display:block;font-size:12px;margin:3px 0 5px}.ao-box small,.ao-box li{font-size:10px;line-height:1.45;color:#8f9bad}.ao-box ul{margin:6px 0 0;padding-left:17px}.ao-box li{margin:5px 0}.ao-label{font-size:8.5px;font-weight:850;letter-spacing:.1em;color:#778399}.ao-box.clear{border-color:#244735}.ao-box.clear strong{color:#8ce7b2}.ao-box.human{border-color:#654f1d;background:#1a160d}.ao-box.human strong{color:#f0c76a}.ao-box.system{border-color:#343164}.ao-box.system strong{color:#bbb6ff}.ao-source{margin-top:8px;font-size:9px;line-height:1.4;color:#6f7c90}@media(max-width:700px){.ao-grid{grid-template-columns:1fr}}';document.head.appendChild(st)}
}
async function voice(){
 let stale=null;
 for(const[url,label]of[[HOSTED,'hosted'],[STATIC,'repository fallback']]){
  try{
   const r=await fetch(`${url}${url.includes('?')?'&':'?'}t=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw new Error(String(r.status));
   const p=await r.json();if(p?.schema!=='aurum-voice-status-v1'||!Array.isArray(p?.human_capabilities))throw new Error('schema');
   const meta=voiceFreshness(p);
   if(meta.fresh){state.voice=p;state.voiceFresh=true;state.voiceSource=label;return}
   if(!stale)stale={p,label,ageMs:meta.ageMs};
  }catch(_){ }
 }
 if(stale){state.voice=stale.p;state.voiceFresh=false;state.voiceSource=`${stale.label} (stale ${ageText(stale.ageMs)})`;return}
 state.voice=null;state.voiceFresh=false;state.voiceSource='unavailable';
}
async function native(){try{const r=await fetch(NATIVE,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}});if(!r.ok)throw new Error(String(r.status));const e=await r.json(),n=JSON.parse(decode(e.content)),schema=n?.schema||n?._checkpoint?.schema;if(schema!=='aurum-native-chain-resume-v1')throw new Error('schema');state.native=n}catch(_){state.native=null}}
async function refresh(){await Promise.all([voice(),native()]);state.route=window.__aurumControlRouteState||state.route;state.seed=window.__aurumSeedDeliveryState||state.seed;state.reach=window.__aurumPi4ReachabilityState||state.reach;state.updated=Date.now();state.lastRender='';render()}
window.addEventListener('aurum-control-route-state',e=>{state.route=e.detail||null;state.lastRender='';render()});
window.addEventListener('aurum-seed-delivery-state',e=>{state.seed=e.detail||null;state.lastRender='';render()});
window.addEventListener('aurum-pi4-reachability-state',e=>{state.reach=e.detail||null;state.lastRender='';render()});
refresh();setInterval(refresh,REFRESH);setInterval(render,3000);
})();