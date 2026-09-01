/* AURUM_FUTURE_BRANCH_EXPERIMENT_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Evidence sources:
 * - FormatX66/aurum-future-branch-quantum experiment gha-33472480781-attempt-1.
 * - FormatX66/BoxBrain Aurum Experiment Race run 33487915033.
 * This surface augments the existing expandable Future Branch card only; it never creates a new major dashboard box.
 * Experimental selection, provider sweep, race results, workflow state, or prediction confidence never creates a human task or execution authority.
 */
(()=>{'use strict';
if(window.__aurumFutureBranchExperimentV1)return;
window.__aurumFutureBranchExperimentV1=true;
const EVIDENCE={
 schema:'aurum-future-branch-experiment-log-v1',
 runId:'33472480781',
 experimentId:'gha-33472480781-attempt-1',
 recordedAt:'2026-09-01T05:10:33.515466+00:00',
 overall:'success',
 selectedPath:'current-release-flash-readback-proven-awaiting-physical-boot',
 probability:0.8888888888888888,
 populationSize:8,
 selectedCount:1,
 prunedCount:7,
 topProbabilityFraction:0.05,
 buildState:'READY_TO_FLASH',
 nextGate:'physical-flash-and-boot-proof',
 unresolvedGates:['guardian_forced_rollback','physical_boot'],
 providerSweeps:[
  {provider:'google',passed:true,casesExecuted:9,failedCases:0},
  {provider:'microsoft',passed:true,casesExecuted:9,failedCases:0}
 ],
 hardwareSubmission:false,
 physicalOrDestructiveEffectExecuted:false,
 disposition:'wait-boundary'
};
const RACE={
 schema:'aurum-experiment-race-scorecard-v1',
 runId:'33487915033',
 recordedAt:'2026-09-01T08:38:06Z',
 headSha:'6a89e4acc6bd723475dbfbd5a5babe1a83c0ec6b',
 overall:'success',
 benchmark:'bounded_recovery_v1',
 lanes:[
  {name:'adaptive-kernel',native:'pass',benchmark:'pass',attempts:'3→1',learnedAvoidance:true,machineNative:false,adaptiveHardware:true,loc:147},
  {name:'conventional-aurum',native:'pass',benchmark:'pass',attempts:'3→1',learnedAvoidance:true,machineNative:false,adaptiveHardware:false,loc:16614},
  {name:'stateweave',native:'pass',benchmark:'pass',attempts:'1→1',learnedAvoidance:false,machineNative:true,adaptiveHardware:false,loc:362},
  {name:'stateweave-adaptive-kernel',native:'pass',benchmark:'pass',attempts:'3→3',learnedAvoidance:false,machineNative:true,adaptiveHardware:true,loc:676}
 ],
 autoPromotion:false,
 promotionGate:'shared-real-world-capability-with-equal-or-better-verified-outcome-safety-recoverability-and-resource-cost',
 needsWorkOwner:'aurum-system',
 humanActionInference:false
};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=v=>`${Math.round(Number(v)*100)}%`;
function mount(){
 const detail=document.querySelector('[data-id="future-branch"] .fb-detail');
 if(!detail)return false;
 let panel=detail.querySelector('.fb-current-experiment');
 if(!panel){
  panel=document.createElement('div');
  panel.className='fb-current-experiment';
  panel.setAttribute('data-evidence-run',EVIDENCE.runId);
  const firstBreak=detail.querySelector('br');
  if(firstBreak)detail.insertBefore(panel,firstBreak); else detail.appendChild(panel);
 }
 const providers=EVIDENCE.providerSweeps.map(x=>`${x.provider}:${x.passed?`${x.casesExecuted}/${x.casesExecuted} pass`:'not passed'}`).join(' · ');
 panel.innerHTML=`<br><b>Latest verified Future Branch experiment</b><div class="fb-grid"><b>Experiment</b><span>${esc(EVIDENCE.experimentId)} · ${esc(EVIDENCE.overall)} · ${esc(EVIDENCE.recordedAt)}</span><b>Selected future</b><span>${esc(EVIDENCE.selectedPath)} · ${esc(pct(EVIDENCE.probability))}</span><b>Field reduction</b><span>${esc(EVIDENCE.selectedCount)} of ${esc(EVIDENCE.populationSize)} retained from the top ${esc(pct(EVIDENCE.topProbabilityFraction))} probability field · ${esc(EVIDENCE.prunedCount)} pruned until branch/evidence/dependency/hypothesis/authority changes</span><b>Provider reproducibility</b><span>${esc(providers)} · credential-free seeded sweeps</span><b>Seed evidence boundary</b><span>${esc(EVIDENCE.buildState)} artifact state; selected branch is held at the physical-boot boundary. Guardian forced-rollback and physical boot remain unverified.</span><b>Authority boundary</b><span>hardware submission=false · physical/destructive execution=false · experiment proof cannot grant production, write, physical, promotion, credential, identity, or LKG-mutation authority</span></div>`;
 let race=detail.querySelector('.fb-experiment-race');
 if(!race){
  race=document.createElement('div');
  race.className='fb-experiment-race';
  race.setAttribute('data-evidence-run',RACE.runId);
  panel.insertAdjacentElement('afterend',race);
 }
 const laneSummary=RACE.lanes.map(x=>`${x.name}: native ${x.native}, benchmark ${x.benchmark}, attempts ${x.attempts}${x.learnedAvoidance?' · learned avoidance':''}${x.machineNative?' · machine-native':''}${x.adaptiveHardware?' · adaptive HW':''}`).join('<br>');
 const allNative=RACE.lanes.every(x=>x.native==='pass');
 const allBenchmark=RACE.lanes.every(x=>x.benchmark==='pass');
 race.innerHTML=`<br><b>Verified Aurum Experiment Race</b><div class="fb-grid"><b>Frontiers Advancing</b><span>Run ${esc(RACE.runId)} · ${esc(RACE.overall)} · all ${esc(RACE.lanes.length)} lanes passed native checks and the shared ${esc(RACE.benchmark)} safety benchmark. This is comparable evidence across conventional Aurum, Stateweave, adaptive-kernel, and combined Stateweave + adaptive-kernel paths.</span><b>Lane evidence</b><span>${laneSummary}</span><b>Interpretation guardrail</b><span>Attempts and LOC are descriptive evidence, not a winner declaration. Unit-test success alone does not promote a lane, and this race has auto-promotion=false.</span><b>Needs Work → Aurum/System</b><span>Promotion remains unearned until a shared real-world Aurum capability demonstrates equal or better verified outcome, safety, recoverability, and resource cost. Continue bounded evidence gathering; do not rerun unchanged lanes merely to create activity.</span><b>Your Actions</b><span>None from this evidence. No credential, reboot, cable/media move, destructive approval, identity decision, or other human-only requirement was established.</span></div>`;
 window.__aurumFutureBranchExperimentState={
  schema:'aurum-command-center-future-branch-experiment-v1',
  surfaceRevision:'v1.1',
  evidenceRunId:EVIDENCE.runId,
  evidenceExperimentId:EVIDENCE.experimentId,
  evidenceRecordedAt:EVIDENCE.recordedAt,
  experimentState:EVIDENCE.overall,
  selectedPath:EVIDENCE.selectedPath,
  selectedProbability:EVIDENCE.probability,
  selectedCount:EVIDENCE.selectedCount,
  populationSize:EVIDENCE.populationSize,
  prunedCount:EVIDENCE.prunedCount,
  providerSweepPassed:EVIDENCE.providerSweeps.every(x=>x.passed&&x.failedCases===0),
  providerSweepCases:EVIDENCE.providerSweeps.reduce((n,x)=>n+x.casesExecuted,0),
  disposition:EVIDENCE.disposition,
  raceEvidenceRunId:RACE.runId,
  raceEvidenceRecordedAt:RACE.recordedAt,
  raceHeadSha:RACE.headSha,
  raceBenchmark:RACE.benchmark,
  raceLanes:RACE.lanes.length,
  raceAllNativePassed:allNative,
  raceAllSharedBenchmarkPassed:allBenchmark,
  raceAutoPromotion:RACE.autoPromotion,
  raceNeedsWorkOwner:RACE.needsWorkOwner,
  hardwareSubmission:false,
  physicalOrDestructiveEffectExecuted:false,
  needsWorkOwner:'aurum-system',
  humanActionInference:false,
  productionExecutionInferred:false,
  newMajorBoxAdded:false,
  existingFutureBranchBoxRemainsExpandable:true
 };
 window.dispatchEvent(new CustomEvent('aurum-future-branch-experiment-state',{detail:window.__aurumFutureBranchExperimentState}));
 return true;
}
let attempts=0;
function boot(){if(mount())return;if(++attempts<40)setTimeout(boot,250)}
window.addEventListener('aurum-future-branch-state',()=>mount());
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
