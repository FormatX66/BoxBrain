/* AURUM_TINYSEED_MEDIA_HANDOFF_V1_2_CANONICAL
 * AURUM_TINYSEED_MEDIA_HANDOFF_V1_CANONICAL compatibility marker.
 * Canonical website owner: FormatX66/ClusterSites.
 * Refines Recovery Guardian at the physical-media boundary using read-only
 * USB discovery, exact guarded preflight, one-shot write authority, and
 * raw-readback proof. Evidence can retire a human task; it never invents one.
 */
(()=>{
'use strict';
if(window.__aurumTinySeedMediaHandoffV1)return;
window.__aurumTinySeedMediaHandoffV1=true;
const RAW='https://raw.githubusercontent.com/FormatX66/BoxBrain/main';
const HELPER=`${RAW}/Projects/Aurum/Germ/handoff/List-TinySeed-Candidates-Windows.ps1`;
const PROTECTED=`${RAW}/Projects/Aurum/Recovery/protected-media.json`;
const PREFLIGHT=`${RAW}/Projects/Aurum/Recovery/latest-tinyseed-physical-preflight.json`;
const FLASH_REQUEST=`${RAW}/Projects/Aurum/Recovery/tinyseed-flash-request.json`;
const FLASH_RECEIPT=`${RAW}/Projects/Aurum/Recovery/latest-tinyseed-flash-receipt.json`;
const REFRESH=60*1000;
let base=window.__aurumRecoveryGuardianState||null;
let helperState='checking';
let protectedSerials=[];
let preflight=null;
let flashRequest=null;
let flashReceipt=null;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const helperProof=t=>[
  "BusType -eq 'USB'",
  'serial-missing',
  'boot-or-system',
  'read-only',
  'protected-recovery-media',
  'SAFE_TO_PREFLIGHT_ONLY',
  'AMBIGUOUS_MULTIPLE_ELIGIBLE'
].every(x=>String(t||'').includes(x));
const ready=s=>Boolean(
  s&&s.schema==='aurum-command-center-recovery-guardian-v1.7'&&
  s.tinySeedReleaseState==='READY_TO_FLASH'&&
  s.physicalHandoffRequiresSeparateTargetIdentity===true&&
  s.preflightRequiredBeforeDestructiveWrite===true&&
  s.physicalRecoveryProofInferred===false
);
const releaseMatches=(s,p)=>Boolean(
  ready(s)&&p?.schema==='aurum-tinyseed-physical-preflight-v1'&&
  p?.state==='READY_FOR_GUARDED_FLASH_PREFLIGHT'&&
  p?.release?.state==='READY_TO_FLASH'&&
  String(p?.release?.source_commit||'').toLowerCase()===String(s?.tinySeedReleaseSourceCommit||'').toLowerCase()&&
  String(p?.release?.x86_sha256||'').toLowerCase()===String(s?.tinySeedX86Sha256||'').toLowerCase()&&
  p?.usb_discovery?.selection_state==='UNIQUE_SAFE_TO_PREFLIGHT_ONLY'&&
  Number(p?.usb_discovery?.eligible_count)===1&&
  p?.usb_discovery?.candidate?.is_boot===false&&
  p?.usb_discovery?.candidate?.is_system===false&&
  p?.usb_discovery?.candidate?.is_read_only===false&&
  p?.usb_discovery?.candidate?.protected===false&&
  p?.write_authority===false&&
  p?.destructive_action_performed===false
);
const requestMatches=(p,r)=>{
  if(!p||!r||r?.schema!=='aurum-tinyseed-flash-request-v1'||r?.state!=='AUTHORIZED_ONCE'||r?.write_authority!==true||r?.confirmation!=='FLASH_TINY_SEED_TEST_USB')return false;
  const expiry=Date.parse(r?.expires_at_utc||'');
  if(!Number.isFinite(expiry)||Date.now()>expiry)return false;
  return String(r?.seed_sha||'').toLowerCase()===String(p?.release?.source_commit||'').toLowerCase()&&
    String(r?.image_sha256||'').toLowerCase()===String(p?.release?.x86_sha256||'').toLowerCase()&&
    String(r?.discovery_request_id||'')===String(p?.usb_discovery?.request_id||'')&&
    String(r?.usb?.model||'')===String(p?.usb_discovery?.candidate?.model||'')&&
    Number(r?.usb?.size_bytes)===Number(p?.usb_discovery?.candidate?.size_bytes)&&
    String(r?.usb?.serial_sha256||'').toLowerCase()===String(p?.usb_discovery?.candidate?.serial_sha256||'').toLowerCase();
};
const receiptMatches=(r,q)=>Boolean(
  r&&q&&q?.schema==='aurum-tinyseed-flash-request-receipt-v1'&&
  q?.state==='READY_TO_BOOT'&&q?.raw_readback_verified===true&&q?.write_authority_consumed===true&&
  String(q?.request_id||'')===String(r?.request_id||'')&&
  String(q?.source_commit||'').toLowerCase()===String(r?.seed_sha||'').toLowerCase()&&
  String(q?.image_sha256||'').toLowerCase()===String(r?.image_sha256||'').toLowerCase()
);
function phase(s){
  if(!ready(s))return'WAITING_FOR_VERIFIED_HANDOFF';
  if(helperState!=='present')return'DISCOVERY_GUARD_NOT_VERIFIED';
  if(!releaseMatches(s,preflight))return'WAITING_FOR_CURRENT_UNIQUE_PREFLIGHT';
  if(!requestMatches(preflight,flashRequest))return'WAITING_FOR_EXPLICIT_WRITE_AUTHORITY';
  if(receiptMatches(flashRequest,flashReceipt))return'READY_TO_BOOT';
  return'AUTHORIZED_FLASH_PENDING';
}
function actionText(s){
  const p=phase(s);
  if(p==='WAITING_FOR_VERIFIED_HANDOFF')return'None. Wait for a verified READY_TO_FLASH handoff.';
  if(p==='DISCOVERY_GUARD_NOT_VERIFIED')return'None. Aurum/System must restore and verify read-only USB discovery before asking you to touch test media.';
  if(p==='WAITING_FOR_CURRENT_UNIQUE_PREFLIGHT'){
    const guard=protectedSerials.length?` Do not use protected recovery serial${protectedSerials.length>1?'s':''} ${protectedSerials.join(', ')}.`:'';
    return`Connect one disposable/test USB that is not a boot/system disk and is not protected recovery media.${guard} Leave it connected for read-only discovery. Do not authorize a write yet.`;
  }
  if(p==='WAITING_FOR_EXPLICIT_WRITE_AUTHORITY'){
    const model=String(preflight?.usb_discovery?.candidate?.model||'the verified test USB');
    const source=String(preflight?.release?.source_commit||s?.tinySeedReleaseSourceCommit||'the verified release');
    const sha=String(preflight?.release?.x86_sha256||s?.tinySeedX86Sha256||'the verified x86 SHA-256');
    return`Explicitly authorize one guarded Tiny Seed flash of the currently selected ${model}, bound to source ${source} and x86 SHA-256 ${sha}. Keep that USB connected and unchanged. The authorization is one-shot; any release or device-identity change invalidates it. Do not remove or boot the media until Aurum reports the full raw readback passed.`;
  }
  if(p==='AUTHORIZED_FLASH_PENDING')return'None. Exact one-shot write authority is already present for the verified test USB. Leave that USB connected. Do not remove it, boot it, or re-authorize another write while Aurum/System performs the guarded flash and full raw-readback verification.';
  if(p==='READY_TO_BOOT')return'None assigned by this evidence layer. The guarded write and raw readback are verified; wait for a separate verified Hopper boot-handoff instruction before moving or booting the media.';
  return'None.';
}
function frontierText(s){
  const p=phase(s);
  if(p==='AUTHORIZED_FLASH_PENDING'){
    const m=String(flashRequest?.usb?.model||preflight?.usb_discovery?.candidate?.model||'verified test USB');
    const sha=String(flashRequest?.image_sha256||preflight?.release?.x86_sha256||s?.tinySeedX86Sha256||'unknown');
    return`Exact physical target preflight is proven (${m}); one-shot AUTHORIZED_ONCE authority is bound to the current Tiny Seed source and x86 SHA-256 ${sha}.`;
  }
  if(p==='READY_TO_BOOT')return'Guarded Tiny Seed write completed and the full raw readback is verified; the one-shot write authority was consumed.';
  if(releaseMatches(s,preflight))return'Current READY_TO_FLASH release is bound to one unique read-only-discovered USB candidate with boot/system/read-only/protected-media checks passed and zero write authority.';
  if(ready(s)&&helperState==='present')return'Current READY_TO_FLASH release and the fail-closed read-only USB discovery guard are verified.';
  return'No newer physical-media frontier is proven by this evidence layer.';
}
function needsText(s){
  const p=phase(s);
  if(p==='AUTHORIZED_FLASH_PENDING')return'Aurum/System must consume the one-shot request, re-prove the exact live USB identity immediately before write, verify the exact handoff/image hash, perform the guarded write once, complete full raw readback, and publish a matching READY_TO_BOOT receipt. Physical Hopper boot and Guardian forced-rollback proof remain separate later gates.';
  if(p==='READY_TO_BOOT')return'Aurum/System still needs physical Hopper boot, Repair/Reseed health/promotion-or-rollback evidence, forced-LKG rollback proof, and remaining Pi physical recovery proof. This component does not infer a boot instruction.';
  if(p==='WAITING_FOR_EXPLICIT_WRITE_AUTHORITY')return'Aurum/System must hold at zero write authority and preserve the current exact-target preflight. After explicit human authorization, it must re-prove live USB identity, verify the exact release/image hash, perform the guarded write once, complete full raw readback, and publish a matching READY_TO_BOOT receipt.';
  if(p==='WAITING_FOR_CURRENT_UNIQUE_PREFLIGHT')return'Aurum/System must discover exactly one eligible USB read-only and bind it to the current release before destructive authority can exist.';
  if(p==='DISCOVERY_GUARD_NOT_VERIFIED')return'Aurum/System must restore the fail-closed discovery guard.';
  return'Aurum/System must complete the current release/handoff evidence before physical media work is actionable.';
}
function enrich(){
  if(!base)return;
  const p=phase(base);
  const connectHuman=p==='WAITING_FOR_CURRENT_UNIQUE_PREFLIGHT';
  const authorizeHuman=p==='WAITING_FOR_EXPLICIT_WRITE_AUTHORITY';
  const humanAction=connectHuman||authorizeHuman;
  const s={...base,
    mediaHandoffAugmented:true,
    tinySeedUsbCandidateDiscoveryEvidence:helperState==='present'?'read-only-serial-system-readonly-protected-ambiguity-fail-closed':'not-verified',
    tinySeedPhysicalPreflightState:releaseMatches(base,preflight)?'UNIQUE_SAFE_TO_PREFLIGHT_ONLY':'not-current-or-not-verified',
    tinySeedFlashRequestState:requestMatches(preflight,flashRequest)?'AUTHORIZED_ONCE':'none-or-not-current',
    tinySeedFlashReceiptState:receiptMatches(flashRequest,flashReceipt)?'READY_TO_BOOT':'not-verified',
    tinySeedPhysicalHandoffPhase:p,
    usbCandidateDiscoveryCanWrite:false,
    usbCandidateDiscoveryCreatesHumanAction:false,
    writeAuthorityPresent:requestMatches(preflight,flashRequest),
    writeAuthorityCanCreateHumanAction:false,
    explicitWriteAuthorityRequired:authorizeHuman,
    explicitWriteAuthorityCreatesHumanAction:authorizeHuman,
    authorizedWritePendingCreatesHumanAction:false,
    fullRawReadbackRequired:true,
    readyToFlashCreatesHumanAction:humanAction,
    humanActionRequired:humanAction,
    humanActionEvidence:connectHuman?'ready-to-flash-needs-one-disposable-usb-for-read-only-discovery':authorizeHuman?'current-exact-target-preflight-needs-explicit-one-shot-write-authority':'none'
  };
  window.__aurumRecoveryGuardianState=s;
  window.__aurumTinySeedMediaHandoffState={
    schema:'aurum-command-center-tinyseed-media-handoff-v1.2',
    helperState,
    phase:p,
    preflightState:s.tinySeedPhysicalPreflightState,
    flashRequestState:s.tinySeedFlashRequestState,
    flashReceiptState:s.tinySeedFlashReceiptState,
    humanActionRequired:humanAction,
    humanActionEvidence:s.humanActionEvidence,
    protectedSerialCount:protectedSerials.length,
    writeAuthorityPresent:s.writeAuthorityPresent,
    explicitWriteAuthorityRequired:authorizeHuman,
    writeAuthorityInferred:false,
    fullRawReadbackRequired:true
  };
  window.dispatchEvent(new CustomEvent('aurum-recovery-guardian-state',{detail:s}));
  window.dispatchEvent(new CustomEvent('aurum-tinyseed-media-handoff-state',{detail:window.__aurumTinySeedMediaHandoffState}));
  patchDetail();
}
function patchDetail(){
  const c=document.querySelector('#systems [data-id="recovery"]');
  if(!c||c.getAttribute('aria-expanded')!=='true')return;
  const guide=document.querySelector('#detail .recovery-guide');
  if(!guide)return;
  let proof=guide.querySelector('.tinyseed-media-handoff-proof');
  if(!proof){proof=document.createElement('div');proof.className='tinyseed-media-handoff-proof';const first=guide.querySelector('.recovery-proof');if(first)first.insertAdjacentElement('afterend',proof);else guide.prepend(proof)}
  proof.style.cssText='margin:8px 0;padding:8px 9px;border:1px solid #343164;border-radius:10px;background:#111522;color:#929db0;font-size:10px;line-height:1.5';
  const p=phase(base);
  proof.innerHTML=`<b style="color:#cfd3df">Tiny Seed media handoff · ${esc(p.replaceAll('_',' '))}</b><br><b style="color:#8ce7b2">Frontiers Advancing:</b> ${esc(frontierText(base))}<br><b style="color:#bbb6ff">Needs Work → Aurum/System:</b> ${esc(needsText(base))}<br><b style="color:#f0c76a">Your Actions:</b> ${esc(actionText(base))}`;
  const owner=guide.querySelector('.recovery-owner');
  if(owner)owner.innerHTML=`<b>Your Actions:</b> ${esc(actionText(base))}`;
}
async function fetchJson(url){
  try{const r=await fetch(`${url}?t=${Date.now()}`,{cache:'no-store'});if(!r.ok)return null;return await r.json()}catch(_){return null}
}
async function refresh(){
  helperState='checking';
  try{
    const [h,p,pf,fr,rc]=await Promise.all([
      fetch(HELPER,{cache:'no-store'}),
      fetchJson(PROTECTED),
      fetchJson(PREFLIGHT),
      fetchJson(FLASH_REQUEST),
      fetchJson(FLASH_RECEIPT)
    ]);
    const text=h.ok?await h.text():'';
    helperState=helperProof(text)?'present':'missing';
    protectedSerials=(Array.isArray(p?.devices)?p.devices:[]).filter(x=>x?.protected===true).map(x=>String(x.serial||'').trim()).filter(Boolean);
    preflight=pf;flashRequest=fr;flashReceipt=rc;
  }catch(_){helperState='unavailable'}
  enrich();
}
window.addEventListener('aurum-recovery-guardian-state',e=>{if(e.detail?.mediaHandoffAugmented)return;base=e.detail||null;enrich()});
document.addEventListener('click',e=>{if(e.target.closest?.('#systems [data-id="recovery"]'))setTimeout(patchDetail,60)});
new MutationObserver(()=>setTimeout(patchDetail,0)).observe(document.body,{childList:true,subtree:true});
refresh();setInterval(refresh,REFRESH);
})();
