/* AURUM_RECOVERY_GUARDIAN_V1_CANONICAL
 * AURUM_RECOVERY_GUARDIAN_V1_1_CANONICAL
 * AURUM_RECOVERY_GUARDIAN_V1_2_CANONICAL
 * AURUM_RECOVERY_GUARDIAN_V1_3_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Surfaces protected reseed/recovery evidence while keeping repository/CI proof,
 * boot-boundary safety logic, and physical promotion/rollback proof distinct.
 */
(()=>{
'use strict';
if(window.__aurumRecoveryGuardianV1)return;
window.__aurumRecoveryGuardianV1=true;
const API='https://api.github.com/repos/FormatX66/BoxBrain';
const DOC_URL='https://github.com/FormatX66/BoxBrain/blob/main/docs/architecture/SEED_RECOVERY_ARCHITECTURE.md';
const GENETICS_DOC_URL='https://github.com/FormatX66/BoxBrain/blob/main/docs/architecture/RESEED_GENETICS_ARCHITECTURE.md';
const STATUS_URL='https://raw.githubusercontent.com/FormatX66/BoxBrain/main/Projects/Aurum/Germ/STATUS.md';
const MANIFEST_URL='https://raw.githubusercontent.com/FormatX66/BoxBrain/main/Projects/Aurum/Germ/GENETICS.json';
const GERM_URL='https://raw.githubusercontent.com/FormatX66/BoxBrain/main/Projects/Aurum/Germ/reseed.py';
const GUARDIAN_URL='https://raw.githubusercontent.com/FormatX66/BoxBrain/main/Projects/Aurum/Germ/guardian.py';
const TINYSEED_URL='https://raw.githubusercontent.com/FormatX66/BoxBrain/main/Projects/Aurum/Germ/tinyseed.py';
const GERM_WORKFLOW='Aurum Reseed Germ';
const INVARIANT='No new state may destroy the last proven working state.';
const REGROWTH_INVARIANT='Any viable germ-bearing seed must be able to regrow directly into the current trusted genetics without replaying every intermediate generation.';
const FLOW='proven local state → snapshot → resolve genetics → grow inactive candidate → arm trial → boot-boundary activation → physical/runtime health gate → promote → new LKG';
const FAILURE='candidate failure or missing proof → freeze → capture → quarantine → LKG rollback → boot/test → optionally regrow fresh candidate → report';
const PHASE1=['protected Reseed Germ with stable genetics manifest/protocol','A/B seed slots','Last Known Good metadata/pointer','protected State Guardian/watchdog','candidate-only genetics staging + pre-change snapshot hook','boot-boundary trial activation','boot/runtime + physical x86 promotion gate','automatic rollback','mutation journal + quarantine','protected GitHub desired-state reseed/rollback trigger'];
const NOT_PROVEN=['a real x86 trial producing a fresh first-boot assessment plus input-ready receipt and then promoting','a real x86 candidate failure returning automatically to the previous Last Known Good state','physical Tiny Seed boot/regrowth on Raspberry Pi hardware','long-duration watchdog/recovery behavior under real faults','signed genetics/protected-ref verification'];
const HUMAN_RULE='No action from you right now. Physical proof remains Aurum/system work until current evidence names a specific device and a genuinely human-only operation.';
const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const activeRun=r=>['queued','in_progress','waiting','requested','pending'].includes(String(r?.status||''));
const failedRun=r=>['failure','timed_out','startup_failure','action_required'].includes(String(r?.conclusion||''));
const runText=r=>!r?'no current workflow evidence':activeRun(r)?String(r.status):r.conclusion||r.status||'unknown';
const style=document.createElement('style');
style.id='aurumRecoveryGuardianStyle';
style.textContent=`
.recovery-law{margin-top:9px;border:1px solid #4d467f;border-radius:10px;background:#171629;padding:8px 9px;color:#cbc7ff;font-size:10px;font-weight:850}.recovery-law small{display:block;margin-top:3px;color:#9099ad;font-size:9px;font-weight:650}.recovery-guide{margin-top:10px;border:1px solid #3c386a;border-radius:12px;background:#121421;padding:11px}.recovery-guide h4{margin:0 0 6px;font-size:11px;color:#cbc7ff;text-transform:uppercase;letter-spacing:.07em}.recovery-guide p,.recovery-guide li{font-size:10.5px;line-height:1.48;color:#939caf}.recovery-guide p{margin:4px 0}.recovery-guide ol,.recovery-guide ul{margin:6px 0 0;padding-left:18px}.recovery-guide a{color:#bcb7ff;font-weight:750;text-decoration:none}.recovery-guide a:hover{text-decoration:underline}.recovery-owner{margin-top:8px;padding-top:8px;border-top:1px solid #343164;color:#8f99ad;font-size:9.5px;line-height:1.42}.recovery-owner b{color:#bcb7ff}.recovery-proof{display:grid;grid-template-columns:165px minmax(0,1fr);gap:5px 9px;margin:7px 0 9px}.recovery-proof b{color:#cfd3df;font-size:10px}.recovery-proof span{min-width:0;overflow-wrap:anywhere}@media(max-width:680px){.recovery-proof{grid-template-columns:1fr}}
`;
document.head.appendChild(style);
let state={phase:'checking',manifest:null,germPresent:false,guardianPresent:false,tinySeedPresent:false,bootBoundaryTrialPresent:false,physicalX86GatePresent:false,tinySeedRepairSafetyPresent:false,statusFrontierPresent:false,run:null,error:''};
function card(){return $('#systems [data-id="recovery"]')}
function ensureCard(){
 const systems=$('#systems');if(!systems)return null;
 let c=card();
 if(!c){
  c=document.createElement('button');c.type='button';c.className='card';c.dataset.id='recovery';
  c.innerHTML='<div class="card-head"><div class="card-icon">⟲</div><span class="pill running">Checking</span></div><h3>Recovery Guardian</h3><p>Protected reseed germ, A/B + LKG survival layer, boot-boundary trials, physical promotion gates and rollback.</p><div class="evidence">Checking current genetics/recovery evidence…</div><div class="recovery-law">Protect the last proven state.<small>Git stores the genetics. Seeds carry the germ. Software guardrails do not equal physical recovery proof.</small></div>';
  systems.appendChild(c);
 }
 return c;
}
function phase(){
 if(state.error)return'unknown';
 if(!state.manifest||!state.germPresent||!state.guardianPresent)return'attention';
 if(!state.bootBoundaryTrialPresent||!state.physicalX86GatePresent)return'attention';
 if(failedRun(state.run))return'attention';
 if(activeRun(state.run))return'building';
 if(state.run?.conclusion==='success')return'verified-germ';
 return'built-germ';
}
function manifestValid(m){return m?.schema==='aurum-genetics-v1'&&m?.germ_protocol===1&&m?.repository==='https://github.com/FormatX66/BoxBrain.git'&&m?.policy?.candidate_only_staging===true&&m?.policy?.live_overwrite_allowed===false&&m?.policy?.promotion_requires_health_evidence===true&&m?.policy?.resolve_immutable_commit_before_growth===true}
function render(){
 const c=ensureCard();if(!c)return;
 state.phase=phase();c.dataset.recoveryPhase=state.phase;
 const pill=$('.pill',c),evidence=$('.evidence',c);
 if(state.phase==='checking'){pill.className='pill running';pill.textContent='Checking';evidence.textContent='Checking current genetics/recovery evidence…'}
 else if(state.phase==='verified-germ'){pill.className='pill running';pill.textContent='Advancing';evidence.textContent=`Boot-boundary A/B/LKG guard + x86 physical promotion gate${state.tinySeedRepairSafetyPresent?' + repair-first Tiny Seed':''} are implemented; germ CI is green · hardware proof remains system work.`}
 else if(state.phase==='building'){pill.className='pill running';pill.textContent='Building';evidence.textContent=`Recovery safety code is present; ${GERM_WORKFLOW} is ${runText(state.run)} · physical promotion/rollback proof remains separate.`}
 else if(state.phase==='built-germ'){pill.className='pill running';pill.textContent='Built';evidence.textContent='Boot-boundary trial and x86 physical promotion guardrails are implemented · current CI proof is not established; physical recovery proof remains separate.'}
 else if(state.phase==='attention'){pill.className='pill failed';pill.textContent='Attention';evidence.textContent=`Recovery evidence problem: ${state.run&&failedRun(state.run)?`Reseed Germ workflow ${runText(state.run)}`:'current germ/guardian safety contract unavailable or incomplete'} · Aurum/system work; no human action inferred.`}
 else{pill.className='pill waiting';pill.textContent='Needs Work';evidence.textContent=`Recovery evidence unavailable${state.error?`: ${state.error}`:''} · Aurum/system evidence refresh; no human action inferred.`}
 enhanceDetail();publish();
}
function enhanceDetail(){
 const c=card();if(!c||c.getAttribute('aria-expanded')!=='true')return;
 const detail=$('#detail');if(!detail||!detail.classList.contains('show'))return;
 const title=$('#detailTitle');if(title)title.textContent='Recovery Guardian — Boot-safe genetics + physical promotion gate';
 const text=$('#detailText');if(text)text.textContent='The software survival layer now keeps the active phenotype untouched while a trial is merely armed, switches only at a boot boundary, and requires fresh physical x86 evidence before promotion. That is stronger implementation evidence, not physical proof.';
 const host=$('.guide-wrap',detail)||detail;
 let box=$('.recovery-guide',host);if(!box){box=document.createElement('div');box.className='recovery-guide';host.appendChild(box)}
 const m=state.manifest||{};
 box.innerHTML=`<h4>Current proof boundary</h4><div class="recovery-proof"><b>Reseed Germ</b><span>${esc(state.germPresent?'regrowth implementation present':'not verified present')}</span><b>A/B + LKG Guardian</b><span>${esc(state.guardianPresent?'runtime implementation present':'not verified present')}</span><b>Boot-boundary trial</b><span>${esc(state.bootBoundaryTrialPresent?'armed candidate does not replace the running phenotype; activation waits for boot preflight':'not verified in current guardian')}</span><b>x86 promotion gate</b><span>${esc(state.physicalX86GatePresent?'fresh first-boot selftest + physical desktop + input-ready evidence required before promotion':'not verified in current guardian')}</span><b>Tiny Seed repair safety</b><span>${esc(state.tinySeedRepairSafetyPresent?'one existing Aurum defaults to Repair/Reseed; ambiguous/no target stops without writing':'not verified in current Tiny Seed')}</span><b>Tiny Seed substrate</b><span>${esc(state.tinySeedPresent?'installer/bootstrap paths are in the current genetics manifest':'not verified present')}</span><b>Genetics manifest</b><span>${esc(manifestValid(m)?`compatible · schema ${m.schema} · protocol ${m.germ_protocol}`:'not verified compatible')}</span><b>Germ CI lane</b><span>${esc(runText(state.run))}</span><b>Current frontier record</b><span>${esc(state.statusFrontierPresent?'repository status keeps physical proof explicitly unresolved':'not verified present')}</span><b>Live overwrite</b><span>${esc(m?.policy?.live_overwrite_allowed===false?'prohibited':'not verified')}</span></div><p><b>Important:</b> the promotion code now refuses to treat a passing unit/selftest alone as sufficient on a rich x86 phenotype. It waits for fresh first-boot assessment and input readiness. Repository implementation or CI success still cannot label physical promotion/rollback as verified.</p><h4 style="margin-top:10px">Genetics / regrowth model</h4><p><b>${esc(INVARIANT)}</b></p><p>${esc(REGROWTH_INVARIANT)}</p><p><b>Healthy promotion:</b> ${esc(FLOW)}</p><p><b>Failure recovery:</b> ${esc(FAILURE)}</p><h4 style="margin-top:10px">Phase 1 survival layer</h4><ol>${PHASE1.map(x=>`<li>${esc(x)}</li>`).join('')}</ol><h4 style="margin-top:10px">Needs Work → Aurum/System</h4><ul>${NOT_PROVEN.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><div class="recovery-owner"><b>Your Actions:</b> ${esc(HUMAN_RULE)}</div><p style="margin-top:8px"><a href="${GENETICS_DOC_URL}" target="_blank" rel="noopener">Open genetics / reseed architecture ↗</a> · <a href="${DOC_URL}" target="_blank" rel="noopener">Open recovery architecture ↗</a></p>`;
}
function seedGuard(){
 const seed=$('#systems [data-id="seed"]');if(!seed)return;
 let note=$('.recovery-owner',seed);if(!note){note=document.createElement('div');note.className='recovery-owner';seed.appendChild(note)}
 note.innerHTML='<b>Genetics/recovery invariant:</b> grow into the inactive slot, leave the current phenotype untouched while the trial is armed, switch only at the boot boundary, and promote only after fresh health evidence.';
}
function publish(){
 const s={schema:'aurum-command-center-recovery-guardian-v1.3',architectureLocked:true,mandatoryBaseSeed:true,phase1:PHASE1.slice(),germImplementationEvidence:state.germPresent?'repository-present':'not-verified',guardianImplementationEvidence:state.guardianPresent?'ab-lkg-health-rollback-runtime-present':'not-verified',bootBoundaryTrialEvidence:state.bootBoundaryTrialPresent?'armed-without-live-switch-boot-preflight-activation':'not-verified',physicalX86PromotionGateEvidence:state.physicalX86GatePresent?'fresh-first-boot-desktop-input-required':'not-verified',tinySeedRepairSafetyEvidence:state.tinySeedRepairSafetyPresent?'repair-first-ambiguous-target-stops-without-write':'not-verified',tinySeedSubstrateEvidence:state.tinySeedPresent?'manifest-present':'not-verified',statusFrontierEvidence:state.statusFrontierPresent?'physical-proof-explicitly-unresolved':'not-verified',germManifestCompatible:manifestValid(state.manifest),germWorkflow:state.run?{id:state.run.id,status:state.run.status,conclusion:state.run.conclusion}:null,germSafetyContractVerified:state.run?.conclusion==='success',fullRecoveryImplementationEvidence:'software-survival-layer-present-hardware-proof-pending',physicalRecoveryProofInferred:false,needsWorkOwner:'aurum-system',humanActionInference:false,docUrl:DOC_URL,geneticsDocUrl:GENETICS_DOC_URL};
 window.__aurumRecoveryGuardianState=s;
 window.dispatchEvent(new CustomEvent('aurum-recovery-guardian-state',{detail:s}));
}
async function refreshEvidence(){
 state={...state,phase:'checking',error:''};render();
 try{
  const [mr,gr,gar,tr,sr,rr]=await Promise.all([
   fetch(MANIFEST_URL,{cache:'no-store'}),
   fetch(GERM_URL,{cache:'no-store'}),
   fetch(GUARDIAN_URL,{cache:'no-store'}),
   fetch(TINYSEED_URL,{cache:'no-store'}),
   fetch(STATUS_URL,{cache:'no-store'}),
   fetch(`${API}/actions/runs?branch=main&per_page=100`,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}})
  ]);
  if(!mr.ok||!gr.ok||!gar.ok||!tr.ok||!sr.ok||!rr.ok)throw new Error(`GitHub evidence HTTP ${mr.status}/${gr.status}/${gar.status}/${tr.status}/${sr.status}/${rr.status}`);
  const manifest=await mr.json(),germ=await gr.text(),guardian=await gar.text(),tinyseed=await tr.text(),frontier=await sr.text(),runs=(await rr.json()).workflow_runs||[];
  const germPresent=germ.includes('Aurum protected reseed germ')&&germ.includes('SLOTS_ROOT')&&germ.includes('previous_lkg_preserved')&&germ.includes('promotion_performed');
  const guardianPresent=guardian.includes('aurum-germ-slots-v1')&&guardian.includes('def arm_trial')&&guardian.includes('def health_check')&&guardian.includes('def rollback')&&guardian.includes('candidate-promoted-healthy');
  const bootBoundaryTrialPresent=guardian.includes('trial-armed-for-next-boot')&&guardian.includes('trial-not-yet-activated-at-boot')&&guardian.includes('candidate slot may not replace the Last Known Good');
  const physicalX86GatePresent=guardian.includes('fresh-physical-health-evidence-not-proven')&&guardian.includes('first-boot-assessment.json')&&guardian.includes('aurum-input-status.json')&&guardian.includes('physical_desktop')&&guardian.includes('input_ready');
  const tinySeedRepairSafetyPresent=tinyseed.includes('repair/reseed selected automatically')&&tinyseed.includes('stopped without writing anything');
  const statusFrontierPresent=frontier.includes('waiting for build/physical proof')&&frontier.includes('require fresh selftest + critical-service + physical desktop + input evidence')&&frontier.includes('promote on proof or automatically roll back to Gen0');
  const required=Array.isArray(manifest?.required_paths)?manifest.required_paths:[];
  const tinySeedPresent=['Projects/Aurum/Germ/installer.py','Projects/Aurum/Germ/tinyseed.py','Projects/Aurum/Germ/bootstrap_console.py','docs/architecture/TINY_SEED_BOOT_MEDIUM.md'].every(x=>required.includes(x));
  const run=runs.filter(r=>String(r.name||'')===GERM_WORKFLOW).sort((a,b)=>new Date(b.updated_at||b.created_at)-new Date(a.updated_at||a.created_at))[0]||null;
  state={phase:'',manifest,germPresent,guardianPresent,tinySeedPresent,bootBoundaryTrialPresent,physicalX86GatePresent,tinySeedRepairSafetyPresent,statusFrontierPresent,run,error:''};
 }catch(e){state={phase:'unknown',manifest:null,germPresent:false,guardianPresent:false,tinySeedPresent:false,bootBoundaryTrialPresent:false,physicalX86GatePresent:false,tinySeedRepairSafetyPresent:false,statusFrontierPresent:false,run:null,error:e?.message||'request failed'}}
 render();
}
let scheduled=false;function refresh(){scheduled=false;ensureCard();seedGuard();enhanceDetail()}function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(refresh)}
document.addEventListener('click',e=>{if(e.target.closest?.('#systems [data-id="recovery"]'))setTimeout(enhanceDetail,35)});
document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.closest?.('#systems [data-id="recovery"]'))setTimeout(enhanceDetail,35)});
new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true,characterData:true});
refresh();refreshEvidence();setTimeout(refresh,500);setInterval(refresh,15000);setInterval(refreshEvidence,300000);
})();
