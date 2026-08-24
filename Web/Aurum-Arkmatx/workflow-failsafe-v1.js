/* AURUM_WORKFLOW_FAILSAFE_V1_CANONICAL
 * AURUM_WORKFLOW_FAILSAFE_V1_1_CANONICAL
 * AURUM_WORKFLOW_FAILSAFE_V1_2_CANONICAL
 * AURUM_WORKFLOW_FAILSAFE_V1_3_CANONICAL
 * AURUM_WORKFLOW_FAILSAFE_V1_4_CANONICAL
 * AURUM_WORKFLOW_FAILSAFE_V1_5_CANONICAL
 * AURUM_WORKFLOW_FAILSAFE_V1_6_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Surfaces durable Aurum Actions readback without turning workflow failures into human tasks.
 * Recent completed failures are enriched with failed job/step names from GitHub Actions.
 * Hopper Echo physical proof is a required evidence lane, distinct from ordinary workflow health.
 * Queued self-hosted proof reports scheduler placement without guessing the root cause.
 * A terminal cancellation clears the queued-placement diagnosis but does not count as physical proof.
 * Failsafe receipt discovery accepts both legacy RUNID.json and rerun-safe RUNID-attempt-N.json names.
 */
(()=>{
'use strict';
if(window.__aurumWorkflowFailsafeV1)return;
window.__aurumWorkflowFailsafeV1=true;
const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const REPO='FormatX66/BoxBrain';
const RESULTS=`https://api.github.com/repos/${REPO}/contents/Projects/AurumBridge/results?ref=main`;
const API=`https://api.github.com/repos/${REPO}`;
const REFRESH=60*1000,QUEUE_GRACE=15*60*1000,RUN_GRACE=60*60*1000,SNAPSHOT_STALE=90*60*1000;
const CORE=[
 ['aurum-continuous-controller.yml@main','Continuous controller'],
 ['aurum-autobuild.yml@aurum/trunk-v0.01','Native autobuild · trunk'],
 ['aurum-autobuild.yml@main','Native autobuild · main'],
 ['aurum-event-bridge.yml@main','Event bridge'],
 ['aurum-external-evidence-recovery.yml@aurum/trunk-v0.01','External evidence recovery'],
 ['aurum-dual-seed-lanes.yml@main','Dual seed lanes'],
 ['aurum-pc01-flash-authorized.yml@main','PC-01 flash'],
 ['aurum-boxbrain-hopper-route-test.yml@main','BoxBrain → Hopper route'],
 ['aurum-hopper-echo-proof.yml@main','Hopper Echo physical proof','self-hosted Linux',true],
 ['ci.yml@main','Repository CI']
];
let state={phase:'checking',observedAt:0,ageMs:null,active:[],stalled:[],unresolved:[],failures:[],lanes:[],readbackFiles:{active:null,history:null},liveConfirmed:false,humanActionInference:false,detail:'Checking workflow failsafe evidence…'};
const style=document.createElement('style');
style.textContent='.workflow-failsafe-card .wf-detail{display:none;margin-top:10px;padding-top:10px;border-top:1px solid #252b39;font-size:10px;line-height:1.5;color:#8f9bad}.workflow-failsafe-card[aria-expanded="true"] .wf-detail{display:block}.workflow-failsafe-card .wf-detail b{color:#c9c6ff}.workflow-failsafe-card .wf-grid{display:grid;grid-template-columns:minmax(145px,.8fr) 88px minmax(0,1.3fr);gap:6px;margin-top:8px}.workflow-failsafe-card .wf-grid>span{padding:5px 6px;border-bottom:1px solid #232936}.workflow-failsafe-card .wf-hint{margin-top:8px;font-size:8.5px;color:#747f92;font-weight:750}@media(max-width:700px){.workflow-failsafe-card .wf-grid{grid-template-columns:1fr}.workflow-failsafe-card .wf-grid>span{border-bottom:0;padding:2px 0}}';
document.head.appendChild(style);
function publish(){window.__aurumWorkflowFailsafeState={...state,humanActionInference:false};window.dispatchEvent(new CustomEvent('aurum-workflow-failsafe-state',{detail:{...window.__aurumWorkflowFailsafeState}}))}
async function json(url){const r=await fetch(url,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}});if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()}
async function rawJson(url){const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()}
function re(s){return String(s).replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}
function receiptRank(name,prefix){const m=String(name||'').match(new RegExp(`^${re(prefix)}-(\\d+)(?:-attempt-(\\d+))?\\.json$`,'i'));return m?{run:Number(m[1]),attempt:Number(m[2]||0)}:null}
async function latest(prefix){const list=await json(RESULTS);const files=Array.isArray(list)?list.map(meta=>({meta,rank:meta?.type==='file'?receiptRank(meta.name,prefix):null})).filter(x=>x.rank).sort((a,b)=>(b.rank.run-a.rank.run)||(b.rank.attempt-a.rank.attempt)):[];if(!files.length)return null;return{meta:files[0].meta,rank:files[0].rank,payload:await rawJson(files[0].meta.download_url)}}
async function liveRun(run){if(!run?.id||!['queued','in_progress','waiting','requested','pending'].includes(String(run.status||'')))return run;try{const live=await json(`${API}/actions/runs/${run.id}`);return{...run,status:live.status||run.status,conclusion:live.conclusion??run.conclusion,created_at:live.created_at||run.created_at,updated_at:live.updated_at||run.updated_at,html_url:live.html_url||run.html_url,live_confirmed:true}}catch{return run}}
async function enrichFailure(run){if(!run?.id||!['failure','timed_out','startup_failure','action_required'].includes(String(run.conclusion||'')))return run;try{const data=await json(`${API}/actions/runs/${run.id}/jobs?per_page=100`),jobs=Array.isArray(data?.jobs)?data.jobs:[];const failedJobs=jobs.filter(j=>['failure','timed_out','startup_failure','action_required'].includes(String(j?.conclusion||'')));const failedSteps=[];for(const job of failedJobs){for(const step of(Array.isArray(job?.steps)?job.steps:[])){if(['failure','timed_out','startup_failure','action_required'].includes(String(step?.conclusion||'')))failedSteps.push({job:job.name||'job',step:step.name||'step'})}}const failureDetail=failedSteps.length?failedSteps.map(x=>`${x.job} → ${x.step}`).join(' · '):failedJobs.length?failedJobs.map(j=>j.name||'failed job').join(' · '):'';return{...run,failed_jobs:failedJobs.map(j=>j.name||'failed job'),failed_steps:failedSteps,failure_detail:failureDetail}}catch{return run}}
function ms(v){const n=Date.parse(v||'');return Number.isFinite(n)?n:0}
function ageText(v){const m=Math.max(0,Math.floor(Number(v||0)/60000));if(m<60)return`${m} min`;const h=Math.floor(m/60),r=m%60;return r?`${h}h ${r}m`:`${h}h`}
function ensure(){const systems=$('#systems');if(!systems)return null;let card=$('[data-id="failsafe"]',systems);if(card)return card;card=document.createElement('article');card.className='system-card workflow-failsafe-card';card.dataset.id='failsafe';card.tabIndex=0;card.setAttribute('role','button');card.setAttribute('aria-expanded','false');card.innerHTML='<div class="card-head"><div class="card-icon">⟲</div><span class="pill running">Running</span></div><h3>Workflow Failsafe</h3><p>Durable readback of Aurum build, controller, recovery, seed, route, hardware-proof, and CI lanes.</p><div class="evidence">Checking failsafe evidence…</div><div class="wf-hint">Tap to expand workflow health →</div><div class="wf-detail"></div>';const toggle=e=>{if(e?.type==='keydown'&&!['Enter',' '].includes(e.key))return;if(e?.type==='keydown')e.preventDefault();card.setAttribute('aria-expanded',String(card.getAttribute('aria-expanded')!=='true'));e?.stopPropagation?.()};card.addEventListener('click',toggle);card.addEventListener('keydown',toggle);systems.appendChild(card);return card}
function statusText(run){if(!run)return'no evidence';if(['queued','waiting','requested','pending'].includes(run.status))return'queued';if(run.status==='in_progress')return'running';return run.conclusion||run.status||'unknown'}
function failureSummary(lane){const d=lane?.run?.failure_detail;return d?`${lane.label} failed at ${d}`:`${lane?.label||'Workflow lane'} latest run failed`}
function queueSummary(lane){if(!lane)return'';return lane.runnerClass?`${lane.label} queued beyond the 15-minute dispatch grace · ${lane.runnerClass} scheduler placement has not occurred · root cause is not yet proven.`:`${lane.label} queued beyond the 15-minute dispatch grace.`}
function unresolvedSummary(lane){if(!lane)return'';return`${lane.label} was cancelled before required physical proof was produced. The old scheduler-placement diagnosis is no longer current; physical proof remains unresolved. Cancellation does not prove why the run ended.`}
function render(){
 const card=ensure();if(!card)return;const pill=$('.pill',card),evidence=$('.evidence',card),detail=$('.wf-detail',card);card.dataset.failsafePhase=state.phase;
 if(state.phase==='checking'){pill.className='pill running';pill.textContent='Running';evidence.textContent='Checking latest durable active/readback evidence…'}
 else if(state.phase==='verified'){pill.className='pill success';pill.textContent='Verified';evidence.textContent=`Workflow failsafe readback is healthy · ${state.lanes.length} core lanes checked · no current stall or unresolved required-proof lane.`}
 else if(state.phase==='running'){pill.className='pill running';pill.textContent=`Running`;evidence.textContent=`${state.active.length} core workflow lane${state.active.length===1?' is':'s are'} executing/queued inside the normal dispatch window.`}
 else if(state.phase==='attention'){
  pill.className='pill failed';pill.textContent='Needs Work';
  if(state.stalled.length)evidence.textContent=state.stalled[0].kind==='queued'?`${queueSummary(state.stalled[0])} Aurum/system attention required.`:`${state.stalled[0].label} running beyond the one-hour execution grace · Aurum/system attention required.`;
  else if(state.unresolved.length)evidence.textContent=`${unresolvedSummary(state.unresolved[0])} Aurum/system attention required; no human action inferred.`;
  else evidence.textContent=`${failureSummary(state.failures[0])} · Aurum/system attention required.`;
 } else {pill.className='pill unknown';pill.textContent='Unknown';evidence.textContent='Workflow failsafe evidence is unavailable or stale · no human action inferred.'}
 const rows=state.lanes.map(x=>`<span><b>${esc(x.label)}</b></span><span>${esc(statusText(x.run))}</span><span>${esc(x.note||'')}</span>`).join('');
 const failureDetail=state.failures.length?state.failures.map(x=>failureSummary(x)).join(' · '):'none';
 const placementDetail=state.stalled.filter(x=>x.kind==='queued'&&x.runnerClass).map(queueSummary).join(' · ')||'none';
 const proofDetail=state.unresolved.length?state.unresolved.map(unresolvedSummary).join(' · '):'none';
 const advancing=state.ageMs!==null&&state.ageMs<=SNAPSHOT_STALE?'durable active/history readback is current; terminal workflow reconciliation is active':'no fresh frontier evidence claimed';
 const needs=state.stalled.length?state.stalled.map(x=>x.kind==='queued'?queueSummary(x):`${x.label} is running beyond the execution grace.`).join(' · '):state.unresolved.length?state.unresolved.map(unresolvedSummary).join(' · '):state.failures.length?state.failures.map(failureSummary).join(' · '):'none';
 detail.innerHTML=`<b>Snapshot observed:</b> ${esc(state.observedAt?new Date(state.observedAt).toLocaleString():'not recorded')}<br><b>Snapshot age:</b> ${esc(state.ageMs===null?'unknown':ageText(state.ageMs))}<br><b>Active readback:</b> ${esc(state.readbackFiles?.active||'not found')}<br><b>Run history:</b> ${esc(state.readbackFiles?.history||'not found')}<br><b>Active core lanes:</b> ${esc(state.active.length)}<br><b>Stalled core lanes:</b> ${esc(state.stalled.length)}<br><b>Unresolved required-proof lanes:</b> ${esc(state.unresolved.length)}<br><b>Recent failed core lanes:</b> ${esc(state.failures.length)}<br><b>Live run confirmation:</b> ${esc(Boolean(state.liveConfirmed))}<br><b>Failure detail:</b> ${esc(failureDetail)}<br><b>Scheduler placement:</b> ${esc(placementDetail)}<br><b>Proof boundary:</b> ${esc(proofDetail)}<div class="wf-grid">${rows||'<span>No core lane evidence loaded.</span>'}</div><br><b>Interpretation:</b> this surface accepts both legacy failsafe receipts and rerun-safe <code>RUNID-attempt-N</code> receipts, chooses the newest run and attempt, live-checks non-completed run IDs before calling them stalled, enriches recent completed failures with failed job/step names, includes Hopper Echo physical proof, and lets live-confirmed terminal state override an older durable snapshot. A queued self-hosted workflow proves only that matching runner placement has not happened; it does not prove whether the runner is offline, busy, mislabeled, or otherwise unavailable. A terminal cancellation ends that scheduler-placement diagnosis but is not success and cannot satisfy a required physical-proof lane.<br><br><b>Frontiers Advancing:</b> ${esc(advancing)}.<br><b>Needs Work → Aurum/System:</b> ${esc(needs)}<br><b>Your Actions:</b> none. Workflow state, cancellation, CI, runner placement, and evidence freshness are Aurum/system work; only separate current evidence of a genuine physical/destructive/credential/preference boundary may create an operator task.<br><b>Ownership:</b> Workflow state alone never creates a human task.`;
}
async function refresh(){
 state={...state,phase:'checking'};render();publish();
 try{
  const[activeFile,historyFile]=await Promise.all([latest('failsafe-active-readback'),latest('failsafe-run-history')]);
  if(!activeFile||!historyFile)throw new Error('failsafe readback files missing');
  const activePayload=activeFile.payload||{},history=historyFile.payload||{};
  const observed=Math.max(Number(activePayload.observed_at||0),Number(history.observed_at||0))*1000,age=observed?Math.max(0,Date.now()-observed):null;
  const activeMap=new Map();for(const[key,v]of Object.entries(activePayload.workflows||{})){for(const r of(v?.active||[]))activeMap.set(`${key}:${r.id}`,{key,run:r})}
  const lanes=[];
  for(const[key,label,runnerClass,requiredProof]of CORE){
   const hist=((history.workflows||{})[key]?.runs||[]);let run=hist[0]||null;const act=[...activeMap.values()].find(x=>x.key===key)?.run;
   if(act&&(!run||ms(act.created_at)>=ms(run.created_at)))run=act;
   if(run)run=await liveRun(run);if(run)run=await enrichFailure(run);
   let note='';if(run){const runAge=Math.max(0,Date.now()-ms(run.created_at));if(['queued','waiting','requested','pending'].includes(run.status))note=`queued ${ageText(runAge)}${runnerClass?` · requires ${runnerClass}; scheduler placement pending`:''}`;else if(run.status==='in_progress')note=`running ${ageText(runAge)}`;else if(requiredProof&&run.status==='completed'&&run.conclusion==='cancelled')note='cancelled · required physical proof not produced';else if(run.failure_detail)note=`failed: ${run.failure_detail}`;else note=`updated ${ageText(Math.max(0,Date.now()-ms(run.updated_at||run.created_at)))} ago`;}
   lanes.push({key,label,runnerClass:runnerClass||null,requiredProof:Boolean(requiredProof),run,note});
  }
  const liveConfirmed=lanes.some(x=>Boolean(x.run?.live_confirmed)),active=[],stalled=[],unresolved=[],failures=[];
  for(const lane of lanes){const r=lane.run;if(!r)continue;const a=Math.max(0,Date.now()-ms(r.created_at));if(['queued','waiting','requested','pending'].includes(r.status)){if(a>QUEUE_GRACE)stalled.push({...lane,kind:'queued'});else active.push(lane)}else if(r.status==='in_progress'){if(a>RUN_GRACE)stalled.push({...lane,kind:'running'});else active.push(lane)}else if(lane.requiredProof&&r.status==='completed'&&r.conclusion==='cancelled')unresolved.push({...lane,kind:'cancelled-required-proof'});else if(['failure','timed_out','startup_failure','action_required'].includes(r.conclusion)&&a<=6*60*60*1000)failures.push(lane)}
  let phase='verified';if(stalled.length||unresolved.length||failures.length)phase='attention';else if(age===null||age>SNAPSHOT_STALE)phase='unknown';else if(active.length)phase='running';
  state={phase,observedAt:observed,ageMs:age,liveConfirmed,active,stalled,unresolved,failures,lanes,readbackFiles:{active:activeFile.meta?.name||null,history:historyFile.meta?.name||null},humanActionInference:false,detail:'Failsafe workflow evidence loaded.'};
 }catch(e){state={phase:'unknown',observedAt:0,ageMs:null,liveConfirmed:false,active:[],stalled:[],unresolved:[],failures:[],lanes:[],readbackFiles:{active:null,history:null},humanActionInference:false,detail:e?.message||'request failed'}}
 render();publish();
}
function boot(){if(!$('#systems')){setTimeout(boot,250);return}refresh();setInterval(refresh,REFRESH)}
boot();
})();
