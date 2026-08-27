/* AURUM_FARMER_PRIVATE_ACTIONS_BOUNDARY_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Adds a freshness-gated, evidence-backed private GitHub Actions account boundary
 * to the existing expandable Autonomy Controller. It never guesses the exact
 * billing/quota cause and never grants execution, mutation, or destructive authority.
 */
(()=>{
'use strict';
if(window.__aurumFarmerPrivateActionsBoundaryV1)return;
window.__aurumFarmerPrivateActionsBoundaryV1=true;
const URL='https://raw.githubusercontent.com/FormatX66/BoxBrain/main/Projects/AurumBridge/results/private-actions-account-boundary-latest.json';
const REFRESH=5*60*1000;
let state=null;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[c]));
function ageMs(){const t=Date.parse(state?.observed_at_utc||'');return Number.isFinite(t)?Date.now()-t:Infinity}
function active(){const max=Math.max(0,Number(state?.fresh_for_seconds||0))*1000;return Boolean(state?.schema==='aurum-private-actions-account-boundary-v1'&&state?.state==='HUMAN_ACCOUNT_CHECK_REQUIRED'&&state?.human_action_required===true&&max>0&&ageMs()>=-5*60*1000&&ageMs()<=max)}
function publish(){window.__aurumFarmerPrivateActionsBoundaryState={schema:'aurum-command-center-farmer-private-actions-boundary-v1.0',active:active(),observedAt:state?.observed_at_utc||null,exactRootCauseProven:state?.root_cause_exactly_proven===true,humanActionRequired:active(),humanAction:active()?state?.human_action:null,grantsExecutionAuthority:false,grantsDestructiveAuthority:false,grantsLkgMutation:false};window.dispatchEvent(new CustomEvent('aurum-farmer-private-actions-boundary-state',{detail:window.__aurumFarmerPrivateActionsBoundaryState}))}
function patch(){
  if(!active())return;
  const card=document.querySelector('#systems [data-id="autonomy-controller"]');if(!card)return;
  const pill=card.querySelector('.pill');if(pill){if(pill.className!=='pill failed')pill.className='pill failed';if(pill.textContent!=='Human Boundary')pill.textContent='Human Boundary'}
  const ev=card.querySelector('.evidence'),evText='Farmer runtime proof remains valid, but private GitHub-hosted Actions are failing before runner/step allocation; account-level Actions availability requires an operator check.';if(ev&&ev.textContent!==evText)ev.textContent=evText;
  if(card.getAttribute('aria-expanded')!=='true')return;
  const detail=card.querySelector('.ac-detail');if(!detail)return;
  let box=detail.querySelector('.private-actions-boundary-proof');if(!box){box=document.createElement('div');box.className='private-actions-boundary-proof';detail.prepend(box)}
  box.style.cssText='margin:0 0 10px;padding:9px 10px;border:1px solid #66552b;border-radius:10px;background:#191712;color:#aca99d;font-size:10.5px;line-height:1.5';
  const exact=state?.root_cause_exactly_proven===true?'exact root cause proven':'exact root cause not exposed; account-level private Actions allocation/usage/billing is the strongest current explanation';
  const html=`<b style="color:#f0c76a">Private GitHub Actions account boundary</b><br><b style="color:#8ce7b2">Frontiers Advancing:</b> Public BoxBrain and wetbeard-site GitHub-hosted execution remains available, so safe public work can continue without weakening LKG or safety gates.<br><b style="color:#bbb6ff">Needs Work → Aurum/System:</b> Chat-to-Git-Pipeline and ClusterSites private jobs are failing before any runner or workflow step executes. ${esc(exact)}. Do not burn retries until the account boundary is cleared; after it is cleared, run one correlated Farmer recovery probe and require a real runner assignment plus workflow steps.<br><b style="color:#f0c76a">Your Actions:</b> ${esc(state?.human_action||'Open GitHub account billing/settings and inspect private Actions usage/budget status.')}<br><b style="color:#929db0">Authority:</b> This account check grants no execution, destructive, mutation, promotion, or LKG authority.`;
  if(box.innerHTML!==html)box.innerHTML=html;
}
async function refresh(){try{const r=await fetch(`${URL}?t=${Date.now()}`,{cache:'no-store'});state=r.ok?await r.json():null}catch(_){state=null}publish();patch()}
window.addEventListener('aurum-workflow-failsafe-state',()=>setTimeout(patch,0));
document.addEventListener('click',e=>{if(e.target.closest?.('#systems [data-id="autonomy-controller"]'))setTimeout(patch,60)});
new MutationObserver(()=>setTimeout(patch,0)).observe(document.body,{childList:true,subtree:true});
refresh();setInterval(refresh,REFRESH);
})();
