/* Aurum dashboard expandable guidance layer.
 * Canonical website component: FormatX66/ClusterSites.
 * Adds actionable details without storing credentials or mutating project state.
 */
(() => {
  'use strict';
  if (window.__aurumGuidanceLoaded) return;
  window.__aurumGuidanceLoaded = true;

  const REPO = 'FormatX66/BoxBrain';
  const API = `https://api.github.com/repos/${REPO}`;
  const $ = (s, root = document) => root.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let circle = {state:'unknown', statuses:[], updated:0};

  const style = document.createElement('style');
  style.textContent = `
    .card .expand-hint{margin-top:9px;font-size:10px;color:#9aabc0;font-weight:700}
    .card[aria-expanded="true"]{border-color:#806a37;background:#131a22}
    .guide-wrap{margin-top:14px;padding-top:13px;border-top:1px solid #263548}
    .guide-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}
    .guide-box{border:1px solid #263548;background:#0b1118;border-radius:12px;padding:11px;min-width:0}
    .guide-box h4{margin:0 0 5px;font-size:11px;color:#d9e2ec;text-transform:uppercase;letter-spacing:.07em}
    .guide-box p,.guide-box li{font-size:11px;line-height:1.48;color:#91a5b9}
    .guide-box p{margin:0}.guide-box ol,.guide-box ul{margin:6px 0 0;padding-left:18px}
    .guide-action{margin-top:10px;border-left:3px solid #62d990;background:#0e1b15;border-radius:5px 12px 12px 5px;padding:11px 12px}
    .guide-action.attention{border-left-color:#f0c76a;background:#1b170d}
    .guide-action.error{border-left-color:#ff8a8a;background:#201012}
    .guide-action b{display:block;font-size:12px;margin-bottom:4px}.guide-action span{font-size:11px;line-height:1.48;color:#a5b4c3}
    .guide-links{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.guide-link{display:inline-flex;align-items:center;min-height:38px;padding:7px 10px;border:1px solid #35465d;border-radius:9px;color:#dce7f2;text-decoration:none;font-size:11px;font-weight:750;background:#151f2a}
    .circle-mini{margin-top:8px;padding-top:8px;border-top:1px solid #233043;font-size:10px;color:#8ea2b7}
    .trait{cursor:pointer}.trait:focus-visible{outline:3px solid #e0bd62aa;outline-offset:2px}.trait .trait-expand{margin-top:9px;font-size:9.5px;color:#93a8bc;font-weight:700}
    .trait-detail{margin-top:12px;border:1px solid #3a4b61;border-radius:14px;background:#0c1219;padding:14px}.trait-detail h3{margin:0 0 6px;font-size:15px}.trait-detail p{font-size:11px;line-height:1.48;color:#9fb0c2;margin:0}.trait-detail .guide-action{margin-top:11px}
    @media(max-width:680px){.guide-grid{grid-template-columns:1fr}}
  `;
  document.head.appendChild(style);

  const SYSTEM_GUIDE = {
    hopper:{what:'Hopper is the physical PC proof lane: boot, seed, GUI, input and real-machine validation.',normal:'A verified flash/boot or an active Hopper workflow means the machine lane is progressing.',action:(status)=> status==='Attention'||status==='Waiting' ? {kind:'attention',title:'Check Hopper only if the evidence names a physical gate.',text:'Keep Hopper powered and connected. Do not reflash or reboot just because the card is yellow/red; follow the evidence text first.'}:{kind:'ok',title:'No action from you.',text:'Hopper has usable evidence or an active lane.'}},
    local:{what:'The local build lane repairs and validates work without depending entirely on hosted CI.',normal:'This is mostly code-side automation and should not require physical intervention.',action:()=>({kind:'ok',title:'No action from you.',text:'Local-lane failures should be diagnosed and repaired by the build system before escalating to you.'})},
    pi4:{what:'BBPI4 is the physical edge/seed node used for enrollment, route, heartbeat and recovery evidence.',normal:'Fresh heartbeat/route evidence means the Pi can participate without a human gate.',action:(status)=> status==='Attention'||status==='Waiting' ? {kind:'attention',title:'Physical check may be needed.',text:'If the Pi4 is not already available: power it on and keep its USB-C link to the main computer connected. If it is already powered and connected, no further action is needed unless a later card names a specific port, cable or boot step.'}:{kind:'ok',title:'No action from you.',text:'The Pi lane has fresh enough evidence to continue.'}},
    ci:{what:'GitHub Actions and the Aurum controller coordinate hosted validation, failsafes, event bridges and build progression.',normal:'A failed hosted job is not automatically a human task; most are code/configuration work.',action:()=>({kind:'ok',title:'No physical action from you.',text:'Use the evidence and CircleCI section below to separate build-system work from true permission/setup gates.'})},
    seed:{what:'The seed pipeline turns verified build output into images/flashable seeds and records proof.',normal:'Build and verification stages should complete before a physical boot/flash is requested.',action:(status)=> status==='Attention' ? {kind:'attention',title:'Only act if the evidence explicitly asks for a target device.',text:'Do not flash a drive just because this card is red. A physical step should name the target device and exact operation.'}:{kind:'ok',title:'No action from you right now.',text:'Seed work can continue in build/verification lanes.'}},
    gui:{what:'The Hopper GUI lane covers loading, desktop behavior, mouse/trackpad and the human-facing projection.',normal:'Code can build automatically; subjective interaction checks happen on Hopper when a test is ready.',action:(status)=> status==='Attention' ? {kind:'attention',title:'A Hopper interaction check may be requested.',text:'When the evidence names a GUI test, use Hopper normally and report only the observed behavior. Otherwise no action is required.'}:{kind:'ok',title:'No action from you.',text:'GUI work is building or awaiting a defined test gate.'}},
    kernel:{what:'The adaptive-kernel lane explores machine-specific specialization independently from StateWeave.',normal:'Experiment status is expected and is not a failure.',action:()=>({kind:'ok',title:'No action from you yet.',text:'Hardware testing should only be requested after a runnable kernel artifact exists.'})},
    weave:{what:'StateWeave explores machine-native state/execution, plus a separate combined StateWeave + adaptive-kernel experiment.',normal:'Experiment status is expected while evidence is being built.',action:()=>({kind:'ok',title:'No action from you yet.',text:'This is an engineering/research lane until a concrete runtime test is ready.'})}
  };

  const TRAIT_ACTIONS = {
    'Continuous Self-Building':'No action from you. The next missing gate should be produced by build/controller evidence.',
    'Seed Propagation':'No action until a specific seed is marked ready for a named physical target.',
    'Adaptive Kernel':'No action until a runnable test artifact is ready; then the dashboard should name the test target and boot method.',
    'StateWeave':'No action until a runtime/verification experiment is ready.',
    'Hardware Learning':'Keep participating hardware available when a physical verification card explicitly requests it.',
    'Driver Synthesis':'No action until a generated/adapted driver reaches a named hardware test.',
    'Resilient Connectivity':'If a physical route test is requested, keep the relevant node powered and its existing wired/USB link connected.',
    'Adaptive GUI':'Use Hopper for an interaction check only when the card explicitly says a GUI test is ready.',
    'Continuous Identity':'No action until an explicit identity/behavior test is ready.'
  };

  function circleLabel(){return circle.state==='success'?'Verified':circle.state==='running'?'Running':circle.state==='failed'?'Attention':'Waiting'}
  function circleEvidence(){
    if(!circle.statuses.length) return 'No CircleCI commit status is visible yet.';
    return circle.statuses.map(s=>`${String(s.context||'').replace(/^ci\/circleci:\s*/,'')}: ${s.state}`).join(' · ');
  }

  async function refreshCircle(){
    try{
      const r=await fetch(`${API}/commits/main/status`,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}});
      if(!r.ok) throw new Error(String(r.status));
      const data=await r.json();
      const statuses=(data.statuses||[]).filter(s=>/circleci/i.test(`${s.context||''} ${s.description||''} ${s.target_url||''}`));
      let st='unknown';
      if(statuses.some(s=>['failure','error'].includes(s.state))) st='failed';
      else if(statuses.some(s=>s.state==='pending')) st='running';
      else if(statuses.length && statuses.every(s=>s.state==='success')) st='success';
      circle={state:st,statuses,updated:Date.now()};
    }catch(_){ circle={state:'unknown',statuses:[],updated:Date.now()}; }
    ensureCircleCard();
  }

  function ensureCircleCard(){
    const box=$('#systems'); if(!box) return;
    let card=$('[data-circleci-card]',box);
    if(!card){
      card=document.createElement('button');
      card.type='button'; card.className='card'; card.dataset.circleciCard='true'; card.dataset.id='circleci';
      box.appendChild(card);
    }
    const stateClass=circle.state==='success'?'success':circle.state==='running'?'running':circle.state==='failed'?'failed':'waiting';
    card.innerHTML=`<div class="card-head"><div class="card-icon">◌</div><span class="pill ${stateClass}">${circleLabel()}</span></div><h3>CircleCI</h3><p>Independent external CI lane for repository integrity, Codelation and backend tests.</p><div class="evidence">${esc(circleEvidence())}</div><div class="expand-hint">Tap for status and directions →</div>`;
    const tracked=$('#mTracked'); if(tracked) tracked.textContent='9';
  }

  function enhanceHints(){
    document.querySelectorAll('#systems .card:not([data-circleci-card])').forEach(card=>{
      if(!$('.expand-hint',card)){
        const hint=document.createElement('div'); hint.className='expand-hint'; hint.textContent='Tap for details and directions →'; card.appendChild(hint);
      }
    });
  }

  function systemAction(id,status){
    if(id==='circleci'){
      if(circle.state==='running') return {kind:'ok',title:'No action — CircleCI is running.',text:'The BoxBrain CircleCI jobs are executing automatically.'};
      if(circle.state==='success') return {kind:'ok',title:'No action — CircleCI is healthy.',text:'The current CircleCI statuses are successful.'};
      if(circle.state==='failed') return {kind:'error',title:'CircleCI has a failed job.',text:'Open the failed job below. If it is a test/config failure, it is build-system work. Only take account action if CircleCI explicitly asks you to reauthorize or restore permissions.'};
      return {kind:'attention',title:'CircleCI project setup may be the remaining gate.',text:'If no CircleCI status appears after the config is on main: open CircleCI → Projects → BoxBrain → Set Up Project / Follow Project → choose the existing .circleci/config.yml. GitHub OAuth and the repository SSH key are already connected.'};
    }
    const g=SYSTEM_GUIDE[id]; return g ? g.action(status) : {kind:'ok',title:'No confirmed human action.',text:'Use the evidence shown on the card before doing physical work.'};
  }

  function showSystemGuide(card){
    const id=card.dataset.id||'';
    const title=$('h3',card)?.textContent||'System';
    const status=$('.pill',card)?.textContent||'Unknown';
    const evidence=$('.evidence',card)?.textContent||'No current evidence.';
    const g= id==='circleci' ? {what:'CircleCI is the independent external CI lane for Linux-safe BoxBrain validation.',normal:'It should run automatically from .circleci/config.yml and post commit statuses back to GitHub.'} : SYSTEM_GUIDE[id];
    const action=systemAction(id,status);
    const detail=$('#detail'); if(!detail) return;
    const dt=$('#detailTitle'); const dp=$('#detailText');
    if(dt) dt.textContent=`${title} — ${status}`;
    if(dp) dp.textContent=g?.what||'Current Aurum workstream.';
    let guide=$('.guide-wrap',detail);
    if(!guide){ guide=document.createElement('div'); guide.className='guide-wrap'; detail.appendChild(guide); }
    const circleLinks=(id==='circleci'||id==='ci') ? circle.statuses.filter(s=>s.target_url).map(s=>`<a class="guide-link" href="${esc(s.target_url)}" target="_blank" rel="noopener">${esc(String(s.context||'CircleCI').replace(/^ci\/circleci:\s*/,''))} ↗</a>`).join('') : '';
    guide.innerHTML=`
      <div class="guide-grid">
        <div class="guide-box"><h4>Current evidence</h4><p>${esc(evidence)}</p></div>
        <div class="guide-box"><h4>What normal looks like</h4><p>${esc(g?.normal||'Fresh evidence supports continued progress without an invented human gate.')}</p></div>
      </div>
      ${(id==='ci')?`<div class="guide-box" style="margin-top:10px"><h4>CircleCI sub-lane</h4><p>${esc(circleEvidence())}</p></div>`:''}
      <div class="guide-action ${action.kind==='attention'?'attention':action.kind==='error'?'error':''}"><b>${esc(action.title)}</b><span>${esc(action.text)}</span></div>
      <div class="guide-links"><a class="guide-link" href="https://github.com/${REPO}/actions" target="_blank" rel="noopener">GitHub Actions ↗</a>${circleLinks}</div>`;
    detail.classList.add('show');
    document.querySelectorAll('#systems .card').forEach(c=>c.setAttribute('aria-expanded',String(c===card)));
  }

  function traitDetail(card){
    const section=card.closest('[data-aurum-traits]'); if(!section) return;
    let detail=$('.trait-detail',section);
    if(!detail){ detail=document.createElement('div'); detail.className='trait-detail'; $('.trait-panel',section)?.insertAdjacentElement('afterend',detail); }
    const name=$('.trait-name',card)?.textContent||'Trait';
    const pct=$('.trait-pct',card)?.textContent||'0%';
    const marks=[...card.querySelectorAll('.trait-mark')];
    const completed=marks.filter(m=>m.classList.contains('on')).map(m=>m.textContent.trim());
    const next=marks.find(m=>!m.classList.contains('on'))?.textContent.trim()||'All four gates complete';
    const action=TRAIT_ACTIONS[name]||'No action unless the dashboard identifies a concrete human-only test gate.';
    detail.innerHTML=`<h3>${esc(name)} — ${esc(pct)}</h3><p><b>Completed gates:</b> ${esc(completed.join(' → ')||'None')}<br><b>Next evidence gate:</b> ${esc(next)}</p><div class="guide-action"><b>Do you need to do anything?</b><span>${esc(action)}</span></div>`;
    [...section.querySelectorAll('.trait')].forEach(t=>t.setAttribute('aria-expanded',String(t===card)));
    detail.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
  }

  document.addEventListener('click',e=>{
    const card=e.target.closest('#systems .card');
    if(card) setTimeout(()=>showSystemGuide(card),0);
    const trait=e.target.closest('.trait');
    if(trait) traitDetail(trait);
  });
  document.addEventListener('keydown',e=>{
    const trait=e.target.closest?.('.trait');
    if(trait && (e.key==='Enter'||e.key===' ')){e.preventDefault();traitDetail(trait)}
  });

  const sys=$('#systems');
  if(sys){ new MutationObserver(()=>{enhanceHints();ensureCircleCard()}).observe(sys,{childList:true,subtree:false}); }
  new MutationObserver(()=>{
    document.querySelectorAll('.trait').forEach(t=>{
      if(!t.hasAttribute('tabindex')){t.tabIndex=0;t.setAttribute('role','button');t.setAttribute('aria-expanded','false');const h=document.createElement('div');h.className='trait-expand';h.textContent='Tap for milestone details and directions →';t.appendChild(h)}
    });
  }).observe(document.body,{childList:true,subtree:true});

  enhanceHints();
  refreshCircle();
  setInterval(refreshCircle,60000);
  $('#refresh')?.addEventListener('click',()=>setTimeout(refreshCircle,500));
})();
