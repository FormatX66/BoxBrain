/* AURUM_EVIDENCE_HEALTH_V1_1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Separates the hosted voice endpoint from the repository-backed static mirror so
 * a primary-route outage is visible without implying that Aurum voice evidence is gone.
 * Evidence-source problems are Aurum/system work and never invent a human task.
 */
(() => {
  'use strict';
  if (window.__aurumEvidenceHealthV11) return;
  window.__aurumEvidenceHealthV11 = true;

  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const STATIC_VOICE = 'https://raw.githubusercontent.com/FormatX66/BoxBrain/main/Web/Aurum-Arkmatx/voice-status.json';

  const style = document.createElement('style');
  style.textContent = `
    .evidence-health-card .eh-detail{display:none;margin-top:10px;padding-top:10px;border-top:1px solid #252b39;font-size:10px;line-height:1.5;color:#8f9bad}
    .evidence-health-card[aria-expanded="true"] .eh-detail{display:block}
    .evidence-health-card .eh-detail b{color:#c9c6ff}
    .evidence-health-card .eh-hint{margin-top:8px;font-size:8.5px;color:#747f92;font-weight:750}
  `;
  document.head.appendChild(style);

  let state = {
    hostedVoice: {ok:null, detail:'Checking hosted voice endpoint…'},
    staticVoice: {ok:null, detail:'Checking repository voice mirror…'},
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
      <p>Health and redundancy of the read-only sources that feed capability, node, and action truth into this command center.</p>
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
    const checks = [state.hostedVoice, state.staticVoice, state.edge];
    const pending = checks.some(x => x.ok === null);
    const voiceAvailable = state.hostedVoice.ok === true || state.staticVoice.ok === true;
    const hardFailure = state.edge.ok === false || (!pending && !voiceAvailable);
    const degraded = !pending && !hardFailure && checks.some(x => x.ok === false);
    const pill = $('.pill', card);
    const evidence = $('.evidence', card);
    const detail = $('.eh-detail', card);

    if (pending) {
      pill.className = 'pill running';
      pill.textContent = 'Running';
      evidence.textContent = 'Checking primary and fallback evidence channels…';
    } else if (hardFailure) {
      pill.className = 'pill failed';
      pill.textContent = 'Attention';
      evidence.textContent = 'Required evidence function unavailable · Aurum/system work, not your action';
    } else if (degraded) {
      pill.className = 'pill waiting';
      pill.textContent = 'Degraded';
      if (state.hostedVoice.ok === false && state.staticVoice.ok === true) {
        evidence.textContent = 'Hosted voice route unavailable · repository mirror verified · Aurum/system work, not your action';
      } else if (state.hostedVoice.ok === true && state.staticVoice.ok === false) {
        evidence.textContent = 'Hosted voice route verified · repository fallback unavailable · Aurum/system work, not your action';
      } else {
        evidence.textContent = 'Evidence redundancy degraded · primary truth remains readable · Aurum/system work, not your action';
      }
    } else {
      pill.className = 'pill success';
      pill.textContent = 'Verified';
      evidence.textContent = 'Hosted voice, repository fallback, and edge status are readable.';
    }

    detail.innerHTML = `<b>Hosted voice endpoint:</b> ${esc(state.hostedVoice.detail)}<br><b>Repository voice mirror:</b> ${esc(state.staticVoice.detail)}<br><b>Edge status:</b> ${esc(state.edge.detail)}<br><br>The repository mirror is a read-only fallback for voice/capability truth. A hosted-route outage can therefore be degraded rather than a total evidence loss. Unavailable evidence never creates a human task by itself.`;
  }

  function validateVoice(p) {
    if (p?.schema !== 'aurum-voice-status-v1' || !Array.isArray(p?.human_capabilities)) throw new Error('schema mismatch');
    if (p.human_capabilities.length !== 7) throw new Error(`expected 7 capabilities, got ${p.human_capabilities.length}`);
    return p;
  }

  async function checkHostedVoice() {
    try {
      const r = await fetch('/aurum/voice-status.json', {cache:'no-store'});
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const p = validateVoice(await r.json());
      state.hostedVoice = {ok:true, detail:`verified · ${p.human_capabilities.length} capability records`};
    } catch (e) {
      state.hostedVoice = {ok:false, detail:`unavailable · ${e?.message || 'request failed'}`};
    }
  }

  async function checkStaticVoice() {
    try {
      const r = await fetch(STATIC_VOICE, {cache:'no-store'});
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const p = validateVoice(await r.json());
      state.staticVoice = {ok:true, detail:`verified · public Git mirror · ${p.human_capabilities.length} capability records`};
    } catch (e) {
      state.staticVoice = {ok:false, detail:`unavailable · ${e?.message || 'request failed'}`};
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
    state.hostedVoice = {ok:null, detail:'Checking hosted voice endpoint…'};
    state.staticVoice = {ok:null, detail:'Checking repository voice mirror…'};
    state.edge = {ok:null, detail:'Checking edge status…'};
    render();
    await Promise.all([checkHostedVoice(), checkStaticVoice(), checkEdge()]);
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
