/* AURUM_OPERATOR_COMMANDS_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Surfaces only repository-backed commands; Proposed commands are never presented as runnable.
 * Parses the live registry by table headers so command-state evidence can evolve safely.
 */
(() => {
  'use strict';
  if (window.__aurumOperatorCommandsV1) return;
  window.__aurumOperatorCommandsV1 = true;

  const RAW = 'https://raw.githubusercontent.com/FormatX66/BoxBrain/main/docs/AURUM_COMMANDS.md';
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let commands = [];
  let error = '';

  const style = document.createElement('style');
  style.textContent = `
    .cc32-summary{grid-template-columns:repeat(7,minmax(0,1fr))!important}
    .aurum-command-row code{font:700 11px ui-monospace,SFMono-Regular,Menlo,monospace;color:#d8d4ff}
    .aurum-command-row .proposed{background:#3a2e16;color:#f0c76a}
    .aurum-command-row .implemented{background:#22294a;color:#abbcff}
    .aurum-command-row .tested{background:#263a42;color:#9cdce5}
    .aurum-command-row .physical{background:#173428;color:#8ce7b2}
    .aurum-command-row .documented{background:#29243c;color:#cfc6ff}
    .aurum-command-summary{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}
    .aurum-command-chip{padding:5px 8px;border-radius:999px;background:#1b202c;border:1px solid #303748;color:#aab4c8;font-size:9px;font-weight:800}
    .aurum-command-chip strong{color:#eef0ff}
    .aurum-command-links{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
    .aurum-command-links a{min-height:36px;display:inline-flex;align-items:center;padding:7px 10px;border:1px solid #363c4c;border-radius:9px;background:#171b25;color:#dfe1ff;text-decoration:none;font-size:10px;font-weight:760}
    @media(max-width:1180px){.cc32-summary{grid-template-columns:repeat(4,minmax(0,1fr))!important}}
    @media(max-width:700px){.cc32-summary{grid-template-columns:repeat(2,minmax(0,1fr))!important}}
  `;
  document.head.appendChild(style);

  function cells(line) {
    return line.split('|').slice(1, -1).map(x => x.trim());
  }

  function parse(text) {
    const out = [];
    let section = '';
    let headers = null;
    for (const raw of text.split(/\r?\n/)) {
      const line = raw.trim();
      if (/^##\s+/.test(line)) {
        section = line.replace(/^##\s+/, '').trim();
        headers = null;
        continue;
      }
      if (!line.startsWith('|')) continue;
      const c = cells(line);
      if (!c.length) continue;
      if (/^command$/i.test(c[0])) {
        headers = c.map(x => x.toLowerCase());
        continue;
      }
      if (!headers || /^[-: ]+$/.test(c[0])) continue;
      const match = c[0].match(/`([^`]+)`/);
      if (!match) continue;
      const value = name => {
        const i = headers.indexOf(name);
        return i >= 0 ? (c[i] || '') : '';
      };
      const purposeIndex = headers.findIndex(h => h.includes('purpose') || h.includes('boundary') || h.includes('evidence') || h.includes('behavior'));
      const state = value('state');
      if (!state) continue;
      out.push({
        command: match[1],
        state,
        scope: value('scope'),
        purpose: purposeIndex >= 0 ? (c[purposeIndex] || '') : '',
        section
      });
    }
    return out;
  }

  function ready() { return $('.cc32-summary') && $('.cc32-drawer'); }
  function stateKey(state) { return String(state || '').toLowerCase().replace(/[^a-z0-9]+/g, '-'); }
  function runnable(x) { return !/^proposed$/i.test(x.state); }
  function countState(name) { return commands.filter(x => new RegExp(`^${name}$`, 'i').test(x.state)).length; }

  function metric() {
    let m = $('#aurumCommandsMetric');
    if (m) return m;
    const sum = $('.cc32-summary');
    if (!sum) return null;
    m = document.createElement('button');
    m.id = 'aurumCommandsMetric';
    m.className = 'cc32-metric';
    m.type = 'button';
    m.setAttribute('aria-expanded', 'false');
    m.innerHTML = '<strong id="aurumCommandsCount">—</strong><span>operator commands</span>';
    sum.appendChild(m);
    m.addEventListener('click', () => show(m));
    return m;
  }

  function show(m) {
    const drawer = $('.cc32-drawer');
    if (!drawer) return;
    const available = commands.filter(runnable);
    const proposed = commands.filter(x => /^proposed$/i.test(x.state));
    const physical = countState('Physical');
    const implemented = countState('Implemented');
    const documented = countState('Documented');
    const tested = countState('Tested');
    const rows = commands.map(x => {
      const detail = [x.scope, x.purpose].filter(Boolean).join(' — ');
      return `<div class="cc32-row aurum-command-row"><b><code>${esc(x.command)}</code></b><span class="cc32-owner ${esc(stateKey(x.state))}">${esc(x.state)}</span><p>${esc(detail || x.section || 'Repository-backed Aurum command.')}</p></div>`;
    }).join('');
    const summary = error ? '' : `<div class="aurum-command-summary"><span class="aurum-command-chip"><strong>${physical}</strong> Hopper-proven</span><span class="aurum-command-chip"><strong>${implemented}</strong> implemented</span>${tested ? `<span class="aurum-command-chip"><strong>${tested}</strong> tested</span>` : ''}<span class="aurum-command-chip"><strong>${documented}</strong> BoxBrain confirmations</span>${proposed.length ? `<span class="aurum-command-chip"><strong>${proposed.length}</strong> proposed / not runnable</span>` : ''}</div>`;
    drawer.innerHTML = `<div class="cc32-head"><div><p class="eyebrow">COMMAND REGISTRY</p><h2>Operator Commands</h2><p>${error ? esc(error) : `${available.length} repository-backed commands are currently available for their exact documented scope. ${physical} have physical Hopper proof. Commands marked Implemented exist but still await physical proof where applicable.`}</p>${summary}</div><button class="cc32-close" type="button">×</button></div>${rows ? `<div class="cc32-list">${rows}</div>` : '<div class="cc32-empty">Command registry evidence is unavailable. Do not invent a replacement command; this is a system evidence gap, not a human task.</div>'}<div class="aurum-command-links"><a href="https://github.com/FormatX66/BoxBrain/blob/main/docs/AURUM_COMMANDS.md" target="_blank" rel="noopener">Open canonical command registry ↗</a></div>`;
    drawer.classList.add('show');
    document.querySelectorAll('.cc32-metric').forEach(x => x.setAttribute('aria-expanded', String(x === m)));
    $('.cc32-close', drawer).onclick = () => {
      drawer.classList.remove('show');
      document.querySelectorAll('.cc32-metric').forEach(x => x.setAttribute('aria-expanded', 'false'));
    };
  }

  async function load() {
    try {
      const r = await fetch(`${RAW}?t=${Date.now()}`, {cache:'no-store'});
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      commands = parse(await r.text());
      if (!commands.length) throw new Error('registry contained no command rows');
      error = '';
    } catch (e) {
      commands = [];
      error = `Command registry unavailable (${e.message || e}).`;
    }
    const m = metric();
    const available = commands.filter(runnable);
    const physical = countState('Physical');
    const count = $('#aurumCommandsCount');
    if (count) count.textContent = commands.length ? String(available.length) : '—';
    if (m) m.title = commands.length ? `${available.length} repository-backed commands; ${physical} physically proven on Hopper` : 'Registry unavailable';
  }

  function boot() {
    if (!ready()) { setTimeout(boot, 250); return; }
    metric();
    load();
    setInterval(load, 5 * 60 * 1000);
  }
  boot();
})();
