/* AURUM_SEED_LIFECYCLE_V1_CANONICAL
 * AURUM_SEED_LIFECYCLE_V1_1_CANONICAL
 * AURUM_SEED_LIFECYCLE_V1_2_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Canonical Aurum law: Boot once. Grow continuously.
 * Git stores the genetics. Seeds carry the germ. Machines regrow the phenotype.
 */
(()=>{
'use strict';
if(window.__aurumSeedLifecycleV1)return;
window.__aurumSeedLifecycleV1=true;
const POLICY_URL='https://github.com/FormatX66/BoxBrain/blob/main/docs/architecture/RESEED_GENETICS_ARCHITECTURE.md';
const RECOVERY_URL='https://github.com/FormatX66/BoxBrain/blob/main/docs/architecture/SEED_RECOVERY_ARCHITECTURE.md';
const PLAN_URL='https://raw.githubusercontent.com/FormatX66/BoxBrain/main/Projects/Aurum/completion-plan.json';
const HANDOFF_URL='https://raw.githubusercontent.com/FormatX66/BoxBrain/main/Projects/Aurum/Release/latest-tinyseed-handoff.json';
const LAW='Boot once. Grow continuously.';
const GENETICS_LAW='Git stores the genetics. Seeds carry the germ. Machines regrow the phenotype.';
const FLOW='viable seed → protected germ → resolve trusted genetics → stage/grow candidate beside active organism → verify phenotype → promote';
const FAILURE='candidate failure → preserve active organism → record receipt → quarantine/discard candidate → retry current genetics or select a trusted historical target';
const BOOT_MEDIA='first seed · external germ for pre-germ/catastrophic recovery · deliberate trusted reseed';
const HUMAN_RULE='Normal generations never imply a reflash. A physical seed/recovery-media step is valid only when separate current evidence identifies first seeding, pre-germ recovery, or a true storage/recovery condition and names the target device.';
const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const short=s=>String(s||'unknown').slice(0,12);
let releaseSync={loaded:false,healthy:false,reason:'loading',planSource:null,planState:null,handoffSource:null,handoffState:null,handoffPhysicalBoot:null,handoffForcedRollback:null};
const style=document.createElement('style');
style.id='aurumSeedLifecycleStyle';
style.textContent=`
.seed-lifecycle-law{margin-top:9px;border:1px solid #4a4580;border-radius:10px;background:#171629;padding:8px 9px;color:#c9c5ff;font-size:10px;font-weight:850;letter-spacing:.02em}
.seed-lifecycle-law small{display:block;margin-top:3px;color:#8e96aa;font-size:9px;font-weight:650;letter-spacing:0}
.seed-lifecycle-guide{margin-top:10px;border:1px solid #3c386a;border-radius:12px;background:#121421;padding:11px}
.seed-lifecycle-guide h4{margin:0 0 6px;font-size:11px;color:#c9c5ff;text-transform:uppercase;letter-spacing:.07em}
.seed-lifecycle-guide p,.seed-lifecycle-guide li{font-size:10.5px;line-height:1.48;color:#939caf}
.seed-lifecycle-guide p{margin:4px 0}.seed-lifecycle-guide ul{margin:6px 0 0;padding-left:18px}
.seed-lifecycle-guide a{color:#bcb7ff;font-weight:750;text-decoration:none}.seed-lifecycle-guide a:hover{text-decoration:underline}
.seed-lifecycle-owner-note{margin-top:8px;padding-top:8px;border-top:1px solid #343164;color:#8f99ad;font-size:9.5px;line-height:1.42}
.seed-lifecycle-owner-note b{color:#bcb7ff}
.seed-release-sync{margin-top:10px;border:1px solid #314258;border-radius:12px;background:#101720;padding:11px}
.seed-release-sync h4{margin:0 0 7px;font-size:11px;color:#9ed0ff;text-transform:uppercase;letter-spacing:.07em}
.seed-release-sync p{margin:5px 0;font-size:10.5px;line-height:1.48;color:#939caf}.seed-release-sync b{color:#d6e8fa}.seed-release-sync .ok{color:#8ce7b2}.seed-release-sync .wait{color:#f0c76a}.seed-release-sync code{font-size:9.5px;color:#bbc8d5;overflow-wrap:anywhere}
`;
document.head.appendChild(style);
function seedCard(){
 const direct=$('#systems [data-id="seed"]');
 if(direct)return direct;
 return [...document.querySelectorAll('#systems .card,#systems .system-card')].find(c=>/^Seed (Pipeline|Lifecycle)$/i.test($('h3',c)?.textContent?.trim()||''))||null;
}
function decorateCard(){
 const card=seedCard();if(!card)return;
 card.dataset.id='seed';card.dataset.seedLifecycle='genetics-regrowth';card.dataset.releaseIdentitySync=releaseSync.healthy?'matched':(releaseSync.loaded?'needs-work':'loading');
 const title=$('h3',card);if(title)title.textContent='Seed Lifecycle';
 const desc=$('p',card);if(desc)desc.textContent='Trusted genetics + protected germ + candidate regrowth; release identity follows the authoritative Tiny Seed handoff.';
 let law=$('.seed-lifecycle-law',card);
 if(!law){law=document.createElement('div');law.className='seed-lifecycle-law';const evidence=$('.evidence',card);(evidence||card).insertAdjacentElement(evidence?'beforebegin':'beforeend',law)}
 const syncText=releaseSync.healthy?` Release spine synced: ${short(releaseSync.handoffSource)} · ${releaseSync.handoffState}.`:'';
 law.innerHTML=`${esc(LAW)}<small>${esc(GENETICS_LAW)} The active proven organism is never overwritten during candidate staging.${esc(syncText)}</small>`;
}
function releaseSyncHtml(){
 const status=!releaseSync.loaded?'<span class="wait">Loading current release truth…</span>':releaseSync.healthy?'<span class="ok">Release identity synchronized</span>':'<span class="wait">Release identity needs repair</span>';
 const identity=releaseSync.loaded?`<p><b>Authoritative handoff:</b> <code>${esc(short(releaseSync.handoffSource))}</code> · ${esc(releaseSync.handoffState||'unknown')}<br><b>Completion plan:</b> <code>${esc(short(releaseSync.planSource))}</code> · ${esc(releaseSync.planState||'unknown')}</p>`:'';
 const boundary=releaseSync.loaded?`<p><b>Physical proof boundary:</b> boot ${esc(releaseSync.handoffPhysicalBoot||'unknown')} · forced LKG rollback ${esc(releaseSync.handoffForcedRollback||'unknown')}. Release synchronization cannot turn either gate into proof.</p>`:'';
 const needs=releaseSync.loaded&&releaseSync.healthy?'Current release identity is coherent. Remaining physical gates stay separate and evidence-driven.':`Repair the completion-plan ↔ handoff projection before trusting release-summary identity (${esc(releaseSync.reason)}).`;
 return `<div class="seed-release-sync"><h4>Completion spine · release identity</h4><p>${status}</p>${identity}${boundary}<p><b>Frontiers Advancing:</b> the Tiny Seed handoff is the release authority and the completion plan now follows its immutable source/state through a fail-closed synchronizer.</p><p><b>Needs Work → Aurum/System:</b> ${needs}</p><p><b>Your Actions:</b> none from release synchronization. Physical or destructive authority is shown only by the separate current Action Ownership evidence gate.</p></div>`;
}
function enhanceGuide(){
 const card=seedCard();if(!card||card.getAttribute('aria-expanded')!=='true')return;
 const detail=$('#detail');if(!detail||!detail.classList.contains('show'))return;
 const title=$('#detailTitle');if(title&&/^Seed Pipeline\b/.test(title.textContent||''))title.textContent=(title.textContent||'').replace(/^Seed Pipeline/,'Seed Lifecycle');
 let host=$('.guide-wrap',detail)||detail;
 let box=$('.seed-lifecycle-guide',host);
 if(!box){box=document.createElement('div');box.className='seed-lifecycle-guide';detail.appendChild(box)}
 box.innerHTML=`<h4>Canonical genetics / seed lifecycle</h4><p><b>${esc(LAW)}</b> ${esc(GENETICS_LAW)}</p><p><b>Normal established-node path:</b> ${esc(FLOW)}</p><p><b>Candidate failure:</b> ${esc(FAILURE)}</p><p><b>Boot/recovery media is only for:</b> ${esc(BOOT_MEDIA)}</p><p><b>Promotion guard:</b> resolve an immutable trusted genetics commit, preserve the active organism during staging, and promote only after required health evidence.</p><p><b>Your action:</b> ${esc(HUMAN_RULE)}</p><p><a href="${POLICY_URL}" target="_blank" rel="noopener">Open genetics / reseed architecture ↗</a> · <a href="${RECOVERY_URL}" target="_blank" rel="noopener">Open recovery architecture ↗</a></p>`;
 let sync=$('.seed-release-sync',detail);if(sync)sync.remove();
 box.insertAdjacentHTML('afterend',releaseSyncHtml());
}
function enhanceSeedTrait(){
 const section=document.querySelector('[data-aurum-traits]');if(!section)return;
 const selected=[...section.querySelectorAll('.trait[aria-expanded="true"]')].find(t=>$('.trait-name',t)?.textContent?.trim()==='Seed Propagation');
 if(!selected)return;
 const detail=$('.trait-detail',section);if(!detail)return;
 let note=$('.seed-lifecycle-guide',detail);
 if(!note){note=document.createElement('div');note.className='seed-lifecycle-guide';detail.appendChild(note)}
 note.innerHTML=`<h4>Propagation rule</h4><p>${esc(FLOW)}. Established nodes regrow from trusted genetics through the protected germ; boot media is reserved for first seed or verified recovery.</p><p>${esc(HUMAN_RULE)}</p>`;
}
function rewriteHumanGate(){
 const gate=$('#humanGate');if(!gate)return;
 const replacements=[
  ['For an established Aurum node, verify the next authorized generation and propagate it through the running seed; use boot media only for first seeding or a verified recovery condition.','For an established Aurum node, resolve trusted genetics, grow a candidate beside the active organism, verify it, then promote it; use boot/recovery media only for first seeding or a verified recovery condition.'],
  ['Established nodes use running-seed propagation for normal generations; boot/flash media is limited to first seed or verified recovery.','Established nodes use protected-germ genetics regrowth for normal generations; boot/flash media is limited to first seed or verified recovery.'],
  ['Build and verify a fresh PC seed containing all seven everyday capabilities, then boot a generation that already contains them.','For an established Aurum node, regrow the next proven phenotype from trusted genetics; do not request a physical reflash without separate current recovery evidence.'],
  ['Build and verification stages should complete before a physical boot/flash is requested.','Genetics resolution, candidate growth and verification must complete before promotion; a physical boot/flash is requested only for first seed or verified recovery.']
 ];
 const walker=document.createTreeWalker(gate,NodeFilter.SHOW_TEXT);
 const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
 for(const n of nodes){let t=n.nodeValue||'';for(const [a,b] of replacements)t=t.replace(a,b);n.nodeValue=t}
 let note=$('.seed-lifecycle-owner-note',gate);
 if(!note){note=document.createElement('div');note.className='seed-lifecycle-owner-note';gate.appendChild(note)}
 note.innerHTML=`<b>Seed lifecycle guard:</b> ${esc(HUMAN_RULE)}`;
}
function statePayload(){return {schema:'aurum-command-center-seed-lifecycle-v1.2',law:'boot-once-grow-continuously',geneticsLaw:'git-stores-genetics-seeds-carry-germ',normal_generation:'genetics-regrowth',candidate_only_staging:true,active_overwrite_allowed:false,promotion_requires_health_evidence:true,boot_media_scope:['first-seed','external-germ-pre-germ-recovery','catastrophic-storage-recovery','deliberate-trusted-reseed'],human_action_requires_separate_current_evidence:true,release_identity_authority:'tinyseed-handoff',release_identity_sync_loaded:releaseSync.loaded,release_identity_in_sync:releaseSync.healthy,release_identity_sync_reason:releaseSync.reason,completion_plan_source_commit:releaseSync.planSource,completion_plan_release_state:releaseSync.planState,handoff_source_commit:releaseSync.handoffSource,handoff_release_state:releaseSync.handoffState,completion_plan_sync_grants_physical_proof:false,completion_plan_sync_grants_human_authority:false,needs_work_owner:'aurum-system',policy_url:POLICY_URL,recovery_url:RECOVERY_URL};}
function publish(){const state=statePayload();window.__aurumSeedLifecycleState=state;window.dispatchEvent(new CustomEvent('aurum-seed-lifecycle-state',{detail:state}));}
async function fetchJson(url){const r=await fetch(`${url}${url.includes('?')?'&':'?'}ts=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw new Error(`http-${r.status}`);return r.json();}
async function loadReleaseSync(){
 try{
  const [plan,handoff]=await Promise.all([fetchJson(PLAN_URL),fetchJson(HANDOFF_URL)]);
  const planSource=plan?.latest_release_source_commit||null,planState=plan?.release_state||null,handoffSource=handoff?.source_commit||null,handoffState=handoff?.state||null;
  const valid=plan?.schema==='aurum-completion-plan-v1'&&handoff?.schema==='aurum-tinyseed-handoff-v1'&&!!planSource&&!!planState&&!!handoffSource&&!!handoffState;
  const matched=valid&&planSource===handoffSource&&planState===handoffState;
  releaseSync={loaded:true,healthy:matched,reason:matched?'handoff-authoritative-plan-projection-matched':(valid?'release-identity-mismatch':'invalid-release-evidence'),planSource,planState,handoffSource,handoffState,handoffPhysicalBoot:handoff?.gates?.physical_boot||null,handoffForcedRollback:handoff?.gates?.guardian_forced_rollback||null};
 }catch(err){releaseSync={...releaseSync,loaded:true,healthy:false,reason:`evidence-unavailable:${err?.message||'fetch-error'}`};}
 publish();refresh();
}
let scheduled=false;
function refresh(){scheduled=false;decorateCard();rewriteHumanGate();enhanceGuide();enhanceSeedTrait()}
function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(refresh)}
document.addEventListener('click',e=>{if(e.target.closest?.('#systems [data-id="seed"], .trait'))setTimeout(refresh,35)});
document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.closest?.('#systems [data-id="seed"], .trait'))setTimeout(refresh,35)});
new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true,characterData:true});
publish();refresh();loadReleaseSync();setTimeout(refresh,500);setInterval(refresh,15000);setInterval(loadReleaseSync,300000);
})();
