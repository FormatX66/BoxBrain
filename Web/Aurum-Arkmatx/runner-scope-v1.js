/* AURUM_RUNNER_SCOPE_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Correlates a fresh PC-01 self-hosted Windows proof with a queued Hopper Echo
 * self-hosted Linux proof so the Command Center can narrow the failed boundary
 * without inventing a root cause or a human task.
 */
(()=>{'use strict';if(window.__aurumRunnerScopeV1)return;window.__aurumRunnerScopeV1=true;
const REPO='FormatX66/BoxBrain';
const RESULTS=`https://api.github.com/repos/${REPO}/contents/Projects/AurumBridge/results?ref=main`;
const REFRESH=60*1000,PEER_FRESH=2*60*60*1000;
let peer={fresh:false,runner:'',observedAt:0,state:'',ageMs:null};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function json(url){const r=await fetch(url,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}});if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()}
async function rawJson(url){const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()}
function receiptRank(name){const m=String(name||'').match(/^pc01-flash-(\d+)-attempt-(\d+)\.json$/i);return m?Number(m[1])*100+Number(m[2]):0}
async function latestPcReceipt(){const list=await json(RESULTS);const files=Array.isArray(list)?list.filter(x=>x.type==='file'&&receiptRank(x.name)).sort((a,b)=>receiptRank(b.name)-receiptRank(a.name)):[];if(!files.length)return null;return rawJson(files[0].download_url)}
function ageText(v){const m=Math.max(0,Math.floor(Number(v||0)/60000));if(m<60)return`${m} min`;const h=Math.floor(m/60),r=m%60;return r?`${h}h ${r}m`:`${h}h`}
function hopperQueued(){const s=window.__aurumWorkflowFailsafeState;return Boolean(s?.stalled?.some(x=>x?.key==='aurum-hopper-echo-proof.yml@main'&&x?.kind==='queued'&&x?.runnerClass==='self-hosted Linux'))}
function render(){const card=document.querySelector('[data-id="failsafe"]');if(!card)return;const detail=card.querySelector('.wf-detail');if(!detail)return;let note=detail.querySelector('.runner-scope-note');if(!note){note=document.createElement('div');note.className='runner-scope-note';note.style.cssText='margin-top:10px;padding-top:9px;border-top:1px solid #252b39;color:#8f9bad';detail.appendChild(note)}
 if(hopperQueued()&&peer.fresh){note.innerHTML=`<b>Runner scope:</b> Recent PC-01 self-hosted Windows proof executed on ${esc(peer.runner)} ${esc(ageText(peer.ageMs))} ago while Hopper Echo still lacks self-hosted Linux scheduler placement. This rules out a global self-hosted runner outage; it does not prove whether the Linux runner is offline, busy, mislabeled, or absent.`;card.dataset.runnerScope='linux-placement-only'}
 else if(hopperQueued()){note.innerHTML='<b>Runner scope:</b> Hopper Echo still lacks self-hosted Linux scheduler placement. No fresh independent peer-runner proof is available to narrow the boundary further.';card.dataset.runnerScope='unconstrained'}
 else{note.innerHTML='<b>Runner scope:</b> No current queued self-hosted Linux proof requires runner-boundary narrowing.';card.dataset.runnerScope='not-applicable'}
 window.__aurumRunnerScopeState={...peer,hopperQueued:hopperQueued(),humanActionInference:false};window.dispatchEvent(new CustomEvent('aurum-runner-scope-state',{detail:{...window.__aurumRunnerScopeState}}))}
async function refresh(){try{const p=await latestPcReceipt();const observed=Date.parse(p?.observed_at||'');const age=Number.isFinite(observed)?Math.max(0,Date.now()-observed):null;const stable=['FLASH_OK','ALREADY_COMPLETE'].includes(String(p?.state||''));peer={fresh:Boolean(stable&&age!==null&&age<=PEER_FRESH&&p?.runner_name),runner:String(p?.runner_name||''),observedAt:Number.isFinite(observed)?observed:0,state:String(p?.state||''),ageMs:age}}catch{peer={fresh:false,runner:'',observedAt:0,state:'',ageMs:null}}render()}
window.addEventListener('aurum-workflow-failsafe-state',()=>setTimeout(render,0));
function boot(){if(!document.querySelector('#systems')){setTimeout(boot,250);return}refresh();setInterval(refresh,REFRESH)}boot();
})();
