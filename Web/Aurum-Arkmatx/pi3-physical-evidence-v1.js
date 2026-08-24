/* AURUM_PI3_PHYSICAL_EVIDENCE_V1_3_CANONICAL
 * AURUM_PI3_PHYSICAL_EVIDENCE_V1_2_CANONICAL compatibility marker.
 * AURUM_PI3_PHYSICAL_EVIDENCE_V1_CANONICAL compatibility marker.
 * Canonical website owner: FormatX66/ClusterSites.
 * Read-only physical-evidence surface for the dedicated Aurum Raspberry Pi 3 experiment node.
 * Repository/workflow evidence never implies a real Pi3 identity receipt, mutation authority,
 * promotion authority, root cause, or a human task. Negative topology evidence is still useful,
 * and routing can pivot between self-hosted runners without weakening SSH identity checks.
 */
(()=>{'use strict';if(window.__aurumPi3PhysicalEvidenceV1)return;window.__aurumPi3PhysicalEvidenceV1=true;
const RAW='https://raw.githubusercontent.com/FormatX66/BoxBrain/main';
const API='https://api.github.com/repos/FormatX66/BoxBrain';
const REQUEST_URL=`${RAW}/Projects/Aurum/Experiments/pi3-probe-request.json`;
const RECEIPT_URL=`${RAW}/Projects/Aurum/Experiments/latest-pi3-physical-receipt.json`;
const PROBE_URL=`${RAW}/Projects/Aurum/Experiments/pi3_physical_probe.py`;
const PROBE_WORKFLOW_URL=`${RAW}/.github/workflows/aurum-pi3-readonly-probe.yml`;
const EXP_WORKFLOW_URL=`${RAW}/.github/workflows/aurum-experiments.yml`;
const ATTACHED_REQUEST_URL=`${RAW}/Projects/Aurum/Experiments/pi3-global-runner-request.json`;
const ATTACHED_RECEIPT_URL=`${RAW}/Projects/Aurum/Experiments/latest-pi3-attached-runner-probe.json`;
const ATTACHED_WORKFLOW_URL=`${RAW}/.github/workflows/aurum-pi3-global-runner-probe.yml`;
const PROBE_WORKFLOW='Aurum Pi3 Read-Only Physical Probe';
const ATTACHED_WORKFLOW='Aurum Pi3 Attached-Runner Read-Only Probe';
const EXP_WORKFLOW='Aurum Parallel Experiments';
const ATTACHED_RUNNER='GLOBAL-FAMILY-DESKTOP';
const REFRESH=2*60*1000,FRESH=6*60*60*1000;
const $=(s,r=document)=>r.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const age=v=>{const n=Date.parse(v||'');return Number.isFinite(n)?Math.max(0,Date.now()-n):null};
const ageText=ms=>{if(ms===null)return'unknown';const m=Math.floor(ms/60000);if(m<60)return`${m} min`;const h=Math.floor(m/60),r=m%60;return r?`${h}h ${r}m`:`${h}h`};
const active=r=>['queued','in_progress','waiting','requested','pending'].includes(String(r?.status||''));
const failed=r=>['failure','timed_out','startup_failure','action_required'].includes(String(r?.conclusion||''));
let state={phase:'checking',request:null,receipt:null,probeText:'',probeWorkflowText:'',expWorkflowText:'',attachedRequest:null,attachedReceipt:null,attachedWorkflowText:'',probeRun:null,probeRunAge:null,attachedRun:null,attachedRunAge:null,expRun:null,expRunAge:null,error:''};
const safeRequest=()=>Boolean(state.request?.schema==='aurum-pi3-probe-request-v1'&&state.request?.mode==='known-name-read-only'&&state.request?.mutation_allowed===false&&state.request?.promotion_allowed===false&&state.request?.write_authority===false);
const attachedRequestSafe=()=>Boolean(state.attachedRequest?.schema==='aurum-pi3-attached-runner-request-v1'&&state.attachedRequest?.expected_runner_name===ATTACHED_RUNNER&&state.attachedRequest?.active_network_scan===false&&state.attachedRequest?.persistent_trust_change_allowed===false&&state.attachedRequest?.mutation_allowed===false&&state.attachedRequest?.promotion_allowed===false&&state.attachedRequest?.write_authority===false);
const codeGatePresent=()=>['capture-stateweave-before-change','probe-mesh-read-only','stage-adaptive-kernel-candidate-observe-only','keep-adaptive-kernel-held-on-current-arch','promotion_allowed'].every(x=>state.probeText.includes(x));
const workflowGuarded=()=>state.probeWorkflowText.includes('runs-on: [self-hosted, Windows, X64, aurum-elevated]')&&state.probeWorkflowText.includes("write_authority = $false")&&state.probeWorkflowText.includes("mutation_allowed = $false")&&state.probeWorkflowText.includes("promotion_allowed = $false")&&state.probeWorkflowText.includes('BatchMode=yes');
const attachedWorkflowGuarded=()=>[
  'name: Aurum Pi3 Attached-Runner Read-Only Probe',
  'runs-on: [self-hosted, Windows, X64, aurum-elevated]',
  "$expectedRunner = 'GLOBAL-FAMILY-DESKTOP'",
  "active_network_scan=$false",
  "persistent_trust_changed=$false",
  "mutation_allowed=$false",
  "promotion_allowed=$false",
  "write_authority=$false",
  'BatchMode=yes',
  'HostKeyAlias=$alias'
].every(x=>state.attachedWorkflowText.includes(x));
const experimentGatePresent=()=>state.expWorkflowText.includes('pi3-physical-gate:')&&state.expWorkflowText.includes('test_pi3_physical_probe');
const receiptCaptured=()=>Boolean(state.receipt?.schema==='aurum-pi3-read-only-probe-result-v1'&&state.receipt?.state==='PHYSICAL_RECEIPT_CAPTURED'&&state.receipt?.receipt?.schema==='aurum-pi3-physical-receipt-v1');
const noReachableReceipt=()=>Boolean(state.receipt?.schema==='aurum-pi3-read-only-probe-result-v1'&&state.receipt?.state==='NO_REACHABLE_PI3_RECEIPT'&&state.receipt?.receipt===null&&state.receipt?.mutation_allowed===false&&state.receipt?.promotion_allowed===false&&state.receipt?.write_authority===false);
const attachedReceiptCaptured=()=>Boolean(state.attachedReceipt?.schema==='aurum-pi3-attached-runner-probe-v1'&&state.attachedReceipt?.runner_name===ATTACHED_RUNNER&&state.attachedReceipt?.state==='PHYSICAL_RECEIPT_CAPTURED'&&state.attachedReceipt?.receipt?.schema==='aurum-pi3-physical-receipt-v1'&&state.attachedReceipt?.mutation_allowed===false&&state.attachedReceipt?.promotion_allowed===false&&state.attachedReceipt?.write_authority===false);
const attachedIdentityBoundary=()=>Boolean(state.attachedReceipt?.schema==='aurum-pi3-attached-runner-probe-v1'&&state.attachedReceipt?.runner_name===ATTACHED_RUNNER&&state.attachedReceipt?.state==='REACHABLE_IDENTITY_UNVERIFIED'&&state.attachedReceipt?.receipt===null&&state.attachedReceipt?.mutation_allowed===false&&state.attachedReceipt?.promotion_allowed===false&&state.attachedReceipt?.write_authority===false);
const attachedNoEndpoint=()=>Boolean(state.attachedReceipt?.schema==='aurum-pi3-attached-runner-probe-v1'&&state.attachedReceipt?.runner_name===ATTACHED_RUNNER&&state.attachedReceipt?.state==='NO_REACHABLE_PASSIVE_USB_ENDPOINT'&&state.attachedReceipt?.receipt===null&&state.attachedReceipt?.mutation_allowed===false&&state.attachedReceipt?.promotion_allowed===false&&state.attachedReceipt?.write_authority===false);
const attempts=()=>Array.isArray(state.receipt?.attempts)?state.receipt.attempts:[];
const attachedAttempts=()=>Array.isArray(state.attachedReceipt?.attempts)?state.attachedReceipt.attempts:[];
const latestRun=(runs,name)=>(runs||[]).filter(r=>String(r?.name||r?.display_title||'')===name).sort((a,b)=>new Date(b.updated_at||b.created_at)-new Date(a.updated_at||a.created_at))[0]||null;
function classify(){
  const implemented=safeRequest()&&codeGatePresent()&&workflowGuarded()&&experimentGatePresent();
  if(!implemented)return'unknown';
  if(attachedReceiptCaptured()||receiptCaptured())return'captured';
  const attachedFresh=state.attachedRunAge!==null&&state.attachedRunAge<=FRESH;
  if(state.attachedRun&&attachedFresh&&active(state.attachedRun))return'runner-routing';
  if(attachedIdentityBoundary())return'identity-boundary';
  if(attachedNoEndpoint())return'attached-unreachable';
  if(attachedRequestSafe()&&attachedWorkflowGuarded())return'runner-routing-armed';
  const fresh=state.probeRunAge!==null&&state.probeRunAge<=FRESH;
  if(state.probeRun&&fresh&&active(state.probeRun))return'running';
  if(state.probeRun&&fresh&&failed(state.probeRun))return'attention';
  if(noReachableReceipt())return'unreachable';
  return'armed';
}
function currentReceipt(){return attachedReceiptCaptured()?state.attachedReceipt?.receipt:state.receipt?.receipt||{}}
function runText(r,ms){if(!r)return'no current workflow evidence';return`${r.conclusion||r.status||'unknown'} · ${ageText(ms)} old`}
function kernelGateText(){if(!attachedReceiptCaptured()&&!receiptCaptured())return'waiting for a real Pi3 identity/hardware receipt before architecture-dependent candidate logic is trusted';const a=String(currentReceipt()?.arch||'').toLowerCase();if(a==='aarch64')return'AArch64 receipt may stage arm64-small observe-only; promotion remains forbidden';if(a==='armv7l'||a==='armv7')return'ARMv7 receipt keeps Adaptive Kernel held on the current observed architecture; no candidate promotion';return`architecture ${a||'unknown'} is recorded, but no candidate promotion is inferred`}
function attemptText(){const a=attempts();if(!a.length)return'none recorded';return a.map(x=>`${x.target_name||'unknown'}:tcp22=${x.tcp22_reachable===true?'yes':'no'}`).join(' · ')}
function attachedAttemptText(){const a=attachedAttempts();if(!a.length)return'none recorded';return a.map(x=>`${x.endpoint_label||'endpoint'}:${x.trusted_alias||'alias'}:ssh=${x.strict_ssh_exit??'?'}`).join(' · ')}
const css=document.createElement('style');css.textContent=`.pi3-physical-card .p3-hint{margin-top:9px;font-size:9px;color:#737e92;font-weight:750}.pi3-physical-card .p3-detail{display:none;margin-top:11px;padding-top:11px;border-top:1px solid #283041;font-size:10.5px;line-height:1.5;color:#909bad}.pi3-physical-card[aria-expanded=true] .p3-detail{display:block}.pi3-physical-card[aria-expanded=true] .p3-hint{color:#74d8d0}.pi3-physical-card .p3-grid{display:grid;grid-template-columns:155px minmax(0,1fr);gap:5px 9px;margin-top:8px}.pi3-physical-card .p3-grid b{color:#cfd3df;font-size:10px}.pi3-physical-card .p3-grid span{min-width:0;overflow-wrap:anywhere}@media(max-width:680px){.pi3-physical-card .p3-grid{grid-template-columns:1fr}}`;document.head.appendChild(css);
function ensure(){const systems=$('#systems');if(!systems)return null;let card=$('[data-id="pi3-physical-evidence"]',systems);if(card)return card;card=document.createElement('article');card.className='system-card pi3-physical-card';card.dataset.id='pi3-physical-evidence';card.tabIndex=0;card.setAttribute('role','button');card.setAttribute('aria-expanded','false');card.innerHTML='<div class="card-head"><div class="card-icon">π3</div><span class="pill experiment">Experiment</span></div><h3>Pi3 Physical Evidence</h3><p>Real-hardware proof lane for StateWeave, Adaptive Kernel, mesh probing, and Future Branch — read-only first.</p><div class="evidence">Checking Pi3 physical evidence…</div><div class="p3-hint">Tap to expand physical receipt, runner routing, architecture gate, workflow, and action boundaries →</div><div class="p3-detail"></div>';const toggle=e=>{if(e?.type==='keydown'&&!['Enter',' '].includes(e.key))return;if(e?.type==='keydown')e.preventDefault();card.setAttribute('aria-expanded',String(card.getAttribute('aria-expanded')!=='true'));e?.stopPropagation?.()};card.addEventListener('click',toggle);card.addEventListener('keydown',toggle);systems.appendChild(card);return card}
async function getJson(u,optional=false){const r=await fetch(u,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}});if(optional&&r.status===404)return null;if(!r.ok)throw Error(`HTTP ${r.status}`);return r.json()}
async function getText(u,optional=false){const r=await fetch(u,{cache:'no-store'});if(optional&&r.status===404)return'';if(!r.ok)throw Error(`HTTP ${r.status}`);return r.text()}
function render(){
 const card=ensure();if(!card)return;
 state.phase=classify();
 const pill=$('.pill',card),evidence=$('.evidence',card),detail=$('.p3-detail',card),captured=attachedReceiptCaptured()||receiptCaptured(),unreachable=noReachableReceipt(),attachedUnreachable=attachedNoEndpoint(),identityBoundary=attachedIdentityBoundary(),rr=currentReceipt(),a=attempts();
 card.dataset.pi3PhysicalPhase=state.phase;
 if(state.phase==='checking'){pill.className='pill running';pill.textContent='Checking';evidence.textContent='Checking Pi3 read-only request, runner routing, workflow guards, topology evidence, and physical receipt…'}
 else if(state.phase==='runner-routing'){pill.className='pill running';pill.textContent='Advancing';evidence.textContent=`Attached-desktop Pi3 proof is ${state.attachedRun?.status||'active'} on the self-hosted Windows lane; only ${ATTACHED_RUNNER} may collect passive USB + strict-SSH evidence.`}
 else if(state.phase==='runner-routing-armed'){pill.className='pill experiment';pill.textContent='Advancing';evidence.textContent=`Attached-runner routing is armed for ${ATTACHED_RUNNER}; zero active scan, trust mutation, write, mutation, or promotion authority.`}
 else if(state.phase==='identity-boundary'){pill.className='pill failed';pill.textContent='Needs Work';evidence.textContent=`${ATTACHED_RUNNER} found a passive USB-side TCP/22 candidate, but strict existing SSH identity/authentication did not verify it. Do not weaken host-key or authentication checks.`}
 else if(state.phase==='attached-unreachable'){pill.className='pill failed';pill.textContent='Needs Work';evidence.textContent=`${ATTACHED_RUNNER} completed the attached-runner probe without a reachable passive USB TCP/22 endpoint. This is a machine-side topology boundary, not proof of a human-only fault.`}
 else if(state.phase==='running'){pill.className='pill running';pill.textContent='Advancing';evidence.textContent=`Read-only Pi3 known-name probe is ${state.probeRun?.status||'active'} on the self-hosted Windows lane · zero write, mutation, or promotion authority.`}
 else if(state.phase==='attention'){pill.className='pill failed';pill.textContent='Needs Work';evidence.textContent=`Pi3 read-only lane is implemented, but the latest fresh known-name probe is ${state.probeRun?.conclusion||state.probeRun?.status}. Root cause is not inferred; Aurum/System owns diagnosis.`}
 else if(state.phase==='captured'){pill.className='pill experiment';pill.textContent='Advancing';evidence.textContent=`Real Pi3 identity/hardware receipt captured · ${rr.model||'Pi3'} · ${rr.arch||'arch unknown'} · ${rr.cores??'?'} cores · ${rr.ram_mb??'?'} MB · observe-only boundary preserved.`}
 else if(state.phase==='unreachable'){pill.className='pill failed';pill.textContent='Needs Work';evidence.textContent=`Known-name topology receipt: no Pi3 target reached TCP/22 across ${a.length||0} bounded names. Newer attached-runner routing is not yet proven terminal.`}
 else if(state.phase==='armed'){pill.className='pill experiment';pill.textContent='Advancing';evidence.textContent='Read-only Pi3 physical-evidence lane is implemented and requested; no terminal topology or real Pi3 identity receipt is current yet.'}
 else{pill.className='pill unknown';pill.textContent='Unknown';evidence.textContent=state.error?`Pi3 physical evidence is incomplete: ${state.error} · no human action inferred.`:'Pi3 physical evidence is incomplete · no human action inferred.'}
 const receiptAge=captured?age((attachedReceiptCaptured()?state.attachedReceipt?.observed_at_utc:state.receipt?.observed_at_utc)||rr.captured_at):(attachedUnreachable||identityBoundary)?age(state.attachedReceipt?.observed_at_utc):unreachable?age(state.receipt?.observed_at_utc):null;
 let need;
 if(captured)need='Feed the captured receipt through the observe-only StateWeave + Adaptive Kernel/Future Branch trial and collect resulting experiment evidence. Physical promotion, kernel replacement, firmware/network changes, and LKG mutation remain separate later proof gates.';
 else if(identityBoundary)need=`Keep the strict identity boundary intact on ${ATTACHED_RUNNER}. Diagnose why the passive USB TCP/22 endpoint cannot satisfy the existing trusted alias/host-key/authentication path; do not add trust automatically or weaken BatchMode/host-key verification.`;
 else if(attachedUnreachable)need=`Diagnose passive USB adapter/neighbor visibility and TCP/22 reachability on ${ATTACHED_RUNNER}. The receipt does not prove power loss, cable failure, or that a person must intervene.`;
 else if(state.phase==='runner-routing'||state.phase==='runner-routing-armed')need=`Let the bounded attached-runner race reach ${ATTACHED_RUNNER} and publish a terminal receipt. Wrong-runner jobs are allowed to exit without probing; only the workstation previously associated with the Pi3 USB endpoint may continue.`;
 else if(unreachable)need=`The earlier bounded names (${attemptText()}) produced no TCP/22 route. Continue the newer attached-runner route before escalating; do not infer that the Pi3 is powered off, physically disconnected, mislabeled, or in need of human intervention.`;
 else if(state.phase==='attention')need='Diagnose the failed read-only probe job or transport and obtain a fresh terminal topology result or real Pi3 identity receipt. Do not infer a human-only fault until evidence proves it.';
 else need='Let the read-only self-hosted probe finish and publish a fresh terminal topology result or real Pi3 identity receipt. Diagnose topology/SSH reachability as system work before asking for any physical intervention.';
 if(detail)detail.innerHTML=`<b>Pi3 physical evidence boundary</b><div class="p3-grid"><b>Known-name request</b><span>${safeRequest()?`safe read-only · ${esc(state.request?.request_id||'request id unknown')}`:'not safely proven'}</span><b>Attached-runner request</b><span>${attachedRequestSafe()?`safe read-only · target ${ATTACHED_RUNNER} · ${esc(state.attachedRequest?.request_id||'request id unknown')}`:'not active / not safely proven'}</span><b>Active network scan</b><span>false</span><b>Persistent SSH trust change</b><span>false</span><b>Mutation authority</b><span>false</span><b>Write authority</b><span>false</span><b>Promotion authority</b><span>false</span><b>Known-name workflow</b><span>${esc(runText(state.probeRun,state.probeRunAge))}</span><b>Attached-runner workflow</b><span>${attachedWorkflowGuarded()?`${esc(runText(state.attachedRun,state.attachedRunAge))} · wrong runners exit before probing`:'not fully proven'}</span><b>Attached-runner receipt</b><span>${attachedReceiptCaptured()?'Pi3 identity captured':identityBoundary?`reachable endpoint / strict identity unverified · ${esc(ageText(receiptAge))} old`:attachedUnreachable?`no reachable passive USB endpoint · ${esc(ageText(receiptAge))} old`:'not terminal yet'}</span><b>Attached strict attempts</b><span>${esc(attachedAttemptText())}</span><b>Known-name topology receipt</b><span>${receiptCaptured()?'Pi3 identity captured':unreachable?`terminal no-reachable result · ${esc(ageText(age(state.receipt?.observed_at_utc)))} old`:'not terminal yet'}</span><b>Known targets attempted</b><span>${unreachable?esc(attemptText()):'not applicable / not yet terminal'}</span><b>Root cause</b><span>not inferred</span><b>Model</b><span>${esc(rr.model||'not proven')}</span><b>Architecture</b><span>${esc(rr.arch||'not proven')}</span><b>Kernel</b><span>${esc(rr.kernel||'not proven')}</span><b>Hardware facts</b><span>${captured?`${esc(rr.cores)} cores · ${esc(rr.ram_mb)} MB · interfaces ${esc((rr.interfaces||[]).join(', ')||'none reported')}`:'waiting for Pi3 identity/hardware receipt'}</span><b>StateWeave binding</b><span>${codeGatePresent()?'hostname/model/arch/kernel/cores/RAM/boot-id/interfaces are bound into observed machine state only after real identity capture':'not proven'}</span><b>Adaptive Kernel gate</b><span>${esc(kernelGateText())}</span><b>Future Branch next</b><span>${codeGatePresent()?'capture StateWeave before change → mesh probe read-only → either stage an architecture-supported candidate observe-only or keep the current architecture held':'not proven'}</span></div><br><b>Frontiers Advancing:</b> the Pi3 lane now has a second fail-closed routing path that targets the workstation previously associated with the Pi3 USB endpoint without changing runner configuration, scanning the broader network, or weakening SSH identity verification. ${captured?'A real Pi3 identity/hardware receipt is present; repository code is no longer the only evidence for this lane.':identityBoundary?'The machine path reached TCP/22 but stopped correctly at strict identity verification.':attachedUnreachable?'The attached workstation produced a terminal no-passive-endpoint result; that negative topology evidence is narrower than the earlier generic runner result.':state.phase==='runner-routing'||state.phase==='runner-routing-armed'?`The bounded runner race is now the active machine-side route toward ${ATTACHED_RUNNER}.`:unreachable?'The older known-name probe already narrowed the boundary before TCP/22; the attached-runner route is the newer system attempt.':'The lane is armed/requested, but repository/workflow implementation is not being mislabeled as a real physical receipt.'}<br><b>Needs Work → Aurum/System:</b> ${esc(need)}<br><b>Your Actions:</b> none for this Pi3 lane. Runner routing, probe requests, reachability failures, identity failures, and no-endpoint receipts cannot manufacture a human task. Exact physical directions belong here only after fresh evidence proves that no machine-capable route remains and identifies the required physical operation.`;
 window.__aurumPi3PhysicalEvidenceState={schema:'aurum-command-center-pi3-physical-evidence-v1.3',phase:state.phase,canonicalOwner:'FormatX66/ClusterSites',requestSafeReadOnly:safeRequest(),probeImplementationPresent:codeGatePresent(),probeWorkflowGuarded:workflowGuarded(),parallelExperimentGatePresent:experimentGatePresent(),attachedRunnerRequestSafeReadOnly:attachedRequestSafe(),attachedRunnerWorkflowGuarded:attachedWorkflowGuarded(),attachedRunnerRouteTarget:ATTACHED_RUNNER,attachedRunnerReceiptState:state.attachedReceipt?.state||'not-verified',attachedRunnerReceiptCaptured:attachedReceiptCaptured(),attachedRunnerIdentityUnverified:attachedIdentityBoundary(),attachedRunnerNoPassiveEndpoint:attachedNoEndpoint(),activeNetworkScanAllowed:false,persistentTrustChangeAllowed:false,physicalReceiptCaptured:captured,noReachableReceiptObserved:unreachable,reachabilityReceiptState:state.receipt?.state||'not-verified',knownTargetsTried:a.length,tcp22ReachableCount:a.filter(x=>x?.tcp22_reachable===true).length,rootCauseInferred:false,physicalReceiptArch:captured?rr.arch||null:null,physicalReceiptModel:captured?rr.model||null:null,adaptiveKernelGate:kernelGateText(),stateWeaveHardwareBinding:codeGatePresent(),mutationAllowed:false,promotionAllowed:false,writeAuthority:false,needsWorkOwner:'aurum-system',humanActionInference:false};
 window.dispatchEvent(new CustomEvent('aurum-pi3-physical-evidence-state',{detail:window.__aurumPi3PhysicalEvidenceState}));
}
async function refresh(){
 state={...state,phase:'checking',error:''};render();
 try{
  const [request,receipt,probeText,probeWorkflowText,expWorkflowText,attachedRequest,attachedReceipt,attachedWorkflowText,runs]=await Promise.all([
   getJson(REQUEST_URL),getJson(RECEIPT_URL,true),getText(PROBE_URL),getText(PROBE_WORKFLOW_URL),getText(EXP_WORKFLOW_URL),
   getJson(ATTACHED_REQUEST_URL,true),getJson(ATTACHED_RECEIPT_URL,true),getText(ATTACHED_WORKFLOW_URL,true),getJson(`${API}/actions/runs?per_page=100`)
  ]);
  const probeRun=latestRun(runs?.workflow_runs,PROBE_WORKFLOW),attachedRun=latestRun(runs?.workflow_runs,ATTACHED_WORKFLOW),expRun=latestRun(runs?.workflow_runs,EXP_WORKFLOW);
  state={phase:'checking',request,receipt,probeText,probeWorkflowText,expWorkflowText,attachedRequest,attachedReceipt,attachedWorkflowText,probeRun,probeRunAge:probeRun?age(probeRun.updated_at||probeRun.created_at):null,attachedRun,attachedRunAge:attachedRun?age(attachedRun.updated_at||attachedRun.created_at):null,expRun,expRunAge:expRun?age(expRun.updated_at||expRun.created_at):null,error:''};
 }catch(e){state={...state,error:e?.message||'request failed'}}
 render();
}
function boot(){if(!$('#systems')){setTimeout(boot,250);return}ensure();refresh();setInterval(refresh,REFRESH)}boot();
})();
