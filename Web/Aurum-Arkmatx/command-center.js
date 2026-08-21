/* Aurum Command Center shell.
 * Makes the live dashboard a cohesive operator surface with expandable summary,
 * system, trait, activity, queue, node, and human-action views.
 */
(() => {
  'use strict';
  if (window.__aurumCommandCenter) return;
  window.__aurumCommandCenter = true;

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const physicalForkIds = new Set(['hopper','pi4']);
  const semanticAdvance = new Set(['Verified','Running','Experiment']);

  const style = document.createElement('style');
  style.textContent = `
    :root{--aurum:#6c63ff;--aurum2:#9d96ff;--aurumGlow:#6c63ff44;--bg:#0c0f16!important;--panel:#151821!important;--panel2:#10131b!important;--border:#2a2f3d!important;--gold:#6c63ff!important;--green:#65d59a!important;--blue:#8ea8ff!important;--amber:#efbd63!important;--purple:#a59eff!important}
    body{background:radial-gradient(circle at 18% -5%,#312d7438 0,transparent 34%),radial-gradient(circle at 92% 12%,#171a4430 0,transparent 30%),#0c0f16!important}
    .wrap{width:min(1240px,95vw)!important}
    .brand{align-items:center!important}.brand h1{letter-spacing:-.04em!important}.brand small{color:#9299aa!important}
    .orb{width:52px!important;height:52px!important;border-radius:16px!important;background:linear-gradient(145deg,#7770ff,#4d45cf)!important;box-shadow:0 0 0 1px #a9a4ff44,0 10px 32px #6c63ff38!important;display:grid!important;place-items:center!important;position:relative!important;overflow:hidden!important}
    .orb::before{content:'A';font:900 29px/1 Inter,system-ui,sans-serif;color:white;letter-spacing:-.08em;transform:translateX(-1px)}
    .orb::after{content:'';position:absolute;inset:7px;border:1px solid #ffffff2c;border-radius:11px;transform:rotate(45deg) scale(.72)}
    .livebox,.metric,.card,.panel,.trait-panel,.trait{background:linear-gradient(180deg,#171a24e8,#12151ee8)!important;border-color:#2c3140!important;box-shadow:inset 0 1px 0 #ffffff08}
    .metric{cursor:pointer;position:relative;transition:border-color .16s ease,background .16s ease,transform .16s ease}.metric::after{content:'›';position:absolute;right:12px;top:10px;color:#777f94;font-size:18px}.metric:hover,.metric:focus-visible,.card:hover,.panel.cc-clickable:hover,.trait:hover{border-color:#6c63ff88!important}.metric[aria-expanded='true'],.panel.cc-expanded{border-color:#6c63ff!important;background:#181b29!important;box-shadow:0 0 0 1px #6c63ff2c,inset 0 1px 0 #ffffff0c}
    .metric strong{color:#f1f0ff}.metric span{padding-right:14px;display:block}.metric.cc-action strong{color:#efbd63}
    .pill.running{background:#25235a!important;color:#bcb7ff!important}.pill.experiment{background:#29234a!important;color:#bfb8ff!important}.pill.success{background:#173428!important}.pill.failed{background:#421f29!important}.pill.waiting{background:#3a2e16!important}
    .btn.primary{background:#6c63ff!important;color:white!important}.btn{border-color:#363c4c!important;background:#171b25!important}.btn:hover{border-color:#6c63ff88!important}
    .cc-drawer{display:none;margin:12px 0 18px;border:1px solid #343b4c;border-radius:18px;background:linear-gradient(180deg,#161a25,#10131b);padding:16px;box-shadow:0 18px 50px #00000028}.cc-drawer.show{display:block}.cc-drawer-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.cc-drawer h2{font-size:18px;margin:0}.cc-drawer p{font-size:11px;color:#929bad;line-height:1.5;margin:4px 0 0}.cc-close{width:42px;height:42px;border:1px solid #363c4c;background:#181c27;color:#eef0ff;border-radius:11px;cursor:pointer}.cc-list{display:grid;gap:8px;margin-top:14px}.cc-row{display:grid;grid-template-columns:minmax(145px,.7fr) 96px minmax(0,1.5fr);gap:10px;align-items:start;border:1px solid #282e3c;border-radius:12px;background:#10141c;padding:11px}.cc-row b{font-size:12px}.cc-row span,.cc-row p{font-size:10.5px;color:#8f9bad;line-height:1.45;margin:0}.cc-owner{font-size:9px!important;text-transform:uppercase;letter-spacing:.08em;font-weight:850;border-radius:999px;padding:5px 7px;text-align:center;color:#aeb6c8!important;background:#222735}.cc-owner.you{background:#3b3017;color:#f0c76a!important}.cc-owner.system{background:#20244b;color:#b8b3ff!important}.cc-owner.none{background:#173428;color:#8ce7b2!important}.cc-empty{margin-top:12px;padding:13px;border:1px dashed #343b4c;border-radius:12px;color:#8f9bad;font-size:11px}
    .panel.cc-clickable{cursor:pointer;transition:border-color .16s ease,background .16s ease}.panel.cc-clickable::after{content:'Tap to expand';display:block;margin-top:10px;font-size:9px;color:#737e92;font-weight:750}.panel.cc-expanded{grid-column:1/-1}.panel.cc-expanded::after{content:'Expanded'}
    .progress-state{margin-top:7px;font-size:10px;font-weight:750}.progress-state.advance{color:#8ce7b2}.progress-state.fork{color:#efbd63}.progress-state.stall{color:#ff9da6}.progress-state.unknown{color:#8f9bad}
    .cc-commandline{margin:0 0 16px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center;border:1px solid #303647;border-radius:14px;background:#10131bd9;padding:10px 12px}.cc-commandline b{font-size:11px;color:#c9c6ff}.cc-commandline span{font-size:10px;color:#858fa2}.cc-badge{padding:6px 9px;border-radius:999px;background:#242150;color:#bcb7ff;font-size:9px!important;font-weight:850;letter-spacing:.06em;text-transform:uppercase}
    @media(max-width:920px){.summary{grid-template-columns:repeat(3,minmax(0,1fr))!important}.cc-row{grid-template-columns:minmax(120px,.8fr) 90px minmax(0,1.2fr)}}
    @media(max-width:680px){.summary{grid-template-columns:repeat(2,minmax(0,1fr))!important}.cc-row{grid-template-columns:1fr}.cc-owner{width:max-content}.cc-commandline{grid-template-columns:1fr}.orb{width:46px!important;height:46px!important}.orb::before{font-size:25px}}
    @media(prefers-reduced-motion:reduce){.metric,.panel.cc-clickable{transition:none}}
  `;
  document.head.appendChild(style);
  const theme = document.querySelector('meta[name="theme-color"]'); if(theme) theme.content='#0c0f16';

  const brandSmall = $('.brand small'); if(brandSmall) brandSmall.textContent='Aurum • live machine command center';
  const eyebrow = $('.brand .eyebrow'); if(eyebrow) eyebrow.textContent='AURUM';
  const orb = $('.orb'); if(orb){orb.setAttribute('aria-label','Aurum');orb.removeAttribute('aria-hidden')}

  const actions = $('.actions');
  if(actions && !$('.cc-commandline')){
    const line=document.createElement('div'); line.className='cc-commandline';
    line.innerHTML='<div><b>Command state</b><br><span>Independent frontiers continue unless a real dependency or human-only gate stops that frontier.</span></div><span class="cc-badge">state-first</span>';
    actions.insertAdjacentElement('afterend',line);
  }

  const summary = $('.summary');
  let humanMetric = $('#mHuman')?.closest('.metric');
  if(summary && !humanMetric){
    humanMetric=document.createElement('div');humanMetric.className='metric cc-action';humanMetric.tabIndex=0;humanMetric.dataset.metric='human';humanMetric.innerHTML='<strong id="mHuman">0</strong><span>your actions</span>';summary.appendChild(humanMetric);
  }
  const tracked=$('#mTracked')?.closest('.metric'); if(tracked) tracked.dataset.metric='tracked';
  const healthy=$('#mSuccess')?.closest('.metric'); if(healthy) healthy.dataset.metric='healthy';
  const progressing=$('#mRunning')?.closest('.metric'); if(progressing){progressing.dataset.metric='progressing';const s=$('span',progressing);if(s)s.textContent='frontiers advancing'}
  const attention=$('#mAttention')?.closest('.metric'); if(attention){attention.dataset.metric='attention';const s=$('span',attention);if(s)s.textContent='needs work'}
  const nodes=$('#mNodes')?.closest('.metric'); if(nodes) nodes.dataset.metric='nodes';

  let drawer=$('#ccDrawer');
  if(summary && !drawer){drawer=document.createElement('section');drawer.id='ccDrawer';drawer.className='cc-drawer';drawer.setAttribute('aria-live','polite');summary.insertAdjacentElement('afterend',drawer)}

  function cardInfo(card){
    const id=card.dataset.id||card.dataset.circleciCard?'circleci':'';
    const name=$('h3',card)?.textContent?.trim()||'System';
    const status=$('.pill',card)?.textContent?.trim()||'Unknown';
    const evidence=$('.evidence',card)?.textContent?.trim()||'No current evidence.';
    return {id,name,status,evidence,card};
  }
  function systems(){return $$('#systems .card').map(cardInfo)}
  function isAdvance(x){return semanticAdvance.has(x.status)||(x.status==='Waiting'&&physicalForkIds.has(x.id))}
  function isNeedsWork(x){return x.status==='Attention'||(x.status==='Waiting'&&!physicalForkIds.has(x.id))||x.status==='Unknown'}
  function ownerFor(x){
    if(x.status==='Attention' && (x.id==='pi4'||x.id==='hopper')) return {key:'you',label:'You / physical'};
    if(x.status==='Waiting' && physicalForkIds.has(x.id)) return {key:'none',label:'Fork continues'};
    if(isNeedsWork(x)) return {key:'system',label:'Aurum / system'};
    return {key:'none',label:'No action'};
  }
  function humanActions(){return systems().filter(x=>ownerFor(x).key==='you')}

  function applyProgress(){
    let advancing=0,needs=0;
    systems().forEach(x=>{
      let note=$('.progress-state',x.card);
      if(!note){note=document.createElement('div');note.className='progress-state';x.card.appendChild(note)}
      note.className='progress-state';
      if(semanticAdvance.has(x.status)){
        advancing++;note.classList.add('advance');note.textContent=x.status==='Running'?'↗ executing now':'↗ verified/experimental frontier remains active';
      }else if(x.status==='Waiting'&&physicalForkIds.has(x.id)){
        advancing++;note.classList.add('fork');note.textContent='↗ physical proof held; independent fork continues';
      }else if(isNeedsWork(x)){
        needs++;note.classList.add(x.status==='Attention'?'stall':'unknown');note.textContent=x.status==='Attention'?'■ stalled/failed — needs work':'○ next frontier evidence needed';
      }
    });
    if($('#mRunning')) $('#mRunning').textContent=String(advancing);
    if($('#mAttention')) $('#mAttention').textContent=String(needs);
    if($('#mHuman')) $('#mHuman').textContent=String(humanActions().length);
    if($('#mTracked')) $('#mTracked').textContent=String(systems().length);
  }

  function row(x){const o=ownerFor(x);return `<div class="cc-row"><b>${esc(x.name)}</b><span class="cc-owner ${o.key}">${esc(o.label)}</span><p><b style="color:#d8dced">${esc(x.status)}</b><br>${esc(x.evidence)}</p></div>`}
  function showMetric(metric){
    const key=metric.dataset.metric;const all=systems();let title='',desc='',items=[];
    if(key==='tracked'){title='Tracked workstreams';desc='Every system currently represented by the command center.';items=all}
    else if(key==='healthy'){title='Healthy / verified';desc='Current workstreams with verified evidence.';items=all.filter(x=>x.status==='Verified')}
    else if(key==='progressing'){title='Frontiers advancing';desc='Executing jobs, experimental frontiers, verified checkpoints with an open next frontier, and physical holds whose independent fork continues.';items=all.filter(isAdvance)}
    else if(key==='attention'){title='Needs work';desc='Frontiers that need engineering, evidence, diagnosis, or a concrete physical intervention. The owner column tells you whose work it is.';items=all.filter(isNeedsWork)}
    else if(key==='human'){title='Your action center';desc='Only work that currently appears to require your physical participation. Empty means you do not need to do anything right now.';items=humanActions()}
    else if(key==='nodes'){title='Known live-edge nodes';desc='Physical node telemetry is shown below; expand the Nodes panel for the full current directory.';items=[]}
    if(!drawer)return;
    drawer.innerHTML=`<div class="cc-drawer-head"><div><p class="eyebrow">COMMAND DETAIL</p><h2>${esc(title)}</h2><p>${esc(desc)}</p></div><button type="button" class="cc-close" aria-label="Close command detail">×</button></div>${items.length?`<div class="cc-list">${items.map(row).join('')}</div>`:`<div class="cc-empty">${key==='human'?'No confirmed action for you right now. Aurum/system work can continue independently.':key==='nodes'?'Tap the Nodes panel below to expand live node details.':'Nothing currently matches this category.'}</div>`}`;
    drawer.classList.add('show');
    $$('.summary .metric').forEach(m=>m.setAttribute('aria-expanded',String(m===metric)));
    $('.cc-close',drawer)?.addEventListener('click',closeDrawer,{once:true});
    drawer.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
  }
  function closeDrawer(){drawer?.classList.remove('show');$$('.summary .metric').forEach(m=>m.setAttribute('aria-expanded','false'))}

  $$('.summary .metric').forEach(metric=>{metric.tabIndex=0;metric.setAttribute('role','button');metric.setAttribute('aria-expanded','false')});
  summary?.addEventListener('click',e=>{const m=e.target.closest('.metric');if(m)showMetric(m)});
  summary?.addEventListener('keydown',e=>{const m=e.target.closest('.metric');if(m&&(e.key==='Enter'||e.key===' ')){e.preventDefault();showMetric(m)}});

  $$('.panel').forEach(panel=>{
    panel.classList.add('cc-clickable');panel.tabIndex=0;panel.setAttribute('role','button');panel.setAttribute('aria-expanded','false');
    const toggle=()=>{const on=!panel.classList.contains('cc-expanded');panel.classList.toggle('cc-expanded',on);panel.setAttribute('aria-expanded',String(on))};
    panel.addEventListener('click',e=>{if(e.target.closest('a,button,input,select,textarea'))return;toggle()});
    panel.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target===panel){e.preventDefault();toggle()}});
  });

  const sys=$('#systems');
  if(sys){new MutationObserver(()=>requestAnimationFrame(applyProgress)).observe(sys,{childList:true,subtree:true,characterData:true})}
  applyProgress();
  setInterval(applyProgress,15000);
})();
