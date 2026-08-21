/* AURUM_EVIDENCE_HEALTH_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Makes dashboard evidence-source outages visible as Aurum/system work without inventing a human task.
 */
(() => {
  'use strict';
  if (window.__aurumEvidenceHealthV1) return;
  window.__aurumEvidenceHealthV1 = true;

  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  const style = document.createElement('style');
  style.textContent = `
    .evidence-health-card .eh-detail{display:none;margin-top:10px;padding-top:10px;border-top:1px solid #252b39;font-size:10px;line-height:1.5;color:#8f9bad}
    .evidence-health-card[aria-expanded="true"] .eh-detail{display:block}
    .evidence-health-card .eh-detail b{color:#c9c6ff}
    .evidence-health-card .eh-hint{margin-top:8px;font-size:8.5px;color:#747f92;font-weight:750}
  `;
  document.head.appendChild(style);

  let state = {
    voice: {ok:null, detail:'Checking voice mirror…'},
    edge: {ok:null, detail:'Checking edge status…'},
    checkedAt: 0,
  };

  function ensureCard() {
    const systems = $('#systems');
    if (!systems) return null;
    let card = $('[data-id="evidence"]', systems);
    if (card) return card;
    card = document.createElement('article');
    card.className = 'system-card evidence-health-card';
    card.dataset.id = 'evidence';
    card.tabIndex = 0;
    card.setAttribute('role','button');
    card.setAttribute('aria-expanded','false');
    card.innerHTML = `
      <div class="card-head"><div class="card-icon">◈</div><span class="pill unknown">Unknown</span></div>
      <h3>Evidence Sources</h3>
      <p>Health of the read-only sources that feed capability, node, and action truth into this command center.</p>
      <div class="evidence">Checking dashboard evidence channels…</div>
      <div class="eh-hint">Tap to expand source health →</div>
      <div class="eh-detail"></div>`;
    const toggle = event => {
      if (event?.type === 'keydown' && !['Enter',' '].includes(event.key)) return;
      if (event?.type === 'keydown') event.preventDefault();
      const on = card.getAttribute('aria-expanded') !== 'true';
      card.setAttribute('aria-expanded', String(on));
      event?.stopPropagation?.();
    };
    card.addEventListener('click', toggle);
    card.addEventListener('keydown', toggle);
    systems.appendChild(card);
    return card;
  }

  function render() {
    const card = ensureCard();
    if (!card) return;
    const checks = [state.voice, state.edge];
    const pending = checks.some(x => x.ok === null);
    const failed = checks.filter(x => x.ok === false).length;
    const pill = $('.pill', card);
    const evidence = $('.evidence', card);
    const detail = $('.eh-detail', card);
    if (pending) {
      pill.className = 'pill running';
      pill.textContent = 'Running';
      evidence.textContent = 'Checking evidence channels…';
    } else if (failed) {
      pill.className = 'pill failed';
      pill.textContent = 'Attention';
      evidence.textContent = `${failed} evidence source${failed === 1 ? '' : 's'} unavailable · Aurum/system work, not your action`;
    } else {
      pill.className = 'pill success';
      pill.textContent = 'Verified';
      evidence.textContent = 'Voice mirror and edge status are currently readable.';
    }
    detail.innerHTML = `<b>Voice mirror:</b> ${esc(state.voice.detail)}<br><b>Edge status:</b> ${esc(state.edge.detail)}<br><br>Unavailable evidence is shown as unknown/degraded elsewhere; it never creates a human task by itself.`;
  }

  async function checkVoice() {
    try {
      const r = await fetch('/aurum/voice-status.json', {cache:'no-store'});
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const p = await r.json();
      if (p?.schema !== 'aurum-voice-status-v1' || !Array.isArray(p?.human_capabilities)) throw new Error('schema mismatch');
      state.voice = {ok:true, detail:`verified · ${p.human_capabilities.length} capability records`};
    } catch (e) {
      state.voice = {ok:false, detail:`unavailable · ${e?.message || 'request failed'}`};
    }
  }

  async function checkEdge() {
    try {
      const r = await fetch('/aurum/index.php', {cache:'no-store'});
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const text = await r.text();
      if (!text.includes('Aurum-Arkmatx')) throw new Error('identity marker missing');
      state.edge = {ok:true, detail:'verified · Aurum-Arkmatx status endpoint readable'};
    } catch (e) {
      state.edge = {ok:false, detail:`unavailable · ${e?.message || 'request failed'}`};
    }
  }

  async function refresh() {
    ensureCard();
    state.voice = {ok:null, detail:'Checking voice mirror…'};
    state.edge = {ok:null, detail:'Checking edge status…'};
    render();
    await Promise.all([checkVoice(), checkEdge()]);
    state.checkedAt = Date.now();
    render();
  }

  function boot() {
    if (!$('#systems')) {
      setTimeout(boot, 250);
      return;
    }
    refresh();
    setInterval(refresh, 30000);
  }
  boot();
})();
