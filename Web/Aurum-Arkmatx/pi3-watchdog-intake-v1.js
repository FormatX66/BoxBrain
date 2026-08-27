/* AURUM_PI3_WATCHDOG_INTAKE_V1_0_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Integrates inside the existing expandable Pi3 Physical Evidence card; it creates no new major dashboard box.
 * schema:'aurum-command-center-pi3-watchdog-intake-v1.0'
 * Fail-closed intake implementation is evidence only: receipt presence never implies validation, watchdog proof, mutation authority, or human action.
 */
(()=>{'use strict';
if(window.__aurumPi3WatchdogIntakeV1)return;
window.__aurumPi3WatchdogIntakeV1=true;
const SOURCE_COMMIT='9b23d84197d4659d7e2de582de86dfe5535c7c02';
const INTAKE_SOURCE=`https://raw.githubusercontent.com/FormatX66/BoxBrain/${SOURCE_COMMIT}/Projects/AdaptiveKernel/recovery/physical_watchdog_receipt.py`;
const PHYSICAL_RECEIPT='https://raw.githubusercontent.com/FormatX66/BoxBrain/main/Projects/AdaptiveDrivers/evidence/pi3-oob-watchdog-physical.json';
let probe={intakeImplementationVerified:false,physicalReceiptPresent:false,probeError:null};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function fetchText(url){const r=await fetch(url,{cache:'no-store'});if(r.status===404)return null;if(!r.ok)throw Error(`HTTP ${r.status}`);return r.text()}
async function inspect(){try{const src=await fetchText(INTAKE_SOURCE);probe.intakeImplementationVerified=!!(src&&src.includes('aurum.pi3.oob-recovery.evaluation.v1')&&src.includes('physical_proof_validated')&&src.includes('mutation_authority_granted'));const receipt=await fetchText(PHYSICAL_RECEIPT);probe.physicalReceiptPresent=receipt!==null;probe.probeError=null;}catch(e){probe.probeError=e?.message||'probe failed';}apply()}
function patchDetail(detail,base){if(!detail)return;const watchdogProven=base?.outOfBandWatchdogProven===true;const implementation=probe.intakeImplementationVerified?'implemented + exact-source verified':'verification unavailable';const receipt=probe.physicalReceiptPresent?'receipt present; canonical validator/preflight must still validate it':'physical receipt not present';
let html=detail.innerHTML;
if(!detail.querySelector('[data-pi3-watchdog-intake-row]')){
  const old='<b>Out-of-band watchdog</b><span>not proven — broader binding/kernel authority held</span>';
  const status=watchdogProven?'proven by the base Pi3 evidence layer':`${implementation} · ${receipt} · broader binding/kernel authority held`;
  if(html.includes(old))html=html.replace(old,`<b data-pi3-watchdog-intake-row>Out-of-band watchdog</b><span>${esc(status)}</span>`);
}
if(!detail.querySelector('[data-pi3-watchdog-intake-frontier]')){
  const frontier=`<span data-pi3-watchdog-intake-frontier> Fail-closed physical-watchdog receipt intake is implemented at BoxBrain ${SOURCE_COMMIT.slice(0,8)} and accepts no inferred proof: a missing receipt is a normal hold, malformed evidence is refused, and even a validated recovery receipt can only clear the watchdog prerequisite.</span>`;
  html=html.replace('<b>Frontiers Advancing:</b>',`<b>Frontiers Advancing:</b>${frontier}`);
}
if(!detail.querySelector('[data-pi3-watchdog-intake-needs]')){
  const needs=`<span data-pi3-watchdog-intake-needs> Complete the real external recovery cycle: exact Pi3 and LKG identity, distinct independent controller / observer / actuator / verifier identities, target-kernel-independent observation and actuation, automatic failure and recovery evidence with content hashes, and exact post-recovery health. Persist that receipt through the canonical intake; after validation, fresh explicit kernel-mutation authority remains a separate gate.</span>`;
  html=html.replace('<b>Needs Work → Aurum/System:</b>',`<b>Needs Work → Aurum/System:</b>${needs}`);
}
detail.innerHTML=html;
}
function apply(){const card=document.querySelector('[data-id="pi3-physical-evidence"]');const detail=card?.querySelector('.p3-detail');const base=window.__aurumPi3PhysicalEvidenceState||null;patchDetail(detail,base);window.__aurumPi3WatchdogIntakeState={schema:'aurum-command-center-pi3-watchdog-intake-v1.0',componentRevision:'1.0',canonicalOwner:'FormatX66/ClusterSites',integratesInto:'pi3-physical-evidence',sourceCommit:SOURCE_COMMIT,intakeImplementationVerified:probe.intakeImplementationVerified,physicalReceiptPresent:probe.physicalReceiptPresent,physicalReceiptValidated:false,watchdogProven:base?.outOfBandWatchdogProven===true,physicalProofInferred:false,mutationAuthorityGranted:false,promotionAuthorityGranted:false,writeAuthority:false,needsWorkOwner:'aurum-system',humanActionInference:false,probeError:probe.probeError};window.dispatchEvent(new CustomEvent('aurum-pi3-watchdog-intake-state',{detail:window.__aurumPi3WatchdogIntakeState}));}
window.addEventListener('aurum-pi3-physical-evidence-state',()=>{apply();inspect()});
function boot(){if(!document.querySelector('[data-id="pi3-physical-evidence"]'))return setTimeout(boot,250);apply();inspect();setInterval(inspect,120000)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
