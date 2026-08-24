/* AURUM_TINYSEED_MEDIA_HANDOFF_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Refines Recovery Guardian at the physical-media boundary using the read-only
 * Tiny Seed USB candidate-discovery helper. It never authorizes media writes.
 */
(()=>{
'use strict';
if(window.__aurumTinySeedMediaHandoffV1)return;
window.__aurumTinySeedMediaHandoffV1=true;
const RAW='https://raw.githubusercontent.com/FormatX66/BoxBrain/main';
const HELPER=`${RAW}/Projects/Aurum/Germ/handoff/List-TinySeed-Candidates-Windows.ps1`;
const PROTECTED=`${RAW}/Projects/Aurum/Recovery/protected-media.json`;
let base=window.__aurumRecoveryGuardianState||null;
let helperState='checking';
let protectedSerials=[];
const helperProof=t=>[
  "BusType -eq 'USB'",
  'serial-missing',
  'boot-or-system',
  'read-only',
  'protected-recovery-media',
  'SAFE_TO_PREFLIGHT_ONLY',
  'AMBIGUOUS_MULTIPLE_ELIGIBLE'
].every(x=>String(t||'').includes(x));
const ready=s=>Boolean(s&&s.schema==='aurum-command-center-recovery-guardian-v1.7'&&s.tinySeedReleaseState==='READY_TO_FLASH'&&s.physicalHandoffRequiresSeparateTargetIdentity===true&&s.preflightRequiredBeforeDestructiveWrite===true&&s.physicalRecoveryProofInferred===false);
const actionText=s=>{
  if(!ready(s))return'No action from you right now. Wait for a verified READY_TO_FLASH handoff.';
  if(helperState!=='present')return'No action from you right now. READY_TO_FLASH is verified, but Aurum/System must restore and verify the read-only USB candidate-discovery helper before asking you to connect test media.';
  const guard=protectedSerials.length?` Do not use protected recovery serial${protectedSerials.length>1?'s':''} ${protectedSerials.join(', ')}.`:'';
  const sha=String(s?.tinySeedX86Sha256||'the verified x86 SHA-256');
  return`Connect one disposable/test USB that is not a boot/system disk and is not protected recovery media.${guard} Leave it connected. Aurum will enumerate USB media read-only and fail closed if the serial is missing, the disk is boot/system or read-only, the serial is protected, or more than one eligible target exists. Discovery never authorizes a write. Do not authorize a destructive write until the guarded dry-run reports READY_FOR_EXPLICIT_WRITE for that exact serial and verifies x86 SHA-256 ${sha}. Then explicitly authorize that exact write. Do not remove or boot the media until Aurum reports full raw readback verification passed.`;
};
function enrich(){
  if(!base)return;
  const humanReady=ready(base)&&helperState==='present';
  const s={...base,
    mediaHandoffAugmented:true,
    tinySeedUsbCandidateDiscoveryEvidence:helperState==='present'?'read-only-serial-system-readonly-protected-ambiguity-fail-closed':'not-verified',
    usbCandidateDiscoveryCanWrite:false,
    usbCandidateDiscoveryCreatesHumanAction:false,
    readyToFlashCreatesHumanAction:humanReady,
    humanActionRequired:humanReady,
    humanActionEvidence:humanReady?'ready-to-flash-plus-read-only-target-identity-preflight':'none'
  };
  window.__aurumRecoveryGuardianState=s;
  window.__aurumTinySeedMediaHandoffState={schema:'aurum-command-center-tinyseed-media-handoff-v1',helperState,humanActionRequired:humanReady,protectedSerialCount:protectedSerials.length,writeAuthorityInferred:false};
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
  proof.style.cssText='margin:8px 0;padding:8px 9px;border:1px solid #343164;border-radius:10px;background:#111522;color:#929db0;font-size:10px;line-height:1.45';
  proof.innerHTML=`<b style="color:#cfd3df">Read-only media discovery</b><br>${helperState==='present'?'Verified helper present: exact USB serial + boot/system + read-only + protected-media checks; ambiguous eligible targets fail closed. Discovery cannot write.':'Not verified. Aurum/System must restore this guard before physical handoff can create Your Actions.'}`;
  const owner=guide.querySelector('.recovery-owner');
  if(owner)owner.innerHTML=`<b>Your Actions:</b> ${actionText(base).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}`;
}
async function refresh(){
  helperState='checking';
  try{
    const [h,p]=await Promise.all([fetch(HELPER,{cache:'no-store'}),fetch(PROTECTED,{cache:'no-store'})]);
    const text=h.ok?await h.text():'';
    helperState=helperProof(text)?'present':'missing';
    if(p.ok){const j=await p.json();protectedSerials=(Array.isArray(j?.devices)?j.devices:[]).filter(x=>x?.protected===true).map(x=>String(x.serial||'').trim()).filter(Boolean)}
  }catch(_){helperState='unavailable'}
  enrich();
}
window.addEventListener('aurum-recovery-guardian-state',e=>{if(e.detail?.mediaHandoffAugmented)return;base=e.detail||null;enrich()});
document.addEventListener('click',e=>{if(e.target.closest?.('#systems [data-id="recovery"]'))setTimeout(patchDetail,60)});
new MutationObserver(()=>setTimeout(patchDetail,0)).observe(document.body,{childList:true,subtree:true});
refresh();setInterval(refresh,300000);
})();
