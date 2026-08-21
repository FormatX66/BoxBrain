/* Aurum Command Center v2 — public deploy projection.
 * Canonical website ownership remains FormatX66/ClusterSites.
 */
(() => {
  'use strict';
  if (window.__aurumCommandCenterV2) return;
  window.__aurumCommandCenterV2 = true;

  const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const advancing=new Set(['Verified','Running','Experiment']);
  const forkable=new Set(['hopper','pi4']);

  const css=document.createElement('style');
  css.textContent=`
  :root{--aurum:#6c63ff;--bg:#0c0f16!important;--panel:#151821!important;--panel2:#10131b!important;--border:#2a2f3d!important;--gold:#6c63ff!important;--purple:#a59eff!important;--blue:#8ea8ff!important}
  body{background:radial-gradient(circle at 18% -5%,#312d7438 0,transparent 34%),radial-gradient(circle at 92% 12%,#171a4430 0,transparent 30%),#0c0f16!important}.wrap{width:min(1240px,95vw)!important}
  .orb{width:52px!important;height:52px!important;border-radius:16px!important;background:linear-gradient(145deg,#7770ff,#4d45cf)!important;box-shadow:0 0 0 1px #a9a4ff44,0 10px 32px #6c63ff38!important;display:grid!important;place-items:center!important;position:relative!important;overflow:hidden!important}.orb::before{content:'A';font:900 29px/1 Inter,system-ui,sans-serif;color:#fff;letter-spacing:-.08em;transform:translateX(-1px)}.orb::after{content:'';position:absolute;inset:7px;border:1px solid #ffffff2c;border-radius:11px;transform:rotate(45deg) scale(.72)}
  .livebox,.metric,.card,.panel,.trait-panel,.trait{background:linear-gradient(180deg,#171a24e8,#12151ee8)!important;border-color:#2c3140!important;box-shadow:inset 0 1px 0 #ffffff08}.btn.primary{background:#6c63ff!important;color:#fff!important}.btn{background:#171b25!important;border-color:#363c4c!important}.pill.running{background:#25235a!important;color:#bcb7ff!important}.pill.experiment{background:#29234a!important;color:#bfb8ff!important}
  .metric{cursor:pointer;position:relative}.metric::after{content:'›';position:absolute;right:12px;top:9px;color:#747e93;font-size:18px}.metric:focus-visible,.metric[aria-expanded='true'],.card:hover,.trait:hover,.panel.cc-panel:hover{outline:none;border-color:#6c63ff!important;box-shadow:0 0 0 1px #6c63ff2a}.metric strong{color:#f2f1ff}.metric.cc-human strong{color:#efbd63}
  .cc-state{margin:0 0 16px;border:1px solid #303647;border-radius:14px;background:#10131bd9;padding:11px 13px;display:flex;justify-content:space-between;gap:12px;align-items:center}.cc-state b{font-size:11px;color:#c9c6ff}.cc-state span{font-size:10px;color:#858fa2}.cc-state em{font-style:normal;padding:6px 9px;border-radius:999px;background:#242150;color:#bcb7ff;font-size:9px;font-weight:850;letter-spacing:.06em;text-transform:uppercase}
  .cc-drawer{display:none;margin:12px 0 18px;border:1px solid #343b4c;border-radius:18px;background:linear-gradient(180deg,#161a25,#10131b);padding:16px}.cc-drawer.show{display:block}.cc-head{display:flex;justify-content:space-between;gap:12px}.cc-head h2{font-size:18px;margin:0}.cc-head p{font-size:11px;color:#929bad;line-height:1.5;margin:4px 0 0}.cc-close{width:42px;height:42px;border:1px solid #363c4c;background:#181c27;color:#eef0ff;border-radius:11px}.cc-list{display:grid;gap:8px;margin-top:14px}.cc-row{display:grid;grid-template-columns:minmax(140px,.7fr) 100px minmax(0,1.5fr);gap:10px;padding:11px;border:1px solid #282e3c;border-radius:12px;background:#10141c}.cc-row b{font-size:12px}.cc-row p{font-size:10.5px;color:#8f9bad;line-height:1.45;margin:0}.cc-owner{width:max-content;height:max-content;padding:5px 7px;border-radius:999px;font-size:9px;text-transform:uppercase;letter-spacing:.07em;font-weight:850}.cc-owner.system{background:#20244b;color:#b8b3ff}.cc-owner.you{background:#3b3017;color:#f0c76a}.cc-owner.none{background:#173428;color:#8ce7b2}.cc-empty{margin-top:12px;padding:13px;border:1px dashed #343b4c;border-radius:12px;color:#8f9bad;font-size:11px}
  .progress-state{margin-top:7px;font-size:10px;font-weight:750}.progress-state.advance{color:#8ce7b2}.progress-state.fork{color:#efbd63}.progress-state.work{color:#ff9da6}.progress-state.unknown{color:#8f9bad}
  .panel.cc-panel{cursor:pointer}.panel.cc-panel::after{content:'Tap to expand';display:block;margin-top:10px;font-size:9px;color:#737e92;font-weight:750}.panel.cc-expanded{grid-column:1/-1;border-color:#6c63ff!important}.panel.cc-expanded::after{content:'Expanded'}
  @media(max-width:920px){.summary{grid-template-columns:repeat(3,minmax(0,1fr))!important}.cc-row{grid-template-columns:minmax(120px,.8fr) 95px minmax(0,1.2fr)}}@media(max-width:680px){.summary{grid-template-columns:repeat(2,minmax(0,1fr))!important}.cc-row{grid-template-columns:1fr}.cc-state{align-items:flex-start;flex-direction:column}.orb{width:46px!important;height:46px!important}}
  `;
  document.head.appendChild(css);
  const meta=$('meta[name="theme-color"]');if(meta)meta.content='#0c0f16';
  const small=$('.brand small');if(small)small.textContent='Aurum • live machine command center';
  const eye=$('.brand .eyebrow');if(eye)eye.textContent='AURUM';
  const orb=$('.orb');if(orb){orb.setAttribute('aria-label','Aurum');orb.removeAttribute('aria-hidden')}

  const actions=$('.actions');
  if(actions&&!$('.cc-state')){const d=document.createElement('div');d.className='cc-state';d.innerHTML='<div><b>Command state</b><br><span>Independent frontiers continue unless a real dependency or human-only gate stops that frontier.</span></div><em>state-first</em>';actions.insertAdjacentElement('afterend',d)}

  const summary=$('.summary');
  if(summary&&!$('#mHuman')){const m=document.createElement('div');m.className='metric cc-human';m.dataset.metric='human';m.innerHTML='<strong id="mHuman">0</strong><span>your actions</span>';summary.appendChild(m)}
  const map=[['mTracked','tracked'],['mSuccess','healthy'],['mRunning','progressing'],['mAttention','attention'],['mHuman','human'],['mNodes','nodes']];
  map.forEach(([id,key])=>{const m=$('#'+id)?.closest('.metric');if(m){m.dataset.metric=key;m.tabIndex=0;m.setAttribute('role','button');m.setAttribute('aria-expanded','false')}});
  const pr=$('#mRunning')?.closest('.metric');if(pr){const s=$('span',pr);if(s)s.textContent='frontiers advancing'}
  const at=$('#mAttention')?.closest('.metric');if(at){const s=$('span',at);if(s)s.textContent='needs work'}

  let drawer=$('#ccDrawerV2');
  if(summary&&!drawer){drawer=document.createElement('section');drawer.id='ccDrawerV2';drawer.className='cc-drawer';drawer.setAttribute('aria-live','polite');summary.insertAdjacentElement('afterend',drawer)}

  function info(card){return {id:card.dataset.circleciCard?'circleci':(card.dataset.id||''),name:$('h3',card)?.textContent?.trim()||'System',status:$('.pill',card)?.textContent?.trim()||'Unknown',evidence:$('.evidence',card)?.textContent?.trim()||'No current evidence.',card}}
  function systems(){return $$('#systems .card').map(info)}
  function isAdv(x){return advancing.has(x.status)||(x.status==='Waiting'&&forkable.has(x.id))}
  function needs(x){return x.status==='Attention'||x.status==='Unknown'||(x.status==='Waiting'&&!forkable.has(x.id))}
  function owner(x){if(x.status==='Attention'&&(x.id==='hopper'||x.id==='pi4'))return ['you','You / physical'];if(x.status==='Waiting'&&forkable.has(x.id))return ['none','Fork continues'];if(needs(x))return ['system','Aurum / system'];return ['none','No action']}
  function yours(){return systems().filter(x=>owner(x)[0]==='you')}

  function refresh(){let a=0,n=0;systems().forEach(x=>{let p=$('.progress-state',x.card);if(!p){p=document.createElement('div');x.card.appendChild(p)}p.className='progress-state';if(advancing.has(x.status)){a++;p.classList.add('advance');p.textContent=x.status==='Running'?'↗ executing now':'↗ active frontier / verified checkpoint'}else if(x.status==='Waiting'&&forkable.has(x.id)){a++;p.classList.add('fork');p.textContent='↗ physical proof held; independent fork continues'}else if(needs(x)){n++;p.classList.add(x.status==='Attention'?'work':'unknown');p.textContent=x.status==='Attention'?'■ needs work — open details':'○ frontier evidence needed'}});if($('#mRunning'))$('#mRunning').textContent=String(a);if($('#mAttention'))$('#mAttention').textContent=String(n);if($('#mHuman'))$('#mHuman').textContent=String(yours().length);if($('#mTracked'))$('#mTracked').textContent=String(systems().length)}

  function row(x){const [k,l]=owner(x);return `<div class="cc-row"><b>${esc(x.name)}</b><span class="cc-owner ${k}">${esc(l)}</span><p><b style="color:#d9dceb">${esc(x.status)}</b><br>${esc(x.evidence)}</p></div>`}
  function show(m){const key=m.dataset.metric,all=systems();let title='',desc='',items=[];if(key==='tracked'){title='Tracked workstreams';desc='Every system currently represented by the Aurum command center.';items=all}else if(key==='healthy'){title='Healthy / verified';desc='Workstreams with current verified evidence.';items=all.filter(x=>x.status==='Verified')}else if(key==='progressing'){title='Frontiers advancing';desc='What is actually moving: executing jobs, experiments, verified checkpoints with an active next frontier, and forked physical holds.';items=all.filter(isAdv)}else if(key==='attention'){title='Needs work';desc='Everything that needs engineering, evidence, diagnosis, or a concrete physical intervention. The owner column tells you who owns the next move.';items=all.filter(needs)}else if(key==='human'){title='Your action center';desc='Only confirmed physical work assigned to you. Empty means you do not need to do anything right now.';items=yours()}else if(key==='nodes'){title='Node command view';desc='Expand the Nodes panel below for live physical-edge details.';items=[]}if(!drawer)return;drawer.innerHTML=`<div class="cc-head"><div><p class="eyebrow">COMMAND DETAIL</p><h2>${esc(title)}</h2><p>${esc(desc)}</p></div><button class="cc-close" type="button" aria-label="Close">×</button></div>${items.length?`<div class="cc-list">${items.map(row).join('')}</div>`:`<div class="cc-empty">${key==='human'?'No confirmed action for you right now. Aurum/system work can continue independently.':key==='nodes'?'Tap the Nodes panel to expand live node detail.':'Nothing currently matches this category.'}</div>`}`;drawer.classList.add('show');$$('.summary .metric').forEach(x=>x.setAttribute('aria-expanded',String(x===m)));$('.cc-close',drawer)?.addEventListener('click',()=>{drawer.classList.remove('show');$$('.summary .metric').forEach(x=>x.setAttribute('aria-expanded','false'))},{once:true})}

  summary?.addEventListener('click',e=>{const m=e.target.closest('.metric');if(m)show(m)});summary?.addEventListener('keydown',e=>{const m=e.target.closest('.metric');if(m&&(e.key==='Enter'||e.key===' ')){e.preventDefault();show(m)}});
  $$('.panel').forEach(p=>{p.classList.add('cc-panel');p.tabIndex=0;p.setAttribute('role','button');p.setAttribute('aria-expanded','false');const toggle=()=>{const on=!p.classList.contains('cc-expanded');p.classList.toggle('cc-expanded',on);p.setAttribute('aria-expanded',String(on))};p.addEventListener('click',e=>{if(!e.target.closest('a,button,input,select,textarea'))toggle()});p.addEventListener('keydown',e=>{if(e.target===p&&(e.key==='Enter'||e.key===' ')){e.preventDefault();toggle()}})});
  const sys=$('#systems');if(sys)new MutationObserver(()=>requestAnimationFrame(refresh)).observe(sys,{childList:true,subtree:true,characterData:true});refresh();setInterval(refresh,15000);
})();
