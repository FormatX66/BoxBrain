/* AURUM_RECOVERY_LEDGER_V1_CANONICAL
 * AURUM_RECOVERY_LEDGER_V1_1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * BoxBrain carries a byte-identical public projection.
 * Augments the existing expandable Recovery Guardian card;
 * it does not create a new dashboard box or any human authority.
 */
(()=>{
'use strict';
if(window.__aurumRecoveryLedgerV11)return;
window.__aurumRecoveryLedgerV11=true;
const RAW='https://raw.githubusercontent.com/FormatX66/BoxBrain/main';
const API='https://api.github.com/repos/FormatX66/BoxBrain';
const MANIFEST=`${RAW}/Projects/Aurum/Germ/GENETICS.json`;
const LEDGER=`${RAW}/Projects/Aurum/Germ/recovery_ledger.py`;
const BRIDGE=`${RAW}/Projects/Aurum/Germ/bridge.py`;
const CARRIER=`${RAW}/Projects/Aurum/Germ/carrier.py`;
const FLASH=`${RAW}/Projects/Aurum/Germ/handoff/Flash-TinySeed-Windows.ps1`;
const GERM_WORKFLOW='Aurum Reseed Germ';
const REFRESH=5*60*1000;
let base=window.__aurumRecoveryGuardianState||null;
let evidence={manifest:null,ledgerText:'',bridgeText:'',carrierText:'',flashText:'',run:null,error:''};
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
const germCiText=()=>!evidence.run?'no current workflow evidence':['queued','in_progress','waiting','requested','pending'].includes(String(evidence.run.status||''))?String(evidence.run.status):String(evidence.run.conclusion||evidence.run.status||'unknown');
function stateSnapshot(){
 const implemented=ledgerImplementationPresent(),carried=bridgeCarriesLedger(),offline=offlineCarrier(),writeGate=preExecutionWriteGatePresent();
 return{
  schema:'aurum-command-center-recovery-ledger-v1.1',
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
  preExecutionRecoveryWriteGateEvidence:writeGate?'hard-fail-closed-before-destructive-write':'not-verified',
  preExecutionRecoveryReceiptRequired:true,
  remoteRepairCompletedSuppressesFlash:true,
  germWorkflow:germCiText(),
  repositoryImplementationIsPhysicalProof:false,
  needsWorkOwner:'aurum-system',
  humanActionRequired:false,
  humanActionInference:false
 };
}
function augment(){
 if(!base)return;
 const ledger=stateSnapshot();
 const merged={...base,recoveryLedgerAugmented:true,recoveryCheckpointLedgerEvidence:ledger.checkpointLedgerImplementation,recoveryJournalEvidence:ledger.journalImplementation,recoveryJournalHeadIntegrityEvidence:ledger.journalHeadIntegrityValidation,recoveryOfflineCarrierEvidence:ledger.offlineRecoveryCarrierEvidence,recoveryPreExecutionWriteGateEvidence:ledger.preExecutionRecoveryWriteGateEvidence,recoveryLedgerPhysicalProofInferred:false};
 window.__aurumRecoveryGuardianState=merged;
 window.__aurumRecoveryLedgerState=ledger;
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
 const implemented=ledgerImplementationPresent(),carried=bridgeCarriesLedger(),offline=offlineCarrier(),writeGate=preExecutionWriteGatePresent();
 const checkpoint=implemented&&carried?'Protected Germ has atomic pre-change checkpoints plus a hash-chained prepared/committed journal whose head validates the referenced record digest.':'Checkpoint/journal implementation is not fully verified from current repository evidence.';
 const fallback=offline.present?`A verified offline x86 recovery carrier is pinned to platform commit ${offline.pinned}; it may grow only an inactive candidate, prohibits live overwrite, and still requires Guardian health before promotion.`:'The offline recovery carrier is not fully verified from current repository evidence.';
 const gate=writeGate?'The Windows Tiny Seed writer now hard-fails closed unless a fresh terminal Hopper recovery-path v2 receipt proves the already-authorized system recovery path could not complete; a completed remote repair suppresses flashing and forces a Hopper health reread.':'The hard pre-execution write gate is not fully verified from current repository evidence.';
 const needs='Aurum/System still must obtain fresh terminal recovery-path evidence when a destructive handoff is actually attempted, then prove the resulting candidate on real Hopper hardware: boot, health-gated promotion, and forced-failure return to the prior Last Known Good state. Repository or CI implementation is not physical recovery proof.';
 box.innerHTML=`<b style="color:#cfd3df">Recovery safety ledger + offline fallback</b><br><b style="color:#8ce7b2">Frontiers Advancing:</b> ${esc(checkpoint)} ${esc(fallback)} ${esc(gate)}<br><b style="color:#bbb6ff">Needs Work → Aurum/System:</b> ${esc(needs)}<br><b style="color:#f0c76a">Your Actions:</b> None from this evidence layer. The offline carrier and pre-execution gate never grant destructive write, boot, promotion, or recovery authority; Action Ownership remains the authority boundary.<br><b style="color:#74d8d0">Germ CI:</b> ${esc(germCiText())}`;
}
async function refresh(){
 try{
  const [m,l,b,c,f,r]=await Promise.all([
   fetch(MANIFEST,{cache:'no-store'}),
   fetch(LEDGER,{cache:'no-store'}),
   fetch(BRIDGE,{cache:'no-store'}),
   fetch(CARRIER,{cache:'no-store'}),
   fetch(FLASH,{cache:'no-store'}),
   fetch(`${API}/actions/runs?branch=main&per_page=100`,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}})
  ]);
  if(!m.ok||!l.ok||!b.ok||!c.ok||!f.ok||!r.ok)throw new Error(`GitHub evidence HTTP ${m.status}/${l.status}/${b.status}/${c.status}/${f.status}/${r.status}`);
  const manifest=await m.json(),ledgerText=await l.text(),bridgeText=await b.text(),carrierText=await c.text(),flashText=await f.text(),runs=(await r.json()).workflow_runs||[];
  evidence={manifest,ledgerText,bridgeText,carrierText,flashText,run:newest(runs,GERM_WORKFLOW),error:''};
 }catch(e){evidence={manifest:null,ledgerText:'',bridgeText:'',carrierText:'',flashText:'',run:null,error:e?.message||'request failed'}}
 augment();
}
window.addEventListener('aurum-recovery-guardian-state',e=>{if(e.detail?.recoveryLedgerAugmented)return;base=e.detail||null;augment()});
document.addEventListener('click',e=>{if(e.target.closest?.('#systems [data-id="recovery"]'))setTimeout(patchDetail,60)});
new MutationObserver(()=>setTimeout(patchDetail,0)).observe(document.body,{childList:true,subtree:true});
refresh();setInterval(refresh,REFRESH);
})();