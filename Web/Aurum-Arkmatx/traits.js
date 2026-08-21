/* Aurum trait-development projection.
 * Canonical website component: FormatX66/ClusterSites.
 * Public dashboard projection: FormatX66/BoxBrain.
 * Progress means evidence maturity, not calendar/time completion.
 */
(() => {
  'use strict';
  if (document.querySelector('[data-aurum-traits]')) return;

  const REPO = 'FormatX66/BoxBrain';
  const API = `https://api.github.com/repos/${REPO}`;
  const rootSection = document.querySelector('#systems')?.closest('section');
  if (!rootSection) return;

  const style = document.createElement('style');
  style.textContent = `
    .trait-panel{border:1px solid #253246;background:#101720d9;border-radius:15px;padding:15px}
    .trait-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
    .trait{min-width:0;padding:13px;border:1px solid #202d3e;background:#0d141d;border-radius:13px}
    .trait-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:8px}
    .trait-name{font-size:13px;font-weight:800;color:#eef3f8}
    .trait-pct{font:800 13px ui-monospace,SFMono-Regular,Menlo,monospace;color:#e0bd62;white-space:nowrap}
    .trait-desc{font-size:10.5px;line-height:1.4;color:#8295a8;margin:0 0 10px}
    .trait-track{height:10px;background:#1c2734;border-radius:999px;overflow:hidden;position:relative}
    .trait-fill{height:100%;width:0;border-radius:999px;background:linear-gradient(90deg,#a88739,#e0bd62);transition:width .45s ease}
    .trait-marks{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;margin-top:8px}
    .trait-mark{font-size:9px;color:#61768b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .trait-mark.on{color:#9fdcb7}
    .trait-mark::before{content:'○';margin-right:3px}.trait-mark.on::before{content:'●'}
    .trait-note{margin-top:10px;font-size:10px;color:#71869b;line-height:1.45}
    .trait-loading{font-size:11px;color:#8fa0b2}
    @media(max-width:680px){.trait-grid{grid-template-columns:1fr}.trait-mark{font-size:8.5px}}
    @media(prefers-reduced-motion:reduce){.trait-fill{transition:none}}
  `;
  document.head.appendChild(style);

  const section = document.createElement('section');
  section.className = 'section';
  section.dataset.aurumTraits = 'true';
  section.innerHTML = `
    <div class="section-head">
      <div><p class="eyebrow">TRAIT DEVELOPMENT</p><h2>What Aurum is growing</h2></div>
      <span id="traitState" class="section-note">Loading evidence…</span>
    </div>
    <div class="trait-panel">
      <div id="traitGrid" class="trait-grid"><div class="trait-loading">Reading current build evidence…</div></div>
      <div class="trait-note">Bars measure evidence maturity in four equal gates: Defined → Implementation → Build lane → Verified. They are not schedule estimates.</div>
    </div>`;
  rootSection.insertAdjacentElement('afterend', section);

  const grid = section.querySelector('#traitGrid');
  const stateLabel = section.querySelector('#traitState');
  let commits = [], runs = [];

  const textOfCommits = () => commits.map(c => String(c.commit?.message || '')).join('\n');
  const textOfRuns = () => runs.map(r => String(r.name || '')).join('\n');
  const hasCommit = rx => rx.test(textOfCommits());
  const hasRun = rx => rx.test(textOfRuns());
  const hasSuccess = rx => runs.some(r => rx.test(String(r.name || '')) && r.conclusion === 'success');
  const flashVerified = () => hasCommit(/PC-01 flash receipt state=(FLASH_OK|ALREADY_COMPLETE)/i);

  const traits = [
    {
      name:'Continuous Self-Building',
      desc:'Aurum rebuilding, healing and advancing itself without point-update thinking.',
      impl:()=>hasCommit(/self[- ]build|self[- ]heal|local-lane|controller/i),
      lane:()=>hasRun(/self[- ]build|self[- ]heal|local.lane|controller/i),
      verified:()=>hasSuccess(/self[- ]build|self[- ]heal|local.lane|controller/i)||hasCommit(/local-lane repair validation/i)
    },
    {
      name:'Seed Propagation',
      desc:'Verified seeds moving from build lanes into flashable and bootable machines.',
      impl:()=>hasCommit(/seed|flash/i),
      lane:()=>hasRun(/seed|flash|image/i),
      verified:()=>flashVerified()||hasSuccess(/seed|flash/i)
    },
    {
      name:'Adaptive Kernel',
      desc:'Kernel behavior that can specialize itself to the machine it is running on.',
      impl:()=>hasCommit(/adaptive kernel|kernel experiment/i),
      lane:()=>hasRun(/adaptive kernel|experimental lane|experiment race/i),
      verified:()=>hasSuccess(/adaptive kernel/i)
    },
    {
      name:'StateWeave',
      desc:'Machine-native state organization and execution that reduces human-code mediation.',
      impl:()=>hasCommit(/stateweave|state weave/i),
      lane:()=>hasRun(/stateweave|state weave|experimental lane|experiment race/i),
      verified:()=>hasSuccess(/stateweave|state weave/i)
    },
    {
      name:'Hardware Learning',
      desc:'Nodes learning real hardware behavior and feeding that evidence back into future generations.',
      impl:()=>hasCommit(/bbpi4|pi4|hopper|hardware/i),
      lane:()=>hasRun(/bbpi4|pi4|hopper|hardware/i),
      verified:()=>hasSuccess(/bbpi4|pi4|hopper/i)||flashVerified()
    },
    {
      name:'Driver Synthesis',
      desc:'Moving toward drivers that are generated or adapted from observed hardware needs.',
      impl:()=>hasCommit(/driver|device support/i),
      lane:()=>hasRun(/driver|device support/i),
      verified:()=>hasSuccess(/driver|device support/i)
    },
    {
      name:'Resilient Connectivity',
      desc:'USB, Ethernet, Wi-Fi and route recovery treated as interchangeable carriers.',
      impl:()=>hasCommit(/ssh|route|network|heartbeat|enroll|usb-c|ap probe/i),
      lane:()=>hasRun(/ssh|route|network|heartbeat|enroll|bbpi4|ap probe/i),
      verified:()=>hasSuccess(/route|heartbeat|enroll|bbpi4|ap probe/i)
    },
    {
      name:'Adaptive GUI',
      desc:'A human view that can change form while the machine-first system remains underneath.',
      impl:()=>hasCommit(/gui|trackpad|mouse|loading screen|desktop/i),
      lane:()=>hasRun(/gui|hopper|desktop/i),
      verified:()=>hasSuccess(/gui|hopper|desktop/i)
    },
    {
      name:'Continuous Identity',
      desc:'Confidence-based identity using behavior and context instead of a single password event.',
      impl:()=>hasCommit(/identity|authentication|keystroke|behavioral|confidence/i),
      lane:()=>hasRun(/identity|authentication|keystroke|behavioral/i),
      verified:()=>hasSuccess(/identity|authentication|keystroke|behavioral/i)
    }
  ];

  function render() {
    grid.innerHTML = '';
    traits.forEach(t => {
      const gates = [true, !!t.impl(), !!t.lane(), !!t.verified()];
      const pct = gates.filter(Boolean).length * 25;
      const labels = ['Defined','Built','Lane','Verified'];
      const card = document.createElement('article');
      card.className = 'trait';
      card.innerHTML = `
        <div class="trait-top"><div class="trait-name"></div><div class="trait-pct">${pct}%</div></div>
        <p class="trait-desc"></p>
        <div class="trait-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}" aria-label="${t.name} evidence maturity"><div class="trait-fill" style="width:${pct}%"></div></div>
        <div class="trait-marks">${labels.map((l,i)=>`<span class="trait-mark ${gates[i]?'on':''}">${l}</span>`).join('')}</div>`;
      card.querySelector('.trait-name').textContent = t.name;
      card.querySelector('.trait-desc').textContent = t.desc;
      grid.appendChild(card);
    });
  }

  async function refreshTraits() {
    try {
      const [cr, rr] = await Promise.all([
        fetch(`${API}/commits?sha=main&per_page=100`, {cache:'no-store', headers:{Accept:'application/vnd.github+json'}}),
        fetch(`${API}/actions/runs?branch=main&per_page=100`, {cache:'no-store', headers:{Accept:'application/vnd.github+json'}})
      ]);
      if (!cr.ok || !rr.ok) throw new Error(`GitHub ${cr.status}/${rr.status}`);
      commits = await cr.json();
      runs = (await rr.json()).workflow_runs || [];
      render();
      stateLabel.textContent = `Evidence refreshed ${new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit'})}`;
    } catch (err) {
      render();
      stateLabel.textContent = 'Evidence partially unavailable';
      stateLabel.classList.add('error');
    }
  }

  refreshTraits();
  window.setInterval(refreshTraits, 300000);
})();
