/* AURUM_FUTURE_BRANCH_EXPERIMENT_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Evidence sources:
 * - Latest normal cycle: FormatX66/aurum-future-branch-quantum experiment gha-33567140374-attempt-1 at evidence commit 31113892de1ff66861fc9f3fb53cfe7d3734b9ee.
 * - Stable selection history: gha-33472480781-attempt-1, gha-33513733596-attempt-1, gha-33549260662-attempt-1, gha-33567140374-attempt-1.
 * - Interaction handoff correction: FormatX66/aurum-future-branch-quantum merge a5bae15cde278f07a77068f9af977bf12d9d1b81 after local-reference-tests run 33557714319 passed; normal cycle 33567140374 then regenerated the durable handoff successfully.
 * - FormatX66/BoxBrain Aurum Experiment Race run 33487915033.
 * This surface augments the existing expandable Future Branch card only; it never creates a new major dashboard box.
 * Experimental selection, provider sweep, race results, workflow state, prediction confidence, or handoff preparation never creates a human task or execution authority.
 * Equivalent scheduled repeats are evidence health, not frontier movement; this publication is justified by the handoff readiness transition, not by the unchanged selected branch.
 */
(()=>{'use strict';
if(window.__aurumFutureBranchExperimentV1)return;
window.__aurumFutureBranchExperimentV1=true;
const EVIDENCE={
 schema:'aurum-future-branch-experiment-log-v1',
 sourceEvidenceCommit:'31113892de1ff66861fc9f3fb53cfe7d3734b9ee',
 runId:'33567140374',
 experimentId:'gha-33567140374-attempt-1',
 recordedAt:'2026-09-01T22:38:23.955436+00:00',
 cycle:38,
 effectiveCycle:41,
 priorRunId:'33549260662',
 priorExperimentId:'gha-33549260662-attempt-1',
 priorCycle:37,
 priorEffectiveCycle:40,
 baselineRunId:'33472480781',
 baselineExperimentId:'gha-33472480781-attempt-1',
 baselineCycle:35,
 baselineEffectiveCycle:38,
 stableSelectionCycleCount:4,
 stableSelectionRunIds:['33472480781','33513733596','33549260662','33567140374'],
 stableSelectionCycles:[35,36,37,38],
 overall:'success',
 selectedPath:'current-release-flash-readback-proven-awaiting-physical-boot',
 probability:0.8888888888888888,
 populationSize:8,
 selectedCount:1,
 prunedCount:7,
 topProbabilityFraction:0.05,
 buildState:'READY_TO_FLASH',
 authorityCommit:'c76dd260941140cf920b9553064ca7b4a79f31a0',
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
 disposition:'wait-boundary',
 equivalentRepeat:true,
 substantiveChange:'handoff-readiness',
 equivalentRepeatSuppression:true,
 republishOnlyOnSubstantiveEvidenceChange:true
};
const HANDOFF={
 schema:'aurum-future-branch-interaction-frontier-v1',
 sourceEvidenceCommit:'31113892de1ff66861fc9f3fb53cfe7d3734b9ee',
 sourceRunId:'33567140374',
 sourceRecordedAt:'2026-09-01T22:38:24.364866+00:00',
 storedStatus:'ready',
 storedMissingEvidence:[],
 storedBuildState:'READY_TO_FLASH',
 storedNextGate:'physical-flash-and-boot-proof',
 selectedMachinePath:'current-release-flash-readback-proven-awaiting-physical-boot',
 selectedMachinePathDisposition:'wait-boundary',
 selectedMachinePathRealBoundary:true,
 branchStateSha256:'11280c2c9fddfe00502bbee2a855417f44e2a4aa662a215aa6b50842f3b258ae',
 calibrationSha256:'8431f00f73b22568eb1b26dea43a8f2cb40f33a51f29c73f99a124693bc4aa4f',
 combinedFingerprint:'8a67443e3935d64c2d51f2df2785496adeacf56de91863b69fd8d46bfe75c015',
 futureBranchSeedSha256:'148ee83e62f85702fd811d7777cd454f20ba842d07c267d154381991bbdc43fe',
 correctionCommit:'a5bae15cde278f07a77068f9af977bf12d9d1b81',
 correctionTestRunId:'33557714319',
 correctionTestConclusion:'success',
 correctionVerified:true,
 normalCycleRefreshVerified:true,
 preparedPacketFirst:true,
 fetchOnlyNewerDeltasWhenPossible:true,
 neverClaimDeliveryBeforeUserInteraction:true,
 neverPromoteUnverifiedPhysicalState:true,
 manualExperimentRerunRequired:false,
 authorityWidened:false,
 needsWorkOwner:'aurum-system',
 humanActionInference:false
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
 panel.innerHTML=`<br><b>Latest verified Future Branch evidence</b><div class="fb-grid"><b>Frontiers Advancing</b><span>The corrected Future Branch handoff path is now verified in the normal scheduled flow. Run ${esc(EVIDENCE.runId)} completed successfully and regenerated a ${esc(HANDOFF.storedStatus)} next-user interaction handoff with the selected machine path, ${esc(HANDOFF.storedBuildState)} build state, ${esc(HANDOFF.storedNextGate)} next gate, and durable proof hashes populated. The selected 1-of-8 future itself remained unchanged at ${esc(pct(EVIDENCE.probability))}; that repeat is evidence health, not separate frontier movement.</span><b>Selected future</b><span>${esc(EVIDENCE.selectedPath)} · ${esc(EVIDENCE.selectedCount)} of ${esc(EVIDENCE.populationSize)} retained · ${esc(EVIDENCE.prunedCount)} pruned until branch, evidence, dependency, hypothesis, or authority changes. The same selection has remained stable across ${esc(EVIDENCE.stableSelectionCycleCount)} scheduled cycles (${esc(EVIDENCE.stableSelectionCycles.join(' → '))}); ${esc(providers)} and the seed artifact fingerprint remain stable.</span><b>Evidence-health policy</b><span>Equivalent scheduled repeats remain healthy proof but do not trigger dashboard publication by themselves. This revision exists only because handoff readiness changed from degraded to ready. Future publications still require a material change in selected path, gate state, artifact fingerprint, provider outcome, authority boundary, or handoff readiness.</span><b>Prepared handoff process</b><span>The parser correction at ${esc(HANDOFF.correctionCommit)} is now proven through the normal continuous-flow path, not only unit/reference tests. Handoff run ${esc(HANDOFF.sourceRunId)} is ${esc(HANDOFF.storedStatus)} with no missing evidence, uses the prepared packet first, fetches only newer deltas when possible, never claims delivery before a user interaction, and never promotes unverified physical state.</span><b>Seed evidence boundary</b><span>${esc(EVIDENCE.buildState)} artifact state from build source ${esc(EVIDENCE.buildSourceCommit)}; authority observation ${esc(EVIDENCE.authorityCommit)} did not change the proven artifact fingerprint. Guardian forced-rollback and physical boot remain unverified.</span><b>Needs Work → Aurum/System</b><span>The handoff parser remediation is complete. Continue to hold at the real physical-boot boundary until bounded physical-boot or Guardian rollback evidence changes. Experiment or handoff proof cannot grant production, write, physical, promotion, credential, identity, or LKG-mutation authority.</span><b>Your Actions</b><span>None from this evidence. No credential, reboot, cable/media move, destructive approval, identity decision, or other genuinely human-only requirement was established.</span></div>`;
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
  surfaceRevision:'v1.5',
  evidenceSourceCommit:EVIDENCE.sourceEvidenceCommit,
  evidenceRunId:EVIDENCE.runId,
  evidenceExperimentId:EVIDENCE.experimentId,
  evidenceRecordedAt:EVIDENCE.recordedAt,
  evidenceCycle:EVIDENCE.cycle,
  evidenceEffectiveCycle:EVIDENCE.effectiveCycle,
  priorEvidenceRunId:EVIDENCE.priorRunId,
  priorEvidenceExperimentId:EVIDENCE.priorExperimentId,
  baselineEvidenceRunId:EVIDENCE.baselineRunId,
  baselineEvidenceExperimentId:EVIDENCE.baselineExperimentId,
  stableSelectionCycleCount:EVIDENCE.stableSelectionCycleCount,
  stableSelectionRunIds:EVIDENCE.stableSelectionRunIds.slice(),
  stableSelectionCycles:EVIDENCE.stableSelectionCycles.slice(),
  consecutiveCycleSelectionStable:EVIDENCE.selectedPath==='current-release-flash-readback-proven-awaiting-physical-boot',
  equivalentRepeat:EVIDENCE.equivalentRepeat,
  substantiveChange:EVIDENCE.substantiveChange,
  equivalentRepeatSuppression:EVIDENCE.equivalentRepeatSuppression,
  republishOnlyOnSubstantiveEvidenceChange:EVIDENCE.republishOnlyOnSubstantiveEvidenceChange,
  experimentState:EVIDENCE.overall,
  selectedPath:EVIDENCE.selectedPath,
  selectedProbability:EVIDENCE.probability,
  selectedCount:EVIDENCE.selectedCount,
  populationSize:EVIDENCE.populationSize,
  prunedCount:EVIDENCE.prunedCount,
  providerSweepPassed:EVIDENCE.providerSweeps.every(x=>x.passed&&x.failedCases===0),
  providerSweepCases:EVIDENCE.providerSweeps.reduce((n,x)=>n+x.casesExecuted,0),
  disposition:EVIDENCE.disposition,
  handoffSourceEvidenceCommit:HANDOFF.sourceEvidenceCommit,
  handoffSourceRunId:HANDOFF.sourceRunId,
  handoffStoredStatus:HANDOFF.storedStatus,
  handoffStoredMissingEvidence:HANDOFF.storedMissingEvidence.slice(),
  handoffStoredBuildState:HANDOFF.storedBuildState,
  handoffStoredNextGate:HANDOFF.storedNextGate,
  handoffSelectedMachinePath:HANDOFF.selectedMachinePath,
  handoffSelectedMachinePathRealBoundary:HANDOFF.selectedMachinePathRealBoundary,
  handoffProofBranchStateSha256:HANDOFF.branchStateSha256,
  handoffProofCalibrationSha256:HANDOFF.calibrationSha256,
  handoffProofCombinedFingerprint:HANDOFF.combinedFingerprint,
  handoffProofFutureBranchSeedSha256:HANDOFF.futureBranchSeedSha256,
  handoffCorrectionCommit:HANDOFF.correctionCommit,
  handoffCorrectionTestRunId:HANDOFF.correctionTestRunId,
  handoffCorrectionVerified:HANDOFF.correctionVerified,
  handoffNormalCycleRefreshVerified:HANDOFF.normalCycleRefreshVerified,
  handoffPreparedPacketFirst:HANDOFF.preparedPacketFirst,
  handoffFetchOnlyNewerDeltasWhenPossible:HANDOFF.fetchOnlyNewerDeltasWhenPossible,
  handoffNeverClaimDeliveryBeforeUserInteraction:HANDOFF.neverClaimDeliveryBeforeUserInteraction,
  handoffNeverPromoteUnverifiedPhysicalState:HANDOFF.neverPromoteUnverifiedPhysicalState,
  handoffManualExperimentRerunRequired:HANDOFF.manualExperimentRerunRequired,
  handoffAuthorityWidened:HANDOFF.authorityWidened,
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
