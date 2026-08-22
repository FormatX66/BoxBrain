/* AURUM_ACTION_OWNERSHIP_V1_2_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Separates confirmed human-only work from Aurum/system work using structured evidence.
 * Includes the read-only BoxBrain -> Hopper route frontier when that proof is pending, stalled, or failed.
 * Unknown or unavailable evidence never creates a human task.
 */
(()=>{'use strict';if(window.__aurumActionOwnershipV12)return;window.__aurumActionOwnershipV12=true;
const HOSTED='/aurum/voice-status.json';
const STATIC='https://raw.githubusercontent.com/FormatX66/BoxBrain/main/Web/Aurum-Arkmatx/voice-status.json';
const NATIVE='https://api.github.com/repos/FormatX66/BoxBrain/contents/Projects/Codelation/autobuild/native_chain_state.json?ref=aurum%2Ftrunk-v0.01';
const REFRESH=5*60*1000;
const state={voice:null,native:null,route:window.__aurumControlRouteState||null,voiceSource:'unknown',updated:0,lastRender:''};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const words=v=>String(v??'unknown').replace(/[_-]+/g,' ').replace(/\s+/g,' ').trim();
function decode(v){const raw=atob(String(v||'').replace(/\s+/g,''));try{return decodeURIComponent([...raw].map(c=>'%'+c.charCodeAt(0).toString(16).padStart(2,'0')).join(''))}catch{return raw}}
function isHumanAction(text){const t=String(text||'').trim();if(!t)return false;if(/^none\b/i.test(t))return false;if(/unknown|unavailable|checking|could not|waiting for evidence/i.test(t))return false;return true}
function ageText(ms){const min=Math.floor(Number(ms||0)/60000);if(min<=0)return 'beyond its grace window';if(min<60)return `${min} min`;const h=Math.floor(min/60),rest=min%60;return rest?`${h}h ${rest}m`:`${h}h`}
function systemItems(){const out=[];const v=state.voice,n=state.native,r=state.route;
  if(v?.overall?.state==='awaiting-boot-proof'||v?.live_evidence?.pc_seed_with_human_traits?.state==='pending'){
    out.push({title:'Human-capability boot proof',detail:'Build and verify a fresh PC seed containing all seven everyday capabilities, then boot a generation that already contains them. Current mirror says this remains automated build work.'});
  }
  if(n?.blocked_reason==='external-prerequisite-blocked'){
    const gen=Number(n?.completed_generations||0),reason=words(n?.external_evidence?.reason||'external prerequisite');
    const local=/candidate-verified/i.test(String(n?.blocked_output||''))?' Local candidate is already verified.':'';
    out.push({title:`Native self-build generation ${gen}`,detail:`Refresh the ${reason} evidence so the verified native frontier can continue.${local}`});
  }else if(n?.failed_attempt){
    out.push({title:'Native self-build recovery',detail:'Diagnose the current failed native attempt and restore a verified checkpoint before promotion.'});
  }
  if(r?.phase==='stalled'){
    out.push({title:'BoxBrain → Hopper route dispatch stall',detail:`The read-only route request has waited ${ageText(r?.requestAgeMs)} without a recorded result, past twice the 10-minute route-test window. Inspect the self-hosted aurum-elevated runner / workflow dispatch and preserve this as Aurum/system work; do not assign a physical task unless separate verified evidence names one.`});
  }else if(r?.phase==='pending'){
    out.push({title:'BoxBrain → Hopper control-route proof',detail:'A read-only GitHub → main PC → BBPI4 → Hopper proof was requested and is waiting for a recorded result inside its dispatch grace window. This is Aurum/system work, not a human action.'});
  }else if(r?.phase==='failed'){
    out.push({title:'BoxBrain → Hopper route diagnosis',detail:`The latest read-only route proof returned ${words(r?.result?.state||'an unresolved state')}. Diagnose the route in the build/control system; do not assign a physical task unless separate verified evidence names one.`});
  }else if(r?.phase==='unknown'){
    out.push({title:'BoxBrain → Hopper route evidence',detail:'The control-route evidence is currently unreadable. Restore/read the evidence path; unknown evidence does not become a human task.'});
  }
  return out;
}
function render(){const gate=document.querySelector('#humanGate');if(!gate)return;const action=state.voice?.overall?.human_action||'Human-action evidence is unavailable.';const human=isHumanAction(action);const work=systemItems();
  const fingerprint=JSON.stringify([human,action,work,state.voiceSource,state.route?.phase]);if(fingerprint===state.lastRender)return;state.lastRender=fingerprint;
  gate.className=`gate ${human?'':'ok'}`;
  gate.dataset.actionContract='verified';gate.dataset.humanActionCount=human?'1':'0';gate.dataset.systemWorkCount=String(work.length);
  gate.innerHTML=`<b>${human?'Human-only action confirmed.':'No action needed from Bruce right now.'}</b><p>${esc(action)}</p><div class="ao-grid"><div class="ao-box ${human?'human':'clear'}"><span class="ao-label">YOU</span><strong>${human?'1 confirmed':'0 confirmed'}</strong><small>${human?esc(action):'Nothing is currently assigned to you.'}</small></div><div class="ao-box system"><span class="ao-label">AURUM</span><strong>${work.length} system ${work.length===1?'item':'items'}</strong>${work.length?`<ul>${work.map(x=>`<li><b>${esc(x.title)}</b><br>${esc(x.detail)}</li>`).join('')}</ul>`:'<small>No structured system work found in these evidence sources.</small>'}</div></div><div class="ao-source">Action ownership uses ${esc(state.voiceSource)} voice evidence, the verified native-chain checkpoint, and the read-only BoxBrain → Hopper route state including aged-request stall classification. Unknown evidence never becomes your task.</div>`;
  const old=document.querySelector('#aoStyle');if(!old){const st=document.createElement('style');st.id='aoStyle';st.textContent='.ao-grid{display:grid;grid-template-columns:.75fr 1.25fr;gap:8px;margin-top:10px}.ao-box{border:1px solid #2b3140;border-radius:12px;background:#10141c;padding:10px}.ao-box strong{display:block;font-size:12px;margin:3px 0 5px}.ao-box small,.ao-box li{font-size:10px;line-height:1.45;color:#8f9bad}.ao-box ul{margin:6px 0 0;padding-left:17px}.ao-box li{margin:5px 0}.ao-label{font-size:8.5px;font-weight:850;letter-spacing:.1em;color:#778399}.ao-box.clear{border-color:#244735}.ao-box.clear strong{color:#8ce7b2}.ao-box.human{border-color:#654f1d;background:#1a160d}.ao-box.human strong{color:#f0c76a}.ao-box.system{border-color:#343164}.ao-box.system strong{color:#bbb6ff}.ao-source{margin-top:8px;font-size:9px;line-height:1.4;color:#6f7c90}@media(max-width:700px){.ao-grid{grid-template-columns:1fr}}';document.head.appendChild(st)}
}
async function voice(){for(const [url,label] of [[HOSTED,'hosted'],[STATIC,'repository fallback']]){try{const r=await fetch(`${url}${url.includes('?')?'&':'?'}t=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw new Error(String(r.status));const p=await r.json();if(p?.schema!=='aurum-voice-status-v1')throw new Error('schema');state.voice=p;state.voiceSource=label;return}catch(_){}}state.voice=null;state.voiceSource='unavailable'}
async function native(){try{const r=await fetch(NATIVE,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}});if(!r.ok)throw new Error(String(r.status));const e=await r.json();const n=JSON.parse(decode(e.content));const schema=n?.schema||n?._checkpoint?.schema;if(schema!=='aurum-native-chain-resume-v1')throw new Error('schema');state.native=n}catch(_){state.native=null}}
async function refresh(){await Promise.all([voice(),native()]);state.route=window.__aurumControlRouteState||state.route;state.updated=Date.now();state.lastRender='';render()}
window.addEventListener('aurum-control-route-state',e=>{state.route=e.detail||null;state.lastRender='';render()});
refresh();setInterval(refresh,REFRESH);setInterval(render,3000);
})();
