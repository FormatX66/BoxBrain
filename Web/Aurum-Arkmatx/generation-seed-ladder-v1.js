/* AURUM_GENERATION_SEED_LADDER_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Evidence boundary: implementation, preparation, and historical proof stay distinct from current exact-head verification and earned-generation gates.
 */
(()=>{
'use strict';
if(window.__aurumGenerationSeedLadderV1)return;
window.__aurumGenerationSeedLadderV1=true;
const EVIDENCE_COMMIT='4e99ca094e5e2c4d786ba69adca4c311a8964936';
const RESTORED_LKG_HEAD='a4b605b50708252fa945783e619a68b706d29382';
const ACTIVE_TRUNK_COMMIT='a89a70b18786b035b6d414ddf6250289c999571a';
const ACTIVE_TRUNK_PARENT='5f15b0f673cdc7c667948a202d4e428d0916c947';
const RESTORE_VALIDATION_COMMIT='bd76bc92f960169ced6edd2b7f895fbbde4b5cce';
const BROKEN_HUMAN_SURFACE_COMMIT='0395b2672e006262c4cbe767e3566c81fe9d9b0c';
const LAST_KNOWN_GOOD_COMMIT='f3c0a2d3f59a22f496e4bf29dff614136bfe7abd';
const LKG_TREE='c0d83736eac27d3ccb94c24a51eea0c4b22bbdeb';
const ACTIVE_TRUNK_TREE='81dd65851c0956adc3cca8440712fc58b801b5da';
const PC_IMAGE_RUN='33253166899';
const HEAL_REGROW_AUTOBUILD_RUN='33260822948';
const EVIDENCE_URL=`https://github.com/FormatX66/BoxBrain/commit/${EVIDENCE_COMMIT}`;
const TRUNK_URL=`https://github.com/FormatX66/BoxBrain/commit/${ACTIVE_TRUNK_COMMIT}`;
const PC_IMAGE_URL=`https://github.com/FormatX66/BoxBrain/actions/runs/${PC_IMAGE_RUN}`;
const HEAL_RUN_URL=`https://github.com/FormatX66/BoxBrain/actions/runs/${HEAL_REGROW_AUTOBUILD_RUN}`;
const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const generations=[
 {id:'Gen1',title:'Everyone-OS readiness gate',status:'forward-only healing/regrowth implemented · exact-head autobuild blocked before continuation proof',ready:['graphical shell contract','seven everyday traits contract','intent/accessibility contract','recovery contract','unattended candidate validation','historical TR8:WEB implementation/acceptance contract at pinned evidence commit','historical TR8:PROMPT implementation/fallback contract at pinned evidence commit','forward-only LKG restoration retained as historical recovery proof','restore-tree PC image build','generic low-memory UEFI install/reboot/self-build smoke','Hopper HP topology + offline-recovery twin smoke','boot-verified ISO publication','never-move-backward lifecycle contract','displaced-state preservation before candidate apply','append-only seed lineage journal + projection','heal current seed after failed proof','cull failed candidate while preserving receipts','require a later forward descendant before regrowth','culled-head retry forbidden'],held:['fresh exact-head Autobuild proof for healing/regrowth controller','GUI preference live-trial freshness/test determinism','heal/cull/regrow end-to-end continuation proof','TR8:WEB payload on active trunk','TR8:PROMPT payload on active trunk','repaired WEB/PROMPT candidate seed/VM acceptance','visible browser render + keyboard/pointer acceptance','prompt runtime health/fallback acceptance','Hopper physical boot','Guardian forced rollback','second-architecture usability']},
 {id:'Gen2',title:'Machine-native state substrate',status:'CI-proven foundation',ready:['deterministic semantic entity/relation graph','Slush persistence class','canonical digest + replay','contradiction rejection'],held:['remaining Gen2 software gates','machine-native recovery proof','presence-policy physical canary','earned Gen1 parent']},
 {id:'Gen3',title:'Scoped inheritance + lineage',status:'CI-proven software exchange transcript',ready:['scope-bound trait inheritance','trusted-node + safety vetoes','immutable hash-linked lineage ledger','tamper/parent-fork rejection','durable quarantine evidence','cross-node evidence receipt + replay','multi-node exchange software preflight','append-only exchange receipt chain','strict anti-replay sequencing','quarantine preservation','receipt tamper detection','LKG-preserving transcript verification'],held:['authenticated live multi-node exchange','independent-node recovery','earned Gen2 parent']}
];
const state={schema:'aurum-command-center-generation-seed-ladder-v1',componentRevision:'1.5',canonicalWebsiteRepo:'FormatX66/ClusterSites',evidenceCommit:EVIDENCE_COMMIT,evidenceClass:'repository-evidence-with-current-exact-head-blocker',restoredLkgHead:RESTORED_LKG_HEAD,activeTrunkCommit:ACTIVE_TRUNK_COMMIT,activeTrunkParent:ACTIVE_TRUNK_PARENT,restoreValidationCommit:RESTORE_VALIDATION_COMMIT,brokenHumanSurfaceCommit:BROKEN_HUMAN_SURFACE_COMMIT,lastKnownGoodCommit:LAST_KNOWN_GOOD_COMMIT,lastKnownGoodTree:LKG_TREE,activeTrunkTree:ACTIVE_TRUNK_TREE,activeTrunkTreeMatchesLastKnownGood:false,activeTrunkDescendsFromRestoredLkg:true,forwardOnlyRecoveryPreserved:true,brokenHumanSurfacePayloadQuarantined:true,evidenceOnlyTreeDriftRemovedAtRestoredLkgHead:true,forwardOnlyHealingContractImplemented:true,appendOnlySeedLineageImplemented:true,displacedStateEvidencePreserved:true,failedCandidateHealImplemented:true,failedCandidateCullAndRegrowImplemented:true,culledCandidateRetryForbidden:true,laterForwardDescendantRequiredAfterCull:true,backwardGitOperationsForbidden:true,healAndRegrowAutobuildRunId:HEAL_REGROW_AUTOBUILD_RUN,healAndRegrowExactHeadAutobuildPassed:false,healAndRegrowExactHeadBlocker:'gui-preference-live-trial-evidence-expired-during-run-tests',healAndRegrowRuntimeAcceptanceProven:false,gen1WebCapabilityContractHistoricalEvidence:true,gen1PromptCapabilityContractHistoricalEvidence:true,gen1WebCapabilityOnActiveTrunk:false,gen1PromptCapabilityOnActiveTrunk:false,gen1WebRuntimeAcceptanceProven:false,gen1PromptRuntimeAcceptanceProven:false,gen1PhysicalHumanSurfaceProofProven:false,restoreTreePcImageValidationPassed:true,restoreTreePcImageBuildPassed:true,restoreTreeGenericUefiSmokePassed:true,restoreTreeHpTwinSmokePassed:true,restoreTreeVerifiedImagePublished:true,pcImageRunId:PC_IMAGE_RUN,futureBranchParallelPreparation:true,generationEarnedBySoftwarePreparation:false,parentGateRequired:true,recoveryGateRequired:true,provenanceGateRequired:true,externalPhysicalProofRequired:true,gen3SoftwareExchangePreflightProven:true,gen3ExchangeReceiptChainProven:true,gen3AntiReplaySequencingProven:true,gen3QuarantinePreservationProven:true,gen3ReceiptTamperDetectionProven:true,gen3LiveMultiNodeExchangeProven:false,gen3IndependentNodeRecoveryProven:false,senderIdentityAuthenticated:false,networkDeliveryProven:false,peerLivenessProven:false,lkgMutationAllowed:false,trustWideningAllowed:false,physicalProofInferred:false,executionAuthorityGranted:false,mutationAuthorityGranted:false,promotionAuthorityGranted:false,humanActionInferred:false,needsWorkOwner:'aurum-system',generations};
window.__aurumGenerationSeedLadderState=state;
window.dispatchEvent(new CustomEvent('aurum-generation-seed-ladder-state',{detail:state}));
const style=document.createElement('style');
style.id='aurumGenerationSeedLadderStyle';
style.textContent=`
.generation-seed-ladder{margin-top:10px;border:1px solid #3b4772;border-radius:12px;background:#101522;padding:11px}
.generation-seed-ladder h4{margin:0 0 7px;font-size:11px;color:#a8c9ff;text-transform:uppercase;letter-spacing:.07em}
.generation-seed-ladder p,.generation-seed-ladder li{font-size:10.5px;line-height:1.48;color:#939caf}.generation-seed-ladder p{margin:5px 0}.generation-seed-ladder ul{margin:5px 0 8px;padding-left:18px}
.generation-seed-ladder b{color:#d8e8ff}.generation-seed-ladder a{color:#a8c9ff;font-weight:750;text-decoration:none}.generation-seed-ladder a:hover{text-decoration:underline}
.generation-seed-row{margin:7px 0;padding:8px 9px;border:1px solid #303b5e;border-radius:9px;background:#141a28}.generation-seed-row strong{color:#cbdcff}.generation-seed-row .held{color:#efc97a}
`;
document.head.appendChild(style);
function seedCard(){
 const direct=$('#systems [data-id="seed"]');
 if(direct)return direct;
 return [...document.querySelectorAll('#systems .card,#systems .system-card')].find(c=>/^Seed (Pipeline|Lifecycle)$/i.test($('h3',c)?.textContent?.trim()||''))||null;
}
function generationHtml(g){return `<div class="generation-seed-row"><p><strong>${esc(g.id)} · ${esc(g.title)}</strong><br>${esc(g.status)}</p><p><b>Software evidence:</b> ${esc(g.ready.join(' · '))}</p><p class="held"><b>Held gates:</b> ${esc(g.held.join(' · '))}</p></div>`}
function enhance(){
 const card=seedCard();if(!card)return;
 card.dataset.generationSeedLadder='gen1-gen3-forward-heal-regrow-truth';
 if(card.getAttribute('aria-expanded')!=='true')return;
 const detail=$('#detail');if(!detail||!detail.classList.contains('show'))return;
 let panel=$('.generation-seed-ladder',detail);
 if(!panel){panel=document.createElement('div');panel.className='generation-seed-ladder';detail.appendChild(panel)}
 panel.innerHTML=`<h4>Future Branch · generation seed ladder</h4><p><b>Evidence rule:</b> later generations may be prepared in parallel, but preparation never makes a generation earned. Implementation is also not the same as exact-head verification: current source, historical green proof, and a blocked current workflow remain separate evidence layers while parent, recovery, provenance, and generation-specific external gates stay fail-closed.</p>${generations.map(generationHtml).join('')}<p><b>Frontiers Advancing:</b> current Aurum trunk <code>${esc(ACTIVE_TRUNK_COMMIT.slice(0,12))}</code> is two commits ahead of the restored-LKG head <code>${esc(RESTORED_LKG_HEAD.slice(0,12))}</code> and adds an explicit forward-only seed law: <i>Boot once. Grow continuously. Never move backward.</i> Failed candidate handling now preserves displaced-state evidence, appends lineage events, heals the running seed, culls the failed candidate without erasing its receipts, forbids retrying that culled head, and accepts only a later forward descendant regrown from verified LKG genetics. The earlier restore-tree PC build/UEFI/Hopper-twin proof remains valid historical evidence for its exact revision.</p><p><b>Needs Work → Aurum/System:</b> do not promote the new healing/regrowth controller as verified yet. Exact-head Autobuild run <code>${esc(HEAL_REGROW_AUTOBUILD_RUN)}</code> failed in <code>Run tests</code> because the GUI preference live-trial fixture was already outside its freshness window, so healing/regrowth continuation steps never ran. Correct the freshness/test-time evidence path, then run the changed head once and require a green exact-head Autobuild plus a real heal/cull/regrow continuation receipt before advancing the claim. Do not rerun the unchanged failed head merely to show activity, do not retry a culled candidate, and do not reopen already-valid restore-tree or Gen2/Gen3 historical proof. WEB/PROMPT, physical boot, forced Guardian rollback, second-architecture usability, LKG, trust, mutation, and promotion gates remain held independently.</p><p><b>Your Actions:</b> none. The freshness failure, exact-head verification, lineage proof, candidate healing/culling, regrowth, and downstream generation gates are Aurum/System work. No credential, media move, reboot, destructive approval, identity decision, or subjective choice is proven necessary by the current evidence.</p><p><a href="${TRUNK_URL}" target="_blank" rel="noopener">Open current forward-healing Aurum trunk ↗</a> · <a href="${HEAL_RUN_URL}" target="_blank" rel="noopener">Open exact-head Autobuild blocker ↗</a> · <a href="${PC_IMAGE_URL}" target="_blank" rel="noopener">Open retained restore-tree boot proof ↗</a> · <a href="${EVIDENCE_URL}" target="_blank" rel="noopener">Open retained generation evidence ↗</a></p>`;
}
let scheduled=false;
function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;enhance()})}
document.addEventListener('click',e=>{if(e.target.closest?.('#systems [data-id="seed"]'))setTimeout(enhance,35)});
document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.closest?.('#systems [data-id="seed"]'))setTimeout(enhance,35)});
new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['aria-expanded','class']});
enhance();setTimeout(enhance,500);setInterval(enhance,15000);
})();
