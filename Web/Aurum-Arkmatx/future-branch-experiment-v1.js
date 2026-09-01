/* AURUM_FUTURE_BRANCH_EXPERIMENT_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Evidence sources:
 * - Latest: FormatX66/aurum-future-branch-quantum experiment gha-33513733596-attempt-1 at evidence commit c50223e2912406a7c23a1df5dba83c1f70cafb81.
 * - Consecutive-cycle baseline: gha-33472480781-attempt-1.
 * - FormatX66/BoxBrain Aurum Experiment Race run 33487915033.
 * This surface augments the existing expandable Future Branch card only; it never creates a new major dashboard box.
 * Experimental selection, provider sweep, race results, workflow state, or prediction confidence never creates a human task or execution authority.
 */
(()=>{'use strict';
if(window.__aurumFutureBranchExperimentV1)return;
window.__aurumFutureBranchExperimentV1=true;
const EVIDENCE={
 schema:'aurum-future-branch-experiment-log-v1',
 sourceEvidenceCommit:'c50223e2912406a7c23a1df5dba83c1f70cafb81',
 runId:'33513733596',
 experimentId:'gha-33513733596-attempt-1',
 recordedAt:'2026-09-01T13:31:25.980507+00:00',
 cycle:36,
 effectiveCycle:39,
 priorRunId:'33472480781',
 priorExperimentId:'gha-33472480781-attempt-1',
 priorCycle:35,
 priorEffectiveCycle:38,
 overall:'success',
 selectedPath:'current-release-flash-readback-proven-awaiting-physical-boot',
 probability:0.8888888888888888,
 populationSize:8,
 selectedCount:1,
 prunedCount:7,
 topProbabilityFraction:0.05,
 buildState:'READY_TO_FLASH',
 authorityCommit:'8da2c636ae35801b76554d8735be84e3a9caee82',
 buildSourceCommit:'4eb31e8071cdc9705f4f5abea5af764ef35e498b',
 combinedFingerprint:'8a67443e3935d64c2d51f2df2785496adeacf56de91863b69fd8d46bfe75c015',
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
 panel.setAttribute('data-evidence-run',EVIDENCE.runId);
 const providers=EVIDENCE.providerSweeps.map(x=>`${x.provider}:${x.passed?`${x.casesExecuted}/${x.casesExecuted} pass`:'not passed'}`).join(' · ');
 panel.innerHTML=`<br><b>Latest verified Future Branch experiment</b><div class="fb-grid"><b>Frontiers Advancing</b><span>${esc(EVIDENCE.experimentId)} · ${esc(EVIDENCE.overall)} · cycle ${esc(EVIDENCE.cycle)} / effective ${esc(EVIDENCE.effectiveCycle)}. The same 1-of-8 future remained selected at ${esc(pct(EVIDENCE.probability))} one scheduled cycle after ${esc(EVIDENCE.priorExperimentId)}; ${esc(providers)} and the seed artifact fingerprint remained stable.</span><b>Selected future</b><span>${esc(EVIDENCE.selectedPath)} · ${esc(EVIDENCE.selectedCount)} of ${esc(EVIDENCE.populationSize)} retained · ${esc(EVIDENCE.prunedCount)} pruned until branch, evidence, dependency, hypothesis, or authority changes.</span><b>Seed evidence boundary</b><span>${esc(EVIDENCE.buildState)} artifact state from build source ${esc(EVIDENCE.buildSourceCommit)}; authority observation advanced to ${esc(EVIDENCE.authorityCommit)} without changing the proven artifact fingerprint. Guardian forced-rollback and physical boot remain unverified.</span><b>Needs Work → Aurum/System</b><span>Hold at the real physical-boot boundary and continue only when bounded evidence or authority changes. Experiment proof cannot grant production, write, physical, promotion, credential, identity, or LKG-mutation authority.</span><b>Your Actions</b><span>None from this evidence. No credential, reboot, cable/media move, destructive approval, identity decision, or other human-only requirement was established.</span></div>`;
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
  surfaceRevision:'v1.2',
  evidenceSourceCommit:EVIDENCE.sourceEvidenceCommit,
  evidenceRunId:EVIDENCE.runId,
  evidenceExperimentId:EVIDENCE.experimentId,
  evidenceRecordedAt:EVIDENCE.recordedAt,
  evidenceCycle:EVIDENCE.cycle,
  evidenceEffectiveCycle:EVIDENCE.effectiveCycle,
  priorEvidenceRunId:EVIDENCE.priorRunId,
  priorEvidenceExperimentId:EVIDENCE.priorExperimentId,
  consecutiveCycleSelectionStable:EVIDENCE.selectedPath==='current-release-flash-readback-proven-awaiting-physical-boot',
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
