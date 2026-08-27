/* AURUM_TINYSEED_PHYSICAL_ACCEPTANCE_V1_1_CANONICAL
 * AURUM_TINYSEED_PHYSICAL_ACCEPTANCE_V1_CANONICAL compatibility marker.
 * Canonical website owner: FormatX66/ClusterSites.
 * Fail-closed overlay for post-flash physical acceptance. A verified raw readback
 * proves media integrity only; a newer exact-release physical failure quarantines
 * the candidate and suppresses stale READY_TO_BOOT interpretation/human action.
 */
(()=>{
'use strict';
if(window.__aurumTinySeedPhysicalAcceptanceV1)return;
window.__aurumTinySeedPhysicalAcceptanceV1=true;
const RAW='https://raw.githubusercontent.com/FormatX66/BoxBrain/main';
const ACCEPTANCE=`${RAW}/Projects/Aurum/Recovery/latest-tinyseed-physical-acceptance.json`;
const RELEASE=`${RAW}/Projects/Aurum/Release/latest-tinyseed-handoff.json`;
const FLASH=`${RAW}/Projects/Aurum/Recovery/latest-tinyseed-flash-receipt.json`;
const REFRESH=60*1000;
let acceptance=null,release=null,flash=null;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const t=s=>{const n=Date.parse(s||'');return Number.isFinite(n)?n:0};
const exactRelease=()=>Boolean(
  acceptance?.schema==='aurum-tinyseed-physical-acceptance-v1'&&
  release?.schema==='aurum-tinyseed-handoff-v1'&&
  String(acceptance?.release?.source_commit||'').toLowerCase()===String(release?.source_commit||'').toLowerCase()&&
  String(acceptance?.release?.x86_sha256||'').toLowerCase()===String(release?.artifacts?.x86?.sha256||'').toLowerCase()
);
const exactFlash=()=>Boolean(
  exactRelease()&&flash?.schema==='aurum-tinyseed-flash-request-receipt-v1'&&
  flash?.state==='READY_TO_BOOT'&&flash?.raw_readback_verified===true&&flash?.write_authority_consumed===true&&
  String(flash?.source_commit||'').toLowerCase()===String(release?.source_commit||'').toLowerCase()&&
  String(flash?.image_sha256||'').toLowerCase()===String(release?.artifacts?.x86?.sha256||'').toLowerCase()
);
const failedPhysicalAcceptance=()=>Boolean(
  exactFlash()&&
  acceptance?.state==='QUARANTINED_PHYSICAL_ACCEPTANCE_FAILED'&&
  acceptance?.candidate_quarantined===true&&
  acceptance?.physical_acceptance===false&&
  acceptance?.physical_ready_to_boot===false&&
  acceptance?.supersedes_prior_physical_readiness===true&&
  t(acceptance?.observed_at_utc)>t(flash?.observed_at_utc)
);
function publish(){
  const failed=failedPhysicalAcceptance();
  const blockers=Array.isArray(acceptance?.release_blockers)?acceptance.release_blockers:[];
  window.__aurumTinySeedPhysicalAcceptanceState={
    schema:'aurum-command-center-tinyseed-physical-acceptance-v1.1',
    currentReleaseMatched:exactRelease(),
    matchingRawReadbackReceipt:exactFlash(),
    physicalAcceptanceFailed:failed,
    candidateQuarantined:failed,
    physicalReadyToBoot:failed?false:null,
    mediaIntegrityStillProven:exactFlash(),
    releaseBlockers:failed?blockers:[],
    readyToBootSupersededForPhysicalReadiness:failed,
    writeAuthority:false,
    promotionAuthority:false,
    physicalActionAuthority:false,
    humanActionRequired:false,
    humanActionInference:false,
    needsWorkOwner:failed?'aurum-system':null
  };
  window.dispatchEvent(new CustomEvent('aurum-tinyseed-physical-acceptance-state',{detail:window.__aurumTinySeedPhysicalAcceptanceState}));
}
function patch(){
  if(!failedPhysicalAcceptance())return;
  const card=document.querySelector('#systems [data-id="recovery"]');
  if(card){
    const pill=card.querySelector('.pill');
    if(pill){if(pill.className!=='pill failed')pill.className='pill failed';if(pill.textContent!=='Needs Work')pill.textContent='Needs Work'}
    const ev=card.querySelector('.evidence');
    const evText='Current Tiny Seed media passed raw readback, but physical acceptance failed; candidate quarantined.';
    if(ev&&ev.textContent!==evText)ev.textContent=evText;
  }
  if(!card||card.getAttribute('aria-expanded')!=='true')return;
  const guide=document.querySelector('#detail .recovery-guide');if(!guide)return;
  let box=guide.querySelector('.tinyseed-physical-acceptance-proof');
  if(!box){box=document.createElement('div');box.className='tinyseed-physical-acceptance-proof';const media=guide.querySelector('.tinyseed-media-handoff-proof');if(media)media.insertAdjacentElement('afterend',box);else guide.prepend(box)}
  box.style.cssText='margin:8px 0;padding:8px 9px;border:1px solid #5c3540;border-radius:10px;background:#191319;color:#a9a2ab;font-size:10px;line-height:1.5';
  const source=String(release?.source_commit||'').slice(0,12),sha=String(release?.artifacts?.x86?.sha256||'').slice(0,12);
  const blockers=(acceptance?.release_blockers||[]).join(', ')||'physical acceptance failure';
  const graphics=acceptance?.graphics?.required_behavior||'repair graphics boot/fallback and prove it is nonrecursive';
  const wifi=(acceptance?.wifi?.required_diff||[]).join(', ')||'Wi-Fi image/startup path';
  const html=`<b style="color:#ffd0d7">Tiny Seed physical acceptance · CANDIDATE QUARANTINED</b><br><b style="color:#8ce7b2">Frontiers Advancing:</b> Exact current media integrity remains proven by the matching full raw-readback receipt (${esc(source)} · x86 ${esc(sha)}…), and post-flash physical acceptance now overrides media-only READY_TO_BOOT semantics.<br><b style="color:#bbb6ff">Needs Work → Aurum/System:</b> Physical release blockers: ${esc(blockers)}. Graphics must converge on ${esc(graphics)}. Wi-Fi repair must compare and re-prove ${esc(wifi)}. Build a new exact-release candidate, re-run virtual gates, guarded flash/readback, then require physical Wi-Fi association plus stable graphics/fallback before restoring physical readiness.<br><b style="color:#f0c76a">Your Actions:</b> none. Do not boot, reflash, reconnect, or authorize media from the stale READY_TO_BOOT state. Wait for a new exact-release physical handoff after Aurum/System clears the quarantined candidate.`;
  if(box.innerHTML!==html)box.innerHTML=html;
  const owner=guide.querySelector('.recovery-owner');
  const ownerHtml='<b>Your Actions:</b> None. The current Tiny Seed candidate is quarantined after physical acceptance failure; repair and re-proof are Aurum/System work.';
  if(owner&&owner.innerHTML!==ownerHtml)owner.innerHTML=ownerHtml;
}
async function j(u){try{const r=await fetch(`${u}?t=${Date.now()}`,{cache:'no-store'});return r.ok?await r.json():null}catch(_){return null}}
async function refresh(){[acceptance,release,flash]=await Promise.all([j(ACCEPTANCE),j(RELEASE),j(FLASH)]);publish();patch()}
window.addEventListener('aurum-tinyseed-media-handoff-state',()=>setTimeout(patch,0));
window.addEventListener('aurum-recovery-guardian-state',()=>setTimeout(patch,0));
document.addEventListener('click',e=>{if(e.target.closest?.('#systems [data-id="recovery"]'))setTimeout(patch,60)});
new MutationObserver(()=>setTimeout(patch,0)).observe(document.body,{childList:true,subtree:true});
refresh();setInterval(refresh,REFRESH);
})();
