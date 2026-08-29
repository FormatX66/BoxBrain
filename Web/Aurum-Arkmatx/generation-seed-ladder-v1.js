/* AURUM_GENERATION_SEED_LADDER_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Evidence boundary: software preparation may run ahead; generations are earned only through parent + recovery + provenance + generation-specific proof.
 */
(()=>{
'use strict';
if(window.__aurumGenerationSeedLadderV1)return;
window.__aurumGenerationSeedLadderV1=true;
const EVIDENCE_COMMIT='4e99ca094e5e2c4d786ba69adca4c311a8964936';
const ACTIVE_TRUNK_COMMIT='a4b605b50708252fa945783e619a68b706d29382';
const RESTORE_VALIDATION_COMMIT='bd76bc92f960169ced6edd2b7f895fbbde4b5cce';
const BROKEN_HUMAN_SURFACE_COMMIT='0395b2672e006262c4cbe767e3566c81fe9d9b0c';
const LAST_KNOWN_GOOD_COMMIT='f3c0a2d3f59a22f496e4bf29dff614136bfe7abd';
const LKG_TREE='c0d83736eac27d3ccb94c24a51eea0c4b22bbdeb';
const PC_IMAGE_RUN='33253166899';
const EVIDENCE_URL=`https://github.com/FormatX66/BoxBrain/commit/${EVIDENCE_COMMIT}`;
const TRUNK_URL=`https://github.com/FormatX66/BoxBrain/commit/${ACTIVE_TRUNK_COMMIT}`;
const PC_IMAGE_URL=`https://github.com/FormatX66/BoxBrain/actions/runs/${PC_IMAGE_RUN}`;
const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[c]));
const generations=[
 {id:'Gen1',title:'Everyone-OS readiness gate',status:'LKG restored · broken human-surface candidate quarantined',ready:['graphical shell contract','seven everyday traits contract','intent/accessibility contract','recovery contract','unattended candidate validation','historical TR8:WEB implementation/acceptance contract at pinned evidence commit','historical TR8:PROMPT implementation/fallback contract at pinned evidence commit','forward-only active trunk restored byte-for-byte to LKG tree'],held:['TR8:WEB payload on active trunk','TR8:PROMPT payload on active trunk','repaired WEB/PROMPT candidate seed/VM acceptance','visible browser render + keyboard/pointer acceptance','prompt runtime health/fallback acceptance','restore-tree generic UEFI + HP-twin boot-smoke completion','Hopper physical boot','Guardian forced rollback','second-architecture usability']},
 {id:'Gen2',title:'Machine-native state substrate',status:'CI-proven foundation',ready:['deterministic semantic entity/relation graph','Slush persistence class','canonical digest + replay','contradiction rejection'],held:['remaining Gen2 software gates','machine-native recovery proof','presence-policy physical canary','earned Gen1 parent']},
 {id:'Gen3',title:'Scoped inheritance + lineage',status:'CI-proven software exchange transcript',ready:['scope-bound trait inheritance','trusted-node + safety vetoes','immutable hash-linked lineage ledger','tamper/parent-fork rejection','durable quarantine evidence','cross-node evidence receipt + replay','multi-node exchange software preflight','append-only exchange receipt chain','strict anti-replay sequencing','quarantine preservation','receipt tamper detection','LKG-preserving transcript verification'],held:['authenticated live multi-node exchange','independent-node recovery','earned Gen2 parent']}
];
const state={schema:'aurum-command-center-generation-seed-ladder-v1',componentRevision:'1.4',canonicalWebsiteRepo:'FormatX66/ClusterSites',evidenceCommit:EVIDENCE_COMMIT,evidenceClass:'repository-ci-proven-software-preparation',activeTrunkCommit:ACTIVE_TRUNK_COMMIT,restoreValidationCommit:RESTORE_VALIDATION_COMMIT,brokenHumanSurfaceCommit:BROKEN_HUMAN_SURFACE_COMMIT,lastKnownGoodCommit:LAST_KNOWN_GOOD_COMMIT,lastKnownGoodTree:LKG_TREE,activeTrunkTree:LKG_TREE,activeTrunkTreeMatchesLastKnownGood:true,forwardOnlyRecoveryPreserved:true,brokenHumanSurfacePayloadQuarantined:true,evidenceOnlyTreeDriftRemoved:true,gen1WebCapabilityContractHistoricalEvidence:true,gen1PromptCapabilityContractHistoricalEvidence:true,gen1WebCapabilityOnActiveTrunk:false,gen1PromptCapabilityOnActiveTrunk:false,gen1WebRuntimeAcceptanceProven:false,gen1PromptRuntimeAcceptanceProven:false,gen1PhysicalHumanSurfaceProofProven:false,restoreTreePcImageValidationPassed:true,restoreTreePcImageBuildPassed:true,restoreTreeGenericUefiSmokePending:true,restoreTreeHpTwinSmokePending:true,pcImageRunId:PC_IMAGE_RUN,futureBranchParallelPreparation:true,generationEarnedBySoftwarePreparation:false,parentGateRequired:true,recoveryGateRequired:true,provenanceGateRequired:true,externalPhysicalProofRequired:true,gen3SoftwareExchangePreflightProven:true,gen3ExchangeReceiptChainProven:true,gen3AntiReplaySequencingProven:true,gen3QuarantinePreservationProven:true,gen3ReceiptTamperDetectionProven:true,gen3LiveMultiNodeExchangeProven:false,gen3IndependentNodeRecoveryProven:false,senderIdentityAuthenticated:false,networkDeliveryProven:false,peerLivenessProven:false,lkgMutationAllowed:false,trustWideningAllowed:false,physicalProofInferred:false,executionAuthorityGranted:false,mutationAuthorityGranted:false,promotionAuthorityGranted:false,humanActionInferred:false,needsWorkOwner:'aurum-system',generations};
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
 card.dataset.generationSeedLadder='gen1-gen3-lkg-recovery-truth';
 if(card.getAttribute('aria-expanded')!=='true')return;
 const detail=$('#detail');if(!detail||!detail.classList.contains('show'))return;
 let panel=$('.generation-seed-ladder',detail);
 if(!panel){panel=document.createElement('div');panel.className='generation-seed-ladder';detail.appendChild(panel)}
 panel.innerHTML=`<h4>Future Branch · generation seed ladder</h4><p><b>Evidence rule:</b> later generations may be prepared in parallel, but preparation never makes a generation earned. A failed candidate also does not erase valid historical evidence: active-trunk truth and older exact-commit software evidence stay separate, while parent, recovery, provenance, and generation-specific external gates remain fail-closed.</p>${generations.map(generationHtml).join('')}<p><b>Frontiers Advancing:</b> Aurum's recovery path moved forward without rewriting history. Broken human-surface head <code>${esc(BROKEN_HUMAN_SURFACE_COMMIT.slice(0,12))}</code> was superseded by forward-only restore <code>${esc(RESTORE_VALIDATION_COMMIT.slice(0,12))}</code>, and current trunk <code>${esc(ACTIVE_TRUNK_COMMIT.slice(0,12))}</code> removes later evidence-only tree drift while selecting tree <code>${esc(LKG_TREE.slice(0,12))}</code>, byte-for-byte identical to Last Known Good <code>${esc(LAST_KNOWN_GOOD_COMMIT.slice(0,12))}</code>. On that restored tree, PC-image fast validation and image build have passed; generic UEFI and Hopper HP-twin boot-smoke jobs are still in progress at this evidence cut. Gen2/Gen3 exact-commit preparation evidence remains retained separately.</p><p><b>Needs Work → Aurum/System:</b> keep the broken TR8:WEB/TR8:PROMPT payload off active LKG. Diagnose and repair those surfaces on a new bounded candidate, then require seed/VM checks, visible browser rendering with keyboard/pointer input, prompt service health plus no-key fallback, and completed image/boot-smoke evidence before any reintroduction or promotion. Do not reopen already-valid historical Gen2/Gen3 evidence, and do not bypass parent, recovery, provenance, physical, LKG, trust, mutation, or promotion gates.</p><p><b>Your Actions:</b> none. Forward-only recovery, candidate quarantine, build/boot validation, WEB/PROMPT repair, and generation evidence management are Aurum/System work. No credential, media move, reboot, destructive approval, identity decision, or subjective choice is proven necessary by this evidence.</p><p><a href="${TRUNK_URL}" target="_blank" rel="noopener">Open current restored Aurum trunk head ↗</a> · <a href="${PC_IMAGE_URL}" target="_blank" rel="noopener">Open restore-tree PC image verification ↗</a> · <a href="${EVIDENCE_URL}" target="_blank" rel="noopener">Open retained generation evidence ↗</a></p>`;
}
let scheduled=false;
function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;enhance()})}
document.addEventListener('click',e=>{if(e.target.closest?.('#systems [data-id="seed"]'))setTimeout(enhance,35)});
document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.closest?.('#systems [data-id="seed"]'))setTimeout(enhance,35)});
new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['aria-expanded','class']});
enhance();setTimeout(enhance,500);setInterval(enhance,15000);
})();
