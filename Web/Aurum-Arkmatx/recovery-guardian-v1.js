/* AURUM_RECOVERY_GUARDIAN_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Surfaces the mandatory Aurum base-seed recovery architecture without claiming implementation proof.
 */
(()=>{
'use strict';
if(window.__aurumRecoveryGuardianV1)return;
window.__aurumRecoveryGuardianV1=true;
const DOC_URL='https://github.com/FormatX66/BoxBrain/blob/main/docs/architecture/SEED_RECOVERY_ARCHITECTURE.md';
const INVARIANT='No new state may destroy the last proven working state.';
const FLOW='proven state → snapshot → candidate → boot/test → health gate → promote → new LKG';
const FAILURE='candidate failure → freeze → capture → quarantine → component/LKG rollback → boot/test → report';
const PHASE1=['A/B seed slots','Last Known Good metadata/pointer','protected State Guardian/watchdog','pre-change snapshot hook','boot/runtime health gate','automatic rollback','mutation journal + quarantine','protected GitHub desired-state rollback trigger'];
const HUMAN_RULE='No action from you right now. Recovery is an Aurum/base-seed engineering requirement until current evidence names a specific recovery test or physical intervention.';
const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const style=document.createElement('style');
style.id='aurumRecoveryGuardianStyle';
style.textContent=`
.recovery-law{margin-top:9px;border:1px solid #4d467f;border-radius:10px;background:#171629;padding:8px 9px;color:#cbc7ff;font-size:10px;font-weight:850}.recovery-law small{display:block;margin-top:3px;color:#9099ad;font-size:9px;font-weight:650}.recovery-guide{margin-top:10px;border:1px solid #3c386a;border-radius:12px;background:#121421;padding:11px}.recovery-guide h4{margin:0 0 6px;font-size:11px;color:#cbc7ff;text-transform:uppercase;letter-spacing:.07em}.recovery-guide p,.recovery-guide li{font-size:10.5px;line-height:1.48;color:#939caf}.recovery-guide p{margin:4px 0}.recovery-guide ol,.recovery-guide ul{margin:6px 0 0;padding-left:18px}.recovery-guide a{color:#bcb7ff;font-weight:750;text-decoration:none}.recovery-guide a:hover{text-decoration:underline}.recovery-owner{margin-top:8px;padding-top:8px;border-top:1px solid #343164;color:#8f99ad;font-size:9.5px;line-height:1.42}.recovery-owner b{color:#bcb7ff}
`;
document.head.appendChild(style);
function card(){return $('#systems [data-id="recovery"]')}
function ensureCard(){
 const systems=$('#systems');if(!systems)return null;
 let c=card();
 if(!c){
  c=document.createElement('button');c.type='button';c.className='card';c.dataset.id='recovery';
  c.innerHTML='<div class="card-head"><div class="card-icon">⟲</div><span class="pill waiting">Waiting</span></div><h3>Recovery Guardian</h3><p>A/B seed, Last Known Good, protected State Guardian, snapshots, rollback and remote recovery control.</p><div class="evidence">Mandatory architecture locked · implementation/proof evidence pending</div><div class="recovery-law">Protect the last proven state.<small>Architecture is mandatory; documentation alone is not implementation proof.</small></div>';
  systems.appendChild(c);
 }
 return c;
}
function enhanceDetail(){
 const c=card();if(!c||c.getAttribute('aria-expanded')!=='true')return;
 const detail=$('#detail');if(!detail||!detail.classList.contains('show'))return;
 const title=$('#detailTitle');if(title)title.textContent='Recovery Guardian — Architecture locked';
 const text=$('#detailText');if(text)text.textContent='Mandatory base-seed survival architecture. This surface distinguishes a locked design requirement from verified implementation.';
 const host=$('.guide-wrap',detail)||detail;
 let box=$('.recovery-guide',host);if(!box){box=document.createElement('div');box.className='recovery-guide';host.appendChild(box)}
 box.innerHTML=`<h4>Core invariant</h4><p><b>${esc(INVARIANT)}</b></p><p><b>Healthy promotion:</b> ${esc(FLOW)}</p><p><b>Failure recovery:</b> ${esc(FAILURE)}</p><h4 style="margin-top:10px">Phase 1 survival layer</h4><ol>${PHASE1.map(x=>`<li>${esc(x)}</li>`).join('')}</ol><div class="recovery-owner"><b>Owner:</b> Aurum/System · ${esc(HUMAN_RULE)}</div><p style="margin-top:8px"><a href="${DOC_URL}" target="_blank" rel="noopener">Open mandatory recovery architecture ↗</a></p>`;
}
function seedGuard(){
 const seed=$('#systems [data-id="seed"]');if(!seed)return;
 let note=$('.recovery-owner',seed);if(note)return;
 note=document.createElement('div');note.className='recovery-owner';note.innerHTML='<b>Recovery invariant:</b> candidate growth must preserve a recoverable proven state; promotion waits for health evidence.';
 seed.appendChild(note);
}
function publish(){
 const state={schema:'aurum-command-center-recovery-guardian-v1',architectureLocked:true,mandatoryBaseSeed:true,phase1:PHASE1.slice(),implementationEvidence:'not-established-by-architecture-document',needsWorkOwner:'aurum-system',humanActionInference:false,docUrl:DOC_URL};
 window.__aurumRecoveryGuardianState=state;
 window.dispatchEvent(new CustomEvent('aurum-recovery-guardian-state',{detail:state}));
}
let scheduled=false;function refresh(){scheduled=false;ensureCard();seedGuard();enhanceDetail()}function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(refresh)}
document.addEventListener('click',e=>{if(e.target.closest?.('#systems [data-id="recovery"]'))setTimeout(enhanceDetail,35)});
document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.closest?.('#systems [data-id="recovery"]'))setTimeout(enhanceDetail,35)});
new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true,characterData:true});
publish();refresh();setTimeout(refresh,500);setInterval(refresh,15000);
})();
