/* AURUM_SEED_LIFECYCLE_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Canonical Aurum law: Boot once. Grow continuously.
 * Established nodes grow through the running seed; boot media is first-seed/recovery infrastructure only.
 */
(()=>{
'use strict';
if(window.__aurumSeedLifecycleV1)return;
window.__aurumSeedLifecycleV1=true;
const POLICY_URL='https://github.com/FormatX66/BoxBrain/blob/aurum/trunk-v0.01/Projects/AurumPC/SEED_LIFECYCLE.md';
const FLOW='current seed → discover → pull → verify → stage → apply → prove → become next seed';
const BOOT_MEDIA='first seed · catastrophic storage recovery · deliberate operator re-seeding';
const HUMAN_RULE='Normal generations never imply a reflash. A physical seed/reflash step is valid only when separate current evidence identifies first seeding or a true recovery condition and names the target device.';
const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
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
`;
document.head.appendChild(style);
function seedCard(){
 const direct=$('#systems [data-id="seed"]');
 if(direct)return direct;
 return [...document.querySelectorAll('#systems .card,#systems .system-card')].find(c=>/^Seed (Pipeline|Lifecycle)$/i.test($('h3',c)?.textContent?.trim()||''))||null;
}
function decorateCard(){
 const card=seedCard();if(!card)return;
 card.dataset.id='seed';card.dataset.seedLifecycle='running-seed';
 const title=$('h3',card);if(title)title.textContent='Seed Lifecycle';
 const desc=$('p',card);if(desc)desc.textContent='Bootstrap/recovery media plus continuous running-seed generation growth.';
 let law=$('.seed-lifecycle-law',card);
 if(!law){law=document.createElement('div');law.className='seed-lifecycle-law';const evidence=$('.evidence',card);(evidence||card).insertAdjacentElement(evidence?'beforebegin':'beforeend',law)}
 law.innerHTML='Boot once. Grow continuously.<small>Established nodes do not rebuild or reflash boot media for normal generations.</small>';
}
function enhanceGuide(){
 const card=seedCard();if(!card||card.getAttribute('aria-expanded')!=='true')return;
 const detail=$('#detail');if(!detail||!detail.classList.contains('show'))return;
 const title=$('#detailTitle');if(title&&/^Seed Pipeline\b/.test(title.textContent||''))title.textContent=(title.textContent||'').replace(/^Seed Pipeline/,'Seed Lifecycle');
 let host=$('.guide-wrap',detail)||detail;
 let box=$('.seed-lifecycle-guide',host);
 if(!box){box=document.createElement('div');box.className='seed-lifecycle-guide';host.appendChild(box)}
 box.innerHTML=`<h4>Canonical seed lifecycle</h4><p><b>Normal established-node path:</b> ${esc(FLOW)}</p><p><b>Boot media is only for:</b> ${esc(BOOT_MEDIA)}</p><p><b>Your action:</b> ${esc(HUMAN_RULE)}</p><p><a href="${POLICY_URL}" target="_blank" rel="noopener">Open canonical seed lifecycle ↗</a></p>`;
}
function enhanceSeedTrait(){
 const section=document.querySelector('[data-aurum-traits]');if(!section)return;
 const selected=[...section.querySelectorAll('.trait[aria-expanded="true"]')].find(t=>$('.trait-name',t)?.textContent?.trim()==='Seed Propagation');
 if(!selected)return;
 const detail=$('.trait-detail',section);if(!detail)return;
 let note=$('.seed-lifecycle-guide',detail);
 if(!note){note=document.createElement('div');note.className='seed-lifecycle-guide';detail.appendChild(note)}
 note.innerHTML=`<h4>Propagation rule</h4><p>${esc(FLOW)}. Established nodes grow from the running seed; boot media is reserved for first seed or verified recovery.</p><p>${esc(HUMAN_RULE)}</p>`;
}
function rewriteHumanGate(){
 const gate=$('#humanGate');if(!gate)return;
 const replacements=[
  ['Build and verify a fresh PC seed containing all seven everyday capabilities, then boot a generation that already contains them.','For an established Aurum node, verify the next authorized generation and propagate it through the running seed; use boot media only for first seeding or a verified recovery condition.'],
  ['Build and verification stages should complete before a physical boot/flash is requested.','Established nodes use running-seed propagation for normal generations; boot/flash media is limited to first seed or verified recovery.']
 ];
 const walker=document.createTreeWalker(gate,NodeFilter.SHOW_TEXT);
 const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
 for(const n of nodes){let t=n.nodeValue||'';for(const [a,b] of replacements)t=t.replace(a,b);n.nodeValue=t}
 let note=$('.seed-lifecycle-owner-note',gate);
 if(!note){note=document.createElement('div');note.className='seed-lifecycle-owner-note';gate.appendChild(note)}
 note.innerHTML=`<b>Seed lifecycle guard:</b> ${esc(HUMAN_RULE)}`;
}
function publish(){
 const state={schema:'aurum-command-center-seed-lifecycle-v1',law:'boot-once-grow-continuously',normal_generation:'running-seed-propagation',boot_media_scope:['first-seed','catastrophic-storage-recovery','deliberate-reseed'],human_action_requires_separate_current_evidence:true,policy_url:POLICY_URL};
 window.__aurumSeedLifecycleState=state;
 window.dispatchEvent(new CustomEvent('aurum-seed-lifecycle-state',{detail:state}));
}
let scheduled=false;
function refresh(){scheduled=false;decorateCard();rewriteHumanGate();enhanceGuide();enhanceSeedTrait()}
function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(refresh)}
document.addEventListener('click',e=>{if(e.target.closest?.('#systems [data-id="seed"], .trait'))setTimeout(refresh,35)});
document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.closest?.('#systems [data-id="seed"], .trait'))setTimeout(refresh,35)});
new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true,characterData:true});
publish();refresh();setTimeout(refresh,500);setInterval(refresh,15000);
})();