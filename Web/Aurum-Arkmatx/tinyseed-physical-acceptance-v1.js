/* AURUM_TINYSEED_PHYSICAL_ACCEPTANCE_V1_2_CANONICAL
 * AURUM_TINYSEED_PHYSICAL_ACCEPTANCE_V1_1_CANONICAL compatibility marker.
 * AURUM_TINYSEED_PHYSICAL_ACCEPTANCE_V1_CANONICAL compatibility marker.
 * Canonical website owner: FormatX66/ClusterSites.
 * Fail-closed overlay for post-flash physical acceptance and recovery-strategy truth.
 * A verified raw readback proves media integrity only; newer physical failure can
 * quarantine the candidate, and an explicit full-seed Clean Regrow pivot can retire
 * Tiny Seed patching as the primary recovery path without granting any new authority.
 */
(()=>{
'use strict';
if(window.__aurumTinySeedPhysicalAcceptanceV1)return;
window.__aurumTinySeedPhysicalAcceptanceV1=true;
const RAW='https://raw.githubusercontent.com/FormatX66/BoxBrain/main';
const ACCEPTANCE=`${RAW}/Projects/Aurum/Recovery/latest-tinyseed-physical-acceptance.json`;
const RELEASE=`${RAW}/Projects/Aurum/Release/latest-tinyseed-handoff.json`;
const FLASH=`${RAW}/Projects/Aurum/Recovery/latest-tinyseed-flash-receipt.json`;
const STRATEGY=`${RAW}/Projects/Aurum/Recovery/latest-seed-recovery-strategy.json`;
const REFRESH=60*1000;
let acceptance=null,release=null,flash=null,strategy=null;
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
const fullSeedPivot=()=>Boolean(
  failedPhysicalAcceptance()&&
  strategy?.schema==='aurum-seed-recovery-strategy-v1'&&
  strategy?.state==='FULL_SEED_CLEAN_REGROW_PREPARED_ROUTE_REPAIR_REQUIRED'&&
  strategy?.strategy==='full_seed_installer_clean_regrow'&&
  strategy?.tinyseed_primary_recovery===false&&
  strategy?.current_tinyseed_candidate_quarantined===true
);
const retiredRouteHeld=()=>Boolean(
  fullSeedPivot()&&
  strategy?.flash_route?.current_historical_workflow_state==='RETIRED_REFUSAL_ONLY'&&
  strategy?.flash_route?.legacy_static_authority_valid===false&&
  strategy?.execution_boundary?.route_repair_required===true
);
function publish(){
  const failed=failedPhysicalAcceptance(),pivot=fullSeedPivot(),routeHeld=retiredRouteHeld();
  const blockers=Array.isArray(acceptance?.release_blockers)?acceptance.release_blockers:[];
  window.__aurumTinySeedPhysicalAcceptanceState={
    schema:'aurum-command-center-tinyseed-physical-acceptance-v1.2',
    currentReleaseMatched:exactRelease(),
    matchingRawReadbackReceipt:exactFlash(),
    physicalAcceptanceFailed:failed,
    candidateQuarantined:failed,
    physicalReadyToBoot:failed?false:null,
    mediaIntegrityStillProven:exactFlash(),
    releaseBlockers:failed?blockers:[],
    readyToBootSupersededForPhysicalReadiness:failed,
    recoveryStrategy:pivot?'full-seed-clean-regrow':null,
    tinySeedPrimaryRecovery:pivot?false:null,
    legacyPc01FlashRouteRetired:routeHeld,
    routeRepairRequired:routeHeld,
    controllerIngressVerified:pivot?strategy?.objective?.controller_ingress_verified===true:null,
    currentPhysicalFlashVerified:pivot?strategy?.objective?.current_physical_flash_verified===true:null,
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
  const pivot=fullSeedPivot(),routeHeld=retiredRouteHeld();
  const card=document.querySelector('#systems [data-id="recovery"]');
  if(card){
    const pill=card.querySelector('.pill');
    if(pill){if(pill.className!=='pill failed')pill.className='pill failed';if(pill.textContent!=='Needs Work')pill.textContent='Needs Work'}
    const ev=card.querySelector('.evidence');
    const evText=pivot?'Tiny Seed physical acceptance failed; candidate quarantined. Full-seed Clean Regrow is now the primary recovery path.':'Current Tiny Seed media passed raw readback, but physical acceptance failed; candidate quarantined.';
    if(ev&&ev.textContent!==evText)ev.textContent=evText;
  }
  if(!card||card.getAttribute('aria-expanded')!=='true')return;
  const guide=document.querySelector('#detail .recovery-guide');if(!guide)return;
  let box=guide.querySelector('.tinyseed-physical-acceptance-proof');
  if(!box){box=document.createElement('div');box.className='tinyseed-physical-acceptance-proof';const media=guide.querySelector('.tinyseed-media-handoff-proof');if(media)media.insertAdjacentElement('afterend',box);else guide.prepend(box)}
  box.style.cssText='margin:8px 0;padding:8px 9px;border:1px solid #5c3540;border-radius:10px;background:#191319;color:#a9a2ab;font-size:10px;line-height:1.5';
  const source=String(release?.source_commit||'').slice(0,12),sha=String(release?.artifacts?.x86?.sha256||'').slice(0,12);
  const blockers=(acceptance?.release_blockers||[]).join(', ')||'physical acceptance failure';
  let html;
  if(pivot){
    const modes=(strategy?.full_seed_contract?.installer_modes||['normal_install','clean_regrow']).join(' / ');
    const preserve=(strategy?.full_seed_contract?.preserve_before_wipe||[]).join(', ');
    const acceptanceGates=(strategy?.full_seed_contract?.physical_acceptance_required||[]).join(', ');
    const target=strategy?.flash_route?.target_guard||'fresh exact removable target only';
    html=`<b style="color:#ffd0d7">Recovery strategy · FULL-SEED CLEAN REGROW</b><br><b style="color:#8ce7b2">Frontiers Advancing:</b> The failed Tiny Seed candidate stays quarantined, while its matching raw-readback receipt is retained only as media-integrity evidence (${esc(source)} · x86 ${esc(sha)}…). Recovery has pivoted to a full Aurum installer with ${esc(modes)} modes. Historical PC-01 flash proof remains useful route evidence, but the old persistent-authority workflow is now retired/refusal-only.${routeHeld?' The dashboard therefore will not treat that legacy route as executable authority.':''}<br><b style="color:#bbb6ff">Needs Work → Aurum/System:</b> Stop Tiny Seed patch-loop work as the primary recovery strategy. Build and VM-qualify the full installer; CLEAN REGROW must preserve only validated facts (${esc(preserve||'validated identity, hardware, network, recovery/LKG metadata')}), wipe only the explicitly selected Aurum installation, restore a complete Wi-Fi/graphics/recovery stack, regrow from canonical Git/LKG, and use the current fresh one-shot guarded flash/preflight contract—not the retired static PC-01 lane. Re-prove the exact target (${esc(target)}), complete full raw readback, then require physical acceptance: ${esc(acceptanceGates||blockers)}. Current controller ingress and current full-seed flash remain unverified.<br><b style="color:#f0c76a">Your Actions:</b> none from this recovery lane. Do not boot, reflash, reconnect, or authorize media from the stale Tiny Seed READY_TO_BOOT receipt or from the historical PC-01 route. Aurum/System must first produce a current full-seed build/VM result and an exact current-release one-shot preflight. A separate verified Action Ownership boundary may request the next genuine human-only step later.`;
  }else{
    const graphics=acceptance?.graphics?.required_behavior||'repair graphics boot/fallback and prove it is nonrecursive';
    const wifi=(acceptance?.wifi?.required_diff||[]).join(', ')||'Wi-Fi image/startup path';
    html=`<b style="color:#ffd0d7">Tiny Seed physical acceptance · CANDIDATE QUARANTINED</b><br><b style="color:#8ce7b2">Frontiers Advancing:</b> Exact current media integrity remains proven by the matching full raw-readback receipt (${esc(source)} · x86 ${esc(sha)}…), and post-flash physical acceptance now overrides media-only READY_TO_BOOT semantics.<br><b style="color:#bbb6ff">Needs Work → Aurum/System:</b> Physical release blockers: ${esc(blockers)}. Graphics must converge on ${esc(graphics)}. Wi-Fi repair must compare and re-prove ${esc(wifi)}. Build a new exact-release candidate, re-run virtual gates, guarded flash/readback, then require physical Wi-Fi association plus stable graphics/fallback before restoring physical readiness.<br><b style="color:#f0c76a">Your Actions:</b> none. Do not boot, reflash, reconnect, or authorize media from the stale READY_TO_BOOT state. Wait for a new exact-release physical handoff after Aurum/System clears the quarantined candidate.`;
  }
  if(box.innerHTML!==html)box.innerHTML=html;
  const owner=guide.querySelector('.recovery-owner');
  const ownerHtml=pivot?'<b>Your Actions:</b> None from Recovery Guardian. Full-seed Clean Regrow build, route repair, VM qualification, exact-device preflight, and proof are Aurum/System work; the retired static PC-01 flash lane grants no authority.':'<b>Your Actions:</b> None. The current Tiny Seed candidate is quarantined after physical acceptance failure; repair and re-proof are Aurum/System work.';
  if(owner&&owner.innerHTML!==ownerHtml)owner.innerHTML=ownerHtml;
}
async function j(u){try{const r=await fetch(`${u}?t=${Date.now()}`,{cache:'no-store'});return r.ok?await r.json():null}catch(_){return null}}
async function refresh(){[acceptance,release,flash,strategy]=await Promise.all([j(ACCEPTANCE),j(RELEASE),j(FLASH),j(STRATEGY)]);publish();patch()}
window.addEventListener('aurum-tinyseed-media-handoff-state',()=>setTimeout(patch,0));
window.addEventListener('aurum-recovery-guardian-state',()=>setTimeout(patch,0));
document.addEventListener('click',e=>{if(e.target.closest?.('#systems [data-id="recovery"]'))setTimeout(patch,60)});
new MutationObserver(()=>setTimeout(patch,0)).observe(document.body,{childList:true,subtree:true});
refresh();setInterval(refresh,REFRESH);
})();
