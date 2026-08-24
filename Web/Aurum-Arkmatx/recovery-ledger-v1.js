/* AURUM_RECOVERY_LEDGER_V1_CANONICAL_PROJECTION
 * Canonical website owner: FormatX66/ClusterSites.
 * Public projection only. Augments the existing expandable Recovery Guardian card;
 * it does not create a new dashboard box or any human authority.
 */
(()=>{
'use strict';
if(window.__aurumRecoveryLedgerV1)return;
window.__aurumRecoveryLedgerV1=true;
const RAW='https://raw.githubusercontent.com/FormatX66/BoxBrain/main';
const API='https://api.github.com/repos/FormatX66/BoxBrain';
const MANIFEST=`${RAW}/Projects/Aurum/Germ/GENETICS.json`;
const LEDGER=`${RAW}/Projects/Aurum/Germ/recovery_ledger.py`;
const BRIDGE=`${RAW}/Projects/Aurum/Germ/bridge.py`;
const GERM_WORKFLOW='Aurum Reseed Germ';
const REFRESH=5*60*1000;
let base=window.__aurumRecoveryGuardianState||null;
let evidence={manifest:null,ledgerText:'',bridgeText:'',run:null,error:''};
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
const germCiText=()=>!evidence.run?'no current workflow evidence':['queued','in_progress','waiting','requested','pending'].includes(String(evidence.run.status||''))?String(evidence.run.status):String(evidence.run.conclusion||evidence.run.status||'unknown');
function stateSnapshot(){
 const implemented=ledgerImplementationPresent(),carried=bridgeCarriesLedger();
 return{
  schema:'aurum-command-center-recovery-ledger-v1',
  canonicalWebsiteRepo:'FormatX66/ClusterSites',
  publicProjection:'FormatX66/BoxBrain:Web/Aurum-Arkmatx/recovery-ledger-v1.js',
  checkpointLedgerImplementation:implemented?'atomic-prechange-checkpoints-present':'not-verified',
  journalImplementation:implemented?'hash-chained-prepared-and-committed-journal-present':'not-verified',
  journalHeadIntegrityValidation:implemented?'record-digest-validated-before-head-acceptance':'not-verified',
  lkgPreservationRecorded:implemented?'checkpoint-records-lkg-preserved':'not-verified',
  installedGermCarrier:carried?'bridge-carries-recovery-ledger':'not-verified',
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
 const merged={...base,recoveryLedgerAugmented:true,recoveryCheckpointLedgerEvidence:ledger.checkpointLedgerImplementation,recoveryJournalEvidence:ledger.journalImplementation,recoveryJournalHeadIntegrityEvidence:ledger.journalHeadIntegrityValidation,recoveryLedgerPhysicalProofInferred:false};
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
 const implemented=ledgerImplementationPresent(),carried=bridgeCarriesLedger();
 const frontier=implemented&&carried?'Protected Germ now has atomic pre-change checkpoints plus a hash-chained prepared/committed change journal; the journal head validates the referenced record digest before accepting continuity. Checkpoints record A/B roles, active link, recoverable LKG presence, and a SHA-256 receipt.':'Checkpoint/journal implementation is not fully verified from current repository evidence.';
 const needs='Aurum/System must still prove this ledger on a real node: a meaningful mutation must create the checkpoint + prepared/committed journal records, survive reboot/recovery with chain integrity intact, and a forced candidate failure must restore the prior Last Known Good state. Repository or CI implementation is not physical recovery proof.';
 box.innerHTML=`<b style="color:#cfd3df">Recovery checkpoint ledger</b><br><b style="color:#8ce7b2">Frontiers Advancing:</b> ${esc(frontier)}<br><b style="color:#bbb6ff">Needs Work → Aurum/System:</b> ${esc(needs)}<br><b style="color:#f0c76a">Your Actions:</b> None from this evidence layer. Checkpoint/journal software never grants destructive write, boot, promotion, or recovery authority. Existing physical-media authority remains governed by the separate Tiny Seed handoff evidence.<br><b style="color:#74d8d0">Germ CI:</b> ${esc(germCiText())}`;
}
async function refresh(){
 try{
  const [m,l,b,r]=await Promise.all([
   fetch(MANIFEST,{cache:'no-store'}),
   fetch(LEDGER,{cache:'no-store'}),
   fetch(BRIDGE,{cache:'no-store'}),
   fetch(`${API}/actions/runs?branch=main&per_page=100`,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}})
  ]);
  if(!m.ok||!l.ok||!b.ok||!r.ok)throw new Error(`GitHub evidence HTTP ${m.status}/${l.status}/${b.status}/${r.status}`);
  const manifest=await m.json(),ledgerText=await l.text(),bridgeText=await b.text(),runs=(await r.json()).workflow_runs||[];
  evidence={manifest,ledgerText,bridgeText,run:newest(runs,GERM_WORKFLOW),error:''};
 }catch(e){evidence={manifest:null,ledgerText:'',bridgeText:'',run:null,error:e?.message||'request failed'}}
 augment();
}
window.addEventListener('aurum-recovery-guardian-state',e=>{if(e.detail?.recoveryLedgerAugmented)return;base=e.detail||null;augment()});
document.addEventListener('click',e=>{if(e.target.closest?.('#systems [data-id="recovery"]'))setTimeout(patchDetail,60)});
new MutationObserver(()=>setTimeout(patchDetail,0)).observe(document.body,{childList:true,subtree:true});
refresh();setInterval(refresh,REFRESH);
})();
