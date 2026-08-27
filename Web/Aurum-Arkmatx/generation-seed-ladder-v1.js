/* AURUM_GENERATION_SEED_LADDER_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Evidence boundary: software preparation may run ahead; generations are earned only through parent + recovery + provenance + generation-specific proof.
 */
(()=>{
'use strict';
if(window.__aurumGenerationSeedLadderV1)return;
window.__aurumGenerationSeedLadderV1=true;
const EVIDENCE_COMMIT='e676ab4e4a4876293a3f0ec6ce6e61bc0e1d92e4';
const EVIDENCE_URL=`https://github.com/FormatX66/BoxBrain/commit/${EVIDENCE_COMMIT}`;
const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const generations=[
 {id:'Gen1',title:'Everyone-OS readiness gate',status:'CI-proven software evaluator',ready:['graphical shell contract','seven everyday traits contract','intent/accessibility contract','recovery contract','unattended candidate validation'],held:['Hopper physical boot','Guardian forced rollback','second-architecture usability']},
 {id:'Gen2',title:'Machine-native state substrate',status:'CI-proven foundation',ready:['deterministic semantic entity/relation graph','Slush persistence class','canonical digest + replay','contradiction rejection'],held:['remaining Gen2 software gates','machine-native recovery proof','presence-policy physical canary','earned Gen1 parent']},
 {id:'Gen3',title:'Scoped inheritance + lineage',status:'CI-proven software exchange transcript',ready:['scope-bound trait inheritance','trusted-node + safety vetoes','immutable hash-linked lineage ledger','tamper/parent-fork rejection','durable quarantine evidence','cross-node evidence receipt + replay','multi-node exchange software preflight','append-only exchange receipt chain','strict anti-replay sequencing','quarantine preservation','receipt tamper detection','LKG-preserving transcript verification'],held:['authenticated live multi-node exchange','independent-node recovery','earned Gen2 parent']}
];
const state={schema:'aurum-command-center-generation-seed-ladder-v1',canonicalWebsiteRepo:'FormatX66/ClusterSites',evidenceCommit:EVIDENCE_COMMIT,evidenceClass:'repository-ci-proven-software-preparation',futureBranchParallelPreparation:true,generationEarnedBySoftwarePreparation:false,parentGateRequired:true,recoveryGateRequired:true,provenanceGateRequired:true,externalPhysicalProofRequired:true,gen3SoftwareExchangePreflightProven:true,gen3ExchangeReceiptChainProven:true,gen3AntiReplaySequencingProven:true,gen3QuarantinePreservationProven:true,gen3ReceiptTamperDetectionProven:true,gen3LiveMultiNodeExchangeProven:false,gen3IndependentNodeRecoveryProven:false,senderIdentityAuthenticated:false,networkDeliveryProven:false,peerLivenessProven:false,lkgMutationAllowed:false,trustWideningAllowed:false,physicalProofInferred:false,executionAuthorityGranted:false,mutationAuthorityGranted:false,promotionAuthorityGranted:false,humanActionInferred:false,needsWorkOwner:'aurum-system',generations};
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
 card.dataset.generationSeedLadder='gen1-gen3-parallel-preparation';
 if(card.getAttribute('aria-expanded')!=='true')return;
 const detail=$('#detail');if(!detail||!detail.classList.contains('show'))return;
 let panel=$('.generation-seed-ladder',detail);
 if(!panel){panel=document.createElement('div');panel.className='generation-seed-ladder';detail.appendChild(panel)}
 panel.innerHTML=`<h4>Future Branch · generation seed ladder</h4><p><b>Evidence rule:</b> later generations may be prepared in parallel, but preparation never makes a generation earned. Parent, recovery, provenance, and generation-specific external gates remain fail-closed.</p>${generations.map(generationHtml).join('')}<p><b>Frontiers Advancing:</b> BoxBrain main CI has proven an executable Gen1→Gen3 preparation ladder through <code>${esc(EVIDENCE_COMMIT.slice(0,12))}</code>: Gen1 readiness evaluation, Gen2 machine-native/Slush state, and Gen3 scoped inheritance, immutable lineage replay, zero-authority exchange preflight, plus a deterministic receipt chain with strict sequencing, anti-replay refusal, quarantine preservation, tamper detection, and LKG preservation.</p><p><b>Needs Work → Aurum/System:</b> earn Gen1 only after its physical/recovery/second-architecture gates; continue remaining Gen2 software/recovery work and take Gen3 from software-only transcript proof to authenticated live multi-node exchange with peer identity, network delivery/liveness, and independent-node recovery evidence. No descendant may bypass an unearned parent, recovery proof, or provenance.</p><p><b>Your Actions:</b> none from generation preparation. CI, predicted futures, lineage data, exchange preflight, receipt chaining, or a software-ready descendant cannot grant physical/destructive authority or create a human task.</p><p><a href="${EVIDENCE_URL}" target="_blank" rel="noopener">Open verified BoxBrain evidence head ↗</a></p>`;
}
let scheduled=false;
function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;enhance()})}
document.addEventListener('click',e=>{if(e.target.closest?.('#systems [data-id="seed"]'))setTimeout(enhance,35)});
document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.closest?.('#systems [data-id="seed"]'))setTimeout(enhance,35)});
new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['aria-expanded','class']});
enhance();setTimeout(enhance,500);setInterval(enhance,15000);
})();
