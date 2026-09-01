/* AURUM_FUTURE_BRANCH_EXPERIMENT_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Evidence source: FormatX66/aurum-future-branch-quantum experiment gha-33472480781-attempt-1.
 * This surface augments the existing expandable Future Branch card only; it never creates a new major dashboard box.
 * Experimental selection, provider sweep, workflow state, or prediction confidence never creates a human task or execution authority.
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
 window.__aurumFutureBranchExperimentState={
  schema:'aurum-command-center-future-branch-experiment-v1',
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
