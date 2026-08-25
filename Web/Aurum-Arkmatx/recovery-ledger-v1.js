/* AURUM_RECOVERY_LEDGER_V1_CANONICAL
 * AURUM_RECOVERY_LEDGER_V1_3_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * BoxBrain carries a byte-identical public projection.
 * Augments the existing expandable Recovery Guardian card;
 * it does not create a new dashboard box or any human authority.
 */
(()=>{
'use strict';
if(window.__aurumRecoveryLedgerV13)return;
window.__aurumRecoveryLedgerV13=true;
const RAW='https://raw.githubusercontent.com/FormatX66/BoxBrain/main';
const API='https://api.github.com/repos/FormatX66/BoxBrain';
const MANIFEST=`${RAW}/Projects/Aurum/Germ/GENETICS.json`;
const LEDGER=`${RAW}/Projects/Aurum/Germ/recovery_ledger.py`;
const BRIDGE=`${RAW}/Projects/Aurum/Germ/bridge.py`;
const CARRIER=`${RAW}/Projects/Aurum/Germ/carrier.py`;
const FLASH=`${RAW}/Projects/Aurum/Germ/handoff/Flash-TinySeed-Windows.ps1`;
const LEGACY=`${RAW}/.github/workflows/aurum-tiny-seed-flash-authorized.yml`;
const FLASH_CONTRACT=`${RAW}/.github/workflows/aurum-tiny-seed-flash-contract.yml`;
const VALIDATOR=`${RAW}/Admin/validate_repository.py`;
const GERM_WORKFLOW='Aurum Reseed Germ';
const FALLBACK_PR=83;
const FALLBACK_PROVENANCE_WORKFLOW='Aurum Tiny Seed fallback canonical provenance';
const FALLBACK_MATRIX_WORKFLOW='Aurum Tiny Seed x86 fallback carrier matrix experiment';
const FALLBACK_ARTIFACT='Aurum-TinySeed-amd64-fallback-matrix-experimental';
const REFRESH=5*60*1000;
let base=window.__aurumRecoveryGuardianState||null;
let evidence={manifest:null,ledgerText:'',bridgeText:'',carrierText:'',flashText:'',legacyText:'',contractText:'',validatorText:'',run:null,fallbackPr:null,fallbackRuns:[],fallbackArtifacts:[],fallbackError:'',error:''};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const newest=(runs,name)=>(Array.isArray(runs)?runs:[]).filter(r=>String(r?.name||'')===name).sort((a,b)=>new Date(b.updated_at||b.created_at)-new Date(a.updated_at||a.created_at))[0]||null;
const ledgerImplementationPresent=()=>{
 const required=Array.isArray(evidence.manifest?.required_paths)?evidence.manifest.required_paths:[];
 const t=String(evidence.ledgerText||'');
 return required.includes('Projects/Aurum/Germ/recovery_ledger.py')&&[
  'aurum-guardian-checkpoint-v1',
  'aurum-guardian-journal-entry-v1',
  'aurum-guardian-journal-head-v1',
  'def _atomic_json',
  'lkg_preserved',
  'previous_record_sha256',
  'record_sha256',
  'def prepare_change',
  'def commit_change'
 ].every(x=>t.includes(x));
};
const bridgeCarriesLedger=()=>String(evidence.bridgeText||'').includes('recovery_ledger.py');
const offlineCarrier=()=>{
 const m=evidence.manifest||{},required=Array.isArray(m.required_paths)?m.required_paths:[],offline=m?.platforms?.x86_64?.offline_carrier,t=String(evidence.carrierText||''),pinned=String(offline?.pinned_commit||'');
 const present=required.includes('Projects/Aurum/Germ/carrier.py')&&offline?.enabled===true&&/^[0-9a-f]{40}$/.test(pinned)&&[
  'aurum-offline-phenotype-carrier-v1',
  'offline-emergency-inactive-slot-candidate',
  'live_overwrite_allowed',
  'promotion_requires_guardian_health'
 ].every(x=>t.includes(x));
 return{present,pinned};
};
const preExecutionWriteGatePresent=()=>[
 'preexecution-recovery-receipt-missing',
 'preexecution-recovery-receipt-stale',
 'preexecution-remote-repair-completed-recheck-hopper',
 'AURUM_TINYSEED_PREEXECUTION_RECOVERY_GATE_OK'
].every(x=>String(evidence.flashText||'').includes(x));
const legacyRawWriteBypassDisabled=()=>{
 const legacy=String(evidence.legacyText||''),contract=String(evidence.contractText||'');
 return legacy.includes('AURUM_TINYSEED_FLASH_REFUSED reason=legacy-authorized-workflow-disabled')&&!legacy.includes('PhysicalDrive')&&!legacy.includes('IO.FileStream')&&contract.includes('legacy_bypass_disabled=true')&&contract.includes('preexecution_recovery_fail_closed=true');
};
const repositoryAuthorityFirewallPresent=()=>{
 const t=String(evidence.validatorText||'').toLowerCase();
 return[
  'def destructive_workflow_policy_errors',
  'static_authorization_pattern',
  'raw_media_write_markers',
  'workflow combines persistent static authorization with raw-media io'
 ].every(x=>t.includes(x));
};
const fallbackProvenance=()=>{
 const pr=evidence.fallbackPr||null,head=String(pr?.head?.sha||'');
 const provenance=newest(evidence.fallbackRuns,FALLBACK_PROVENANCE_WORKFLOW);
 const matrix=newest(evidence.fallbackRuns,FALLBACK_MATRIX_WORKFLOW);
 const sameHead=!!head&&String(provenance?.head_sha||'')===head&&String(matrix?.head_sha||'')===head;
 const provenancePassed=sameHead&&provenance?.status==='completed'&&provenance?.conclusion==='success';
 const matrixPassed=sameHead&&matrix?.status==='completed'&&matrix?.conclusion==='success';
 const artifact=(Array.isArray(evidence.fallbackArtifacts)?evidence.fallbackArtifacts:[]).find(a=>a?.name===FALLBACK_ARTIFACT&&a?.expired!==true&&String(a?.workflow_run?.head_sha||'')===head)||null;
 const artifactPublished=!!artifact&&matrixPassed;
 return{present:provenancePassed&&matrixPassed&&artifactPublished,head,provenance,matrix,artifact,provenancePassed,matrixPassed,artifactPublished};
};
const germCiText=()=>!evidence.run?'no current workflow evidence':['queued','in_progress','waiting','requested','pending'].includes(String(evidence.run.status||''))?String(evidence.run.status):String(evidence.run.conclusion||evidence.run.status||'unknown');
function stateSnapshot(){
 const implemented=ledgerImplementationPresent(),carried=bridgeCarriesLedger(),offline=offlineCarrier(),writeGate=preExecutionWriteGatePresent(),legacyDisabled=legacyRawWriteBypassDisabled(),authorityFirewall=repositoryAuthorityFirewallPresent(),fallback=fallbackProvenance();
 return{
  schema:'aurum-command-center-recovery-ledger-v1.3',
  canonicalWebsiteRepo:'FormatX66/ClusterSites',
  publicProjection:'FormatX66/BoxBrain:Web/Aurum-Arkmatx/recovery-ledger-v1.js',
  checkpointLedgerImplementation:implemented?'atomic-prechange-checkpoints-present':'not-verified',
  journalImplementation:implemented?'hash-chained-prepared-and-committed-journal-present':'not-verified',
  journalHeadIntegrityValidation:implemented?'record-digest-validated-before-head-acceptance':'not-verified',
  lkgPreservationRecorded:implemented?'checkpoint-records-lkg-preserved':'not-verified',
  installedGermCarrier:carried?'bridge-carries-recovery-ledger':'not-verified',
  offlineRecoveryCarrierEvidence:offline.present?'verified-pinned-offline-phenotype-carrier-present':'not-verified',
  offlineRecoveryPinnedPlatformCommit:offline.present?offline.pinned:null,
  offlineCarrierLiveOverwriteAllowed:false,
  offlineCarrierPromotionRequiresGuardianHealth:true,
  fallbackCanonicalProvenanceEvidence:fallback.provenancePassed?'same-head-canonical-provenance-workflow-passed':'not-verified',
  fallbackMatrixVirtualBootEvidence:fallback.matrixPassed?'same-head-fallback-matrix-workflow-passed':'not-verified',
  fallbackArtifactPublicationEvidence:fallback.artifactPublished?'same-head-experimental-fallback-artifact-published':'not-verified',
  fallbackExperimentalHead:fallback.present?fallback.head:null,
  fallbackArtifactDigest:fallback.present?(fallback.artifact?.digest||null):null,
  fallbackPhysicalCompatibilityInferred:false,
  fallbackWriteAuthorityGranted:false,
  fallbackPromotionAuthorityGranted:false,
  preExecutionRecoveryWriteGateEvidence:writeGate?'hard-fail-closed-before-destructive-write':'not-verified',
  preExecutionRecoveryReceiptRequired:true,
  remoteRepairCompletedSuppressesFlash:true,
  legacyRawWriteBypassEvidence:legacyDisabled?'legacy-destructive-workflow-disabled-and-contract-guarded':'not-verified',
  destructiveWriteHasSingleGuardedPath:legacyDisabled&&writeGate,
  repositoryAuthorityFirewallEvidence:authorityFirewall?'repo-wide-destructive-authority-policy-fail-closed':'not-verified',
  persistentAuthorityInDestructiveWorkflowAllowed:false,
  repositoryImplementationIsPhysicalProof:false,
  needsWorkOwner:'aurum-system',
  humanActionRequired:false,
  humanActionInference:false
 };
}
function augment(){
 if(!base)return;
 const ledger=stateSnapshot();
 const merged={...base,recoveryLedgerAugmented:true,recoveryCheckpointLedgerEvidence:ledger.checkpointLedgerImplementation,recoveryJournalEvidence:ledger.journalImplementation,recoveryJournalHeadIntegrityEvidence:ledger.journalHeadIntegrityValidation,recoveryOfflineCarrierEvidence:ledger.offlineRecoveryCarrierEvidence,recoveryFallbackCanonicalProvenanceEvidence:ledger.fallbackCanonicalProvenanceEvidence,recoveryFallbackMatrixVirtualBootEvidence:ledger.fallbackMatrixVirtualBootEvidence,recoveryFallbackArtifactPublicationEvidence:ledger.fallbackArtifactPublicationEvidence,recoveryPreExecutionWriteGateEvidence:ledger.preExecutionRecoveryWriteGateEvidence,recoveryLegacyRawWriteBypassEvidence:ledger.legacyRawWriteBypassEvidence,recoveryRepositoryAuthorityFirewallEvidence:ledger.repositoryAuthorityFirewallEvidence,recoveryLedgerPhysicalProofInferred:false};
 window.__aurumRecoveryGuardianState=merged;
 window.__aurumRecoveryLedgerState=ledger;
 window.__AURUM_RECOVERY_LEDGER_VERSION='1.3';
 window.dispatchEvent(new CustomEvent('aurum-recovery-guardian-state',{detail:merged}));
 window.dispatchEvent(new CustomEvent('aurum-recovery-ledger-state',{detail:ledger}));
 patchDetail();
}
function patchDetail(){
 const card=document.querySelector('#systems [data-id="recovery"]');
 if(!card||card.getAttribute('aria-expanded')!=='true')return;
 const guide=document.querySelector('#detail .recovery-guide');
 if(!guide)return;
 let box=guide.querySelector('.recovery-ledger-proof');
 if(!box){box=document.createElement('div');box.className='recovery-ledger-proof';const first=guide.querySelector('.recovery-proof');if(first)first.insertAdjacentElement('afterend',box);else guide.prepend(box)}
 box.style.cssText='margin:8px 0;padding:8px 9px;border:1px solid #343164;border-radius:10px;background:#111522;color:#929db0;font-size:10px;line-height:1.5';
 const implemented=ledgerImplementationPresent(),carried=bridgeCarriesLedger(),offline=offlineCarrier(),writeGate=preExecutionWriteGatePresent(),legacyDisabled=legacyRawWriteBypassDisabled(),authorityFirewall=repositoryAuthorityFirewallPresent(),fallback=fallbackProvenance();
 const checkpoint=implemented&&carried?'Protected Germ has atomic pre-change checkpoints plus a hash-chained prepared/committed journal whose head validates the referenced record digest.':'Checkpoint/journal implementation is not fully verified from current repository evidence.';
 const carrier=offline.present?`A verified offline x86 recovery carrier is pinned to platform commit ${offline.pinned}; it may grow only an inactive candidate, prohibits live overwrite, and still requires Guardian health before promotion.`:'The offline recovery carrier is not fully verified from current repository evidence.';
 const fallbackText=fallback.present?`The experimental x86 fallback loader matrix is now provenance-locked on PR #${FALLBACK_PR}: canonical-provenance and fallback-matrix workflows both passed on head ${fallback.head.slice(0,10)}, and artifact ${FALLBACK_ARTIFACT} is published${fallback.artifact?.digest?` (${fallback.artifact.digest})`:''}. This proves a same-head virtual fallback lane, not physical Hopper compatibility or promotion authority.`:'The experimental fallback loader matrix does not currently have complete same-head provenance + matrix + published-artifact proof.';
 const gate=writeGate?'The Windows Tiny Seed writer hard-fails closed unless a fresh terminal Hopper recovery-path v2 receipt proves the already-authorized system recovery path could not complete; a completed remote repair suppresses flashing and forces a Hopper health reread.':'The hard pre-execution write gate is not fully verified from current repository evidence.';
 const legacy=legacyDisabled?'The former independent authorized raw-write workflow is now a refusal-only lane, and the flash contract rejects any return of that bypass; destructive media writes have one guarded path.':'Legacy raw-write bypass lockout is not fully verified from current repository evidence.';
 const firewall=authorityFirewall?'Repository validation fails closed if retired raw-media workflows regain destructive behavior or a workflow combines persistent static AURUM authorization with raw-media I/O. Destructive authority must remain runtime-bound.':'The repository-wide destructive-authority policy is not fully verified from current validator source.';
 const needs='Aurum/System still must obtain fresh terminal recovery-path evidence when a destructive handoff is actually attempted, then prove the resulting candidate on real Hopper hardware: boot, health-gated promotion, and forced-failure return to the prior Last Known Good state. The provenance-locked fallback also remains experimental until real hardware compatibility is proven; repository or CI implementation is not physical recovery proof.';
 box.innerHTML=`<b style="color:#cfd3df">Recovery safety ledger + offline fallback</b><br><b style="color:#8ce7b2">Frontiers Advancing:</b> ${esc(checkpoint)} ${esc(carrier)} ${esc(fallbackText)} ${esc(gate)} ${esc(legacy)} ${esc(firewall)}<br><b style="color:#bbb6ff">Needs Work → Aurum/System:</b> ${esc(needs)}<br><b style="color:#f0c76a">Your Actions:</b> None from this evidence layer. The offline carriers, experimental fallback, authority firewall, and write-path guards never grant destructive write, boot, promotion, or recovery authority; Action Ownership remains the authority boundary.<br><b style="color:#74d8d0">Germ CI:</b> ${esc(germCiText())}`;
}
async function refreshFallback(){
 try{
  const p=await fetch(`${API}/pulls/${FALLBACK_PR}`,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}});
  if(!p.ok)throw new Error(`fallback PR HTTP ${p.status}`);
  const fallbackPr=await p.json(),head=String(fallbackPr?.head?.sha||'');
  if(!head)throw new Error('fallback PR head missing');
  const r=await fetch(`${API}/actions/runs?head_sha=${encodeURIComponent(head)}&per_page=100`,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}});
  if(!r.ok)throw new Error(`fallback runs HTTP ${r.status}`);
  const fallbackRuns=(await r.json()).workflow_runs||[];
  const matrix=newest(fallbackRuns,FALLBACK_MATRIX_WORKFLOW);
  let fallbackArtifacts=[];
  if(matrix?.id){
   const a=await fetch(`${API}/actions/runs/${matrix.id}/artifacts`,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}});
   if(a.ok)fallbackArtifacts=(await a.json()).artifacts||[];
  }
  evidence={...evidence,fallbackPr,fallbackRuns,fallbackArtifacts,fallbackError:''};
 }catch(e){evidence={...evidence,fallbackPr:null,fallbackRuns:[],fallbackArtifacts:[],fallbackError:e?.message||'fallback evidence request failed'}}
}
async function refresh(){
 try{
  const [m,l,b,c,f,x,k,v,r]=await Promise.all([
   fetch(MANIFEST,{cache:'no-store'}),
   fetch(LEDGER,{cache:'no-store'}),
   fetch(BRIDGE,{cache:'no-store'}),
   fetch(CARRIER,{cache:'no-store'}),
   fetch(FLASH,{cache:'no-store'}),
   fetch(LEGACY,{cache:'no-store'}),
   fetch(FLASH_CONTRACT,{cache:'no-store'}),
   fetch(VALIDATOR,{cache:'no-store'}),
   fetch(`${API}/actions/runs?branch=main&per_page=100`,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}})
  ]);
  if(!m.ok||!l.ok||!b.ok||!c.ok||!f.ok||!x.ok||!k.ok||!v.ok||!r.ok)throw new Error(`GitHub evidence HTTP ${m.status}/${l.status}/${b.status}/${c.status}/${f.status}/${x.status}/${k.status}/${v.status}/${r.status}`);
  const manifest=await m.json(),ledgerText=await l.text(),bridgeText=await b.text(),carrierText=await c.text(),flashText=await f.text(),legacyText=await x.text(),contractText=await k.text(),validatorText=await v.text(),runs=(await r.json()).workflow_runs||[];
  evidence={...evidence,manifest,ledgerText,bridgeText,carrierText,flashText,legacyText,contractText,validatorText,run:newest(runs,GERM_WORKFLOW),error:''};
 }catch(e){evidence={...evidence,manifest:null,ledgerText:'',bridgeText:'',carrierText:'',flashText:'',legacyText:'',contractText:'',validatorText:'',run:null,error:e?.message||'request failed'}}
 await refreshFallback();
 augment();
}
window.addEventListener('aurum-recovery-guardian-state',e=>{if(e.detail?.recoveryLedgerAugmented)return;base=e.detail||null;augment()});
document.addEventListener('click',e=>{if(e.target.closest?.('#systems [data-id="recovery"]'))setTimeout(patchDetail,60)});
new MutationObserver(()=>setTimeout(patchDetail,0)).observe(document.body,{childList:true,subtree:true});
refresh();setInterval(refresh,REFRESH);
})();