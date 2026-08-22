/* AURUM_EVIDENCE_HEALTH_V1_2_CANONICAL
 * AURUM_EVIDENCE_HEALTH_V1_1_CANONICAL compatibility marker.
 * Canonical website owner: FormatX66/ClusterSites.
 * Separates transport/readability from freshness so an old voice mirror is never
 * presented as current operator truth merely because the JSON still loads.
 * Evidence-source problems are Aurum/system work and never invent a human task.
 */
(() => {
  'use strict';
  if (window.__aurumEvidenceHealthV12) return;
  window.__aurumEvidenceHealthV12 = true;

  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const STATIC_VOICE = 'https://raw.githubusercontent.com/FormatX66/BoxBrain/main/Web/Aurum-Arkmatx/voice-status.json';
  const VOICE_FRESH_MS = 6 * 60 * 60 * 1000;

  const style = document.createElement('style');
  style.textContent = `
    .evidence-health-card .eh-detail{display:none;margin-top:10px;padding-top:10px;border-top:1px solid #252b39;font-size:10px;line-height:1.5;color:#8f9bad}
    .evidence-health-card[aria-expanded="true"] .eh-detail{display:block}
    .evidence-health-card .eh-detail b{color:#c9c6ff}
    .evidence-health-card .eh-hint{margin-top:8px;font-size:8.5px;color:#747f92;font-weight:750}
  `;
  document.head.appendChild(style);

  let state = {
    hostedVoice: {ok:null, fresh:null, detail:'Checking hosted voice endpoint…'},
    staticVoice: {ok:null, fresh:null, detail:'Checking repository voice mirror…'},
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
      <p>Health, redundancy, and freshness of the read-only sources that feed capability, node, and action truth into this command center.</p>
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

  function ageText(ms) {
    const min = Math.max(0, Math.floor(Number(ms || 0) / 60000));
    if (min < 60) return `${min}m old`;
    const h = Math.floor(min / 60), rem = min % 60;
    return rem ? `${h}h ${rem}m old` : `${h}h old`;
  }

  function inspectVoice(p) {
    if (p?.schema !== 'aurum-voice-status-v1' || !Array.isArray(p?.human_capabilities)) throw new Error('schema mismatch');
    if (p.human_capabilities.length !== 7) throw new Error(`expected 7 capabilities, got ${p.human_capabilities.length}`);
    const generatedMs = Date.parse(p.generated_at_utc || '');
    if (!Number.isFinite(generatedMs)) return {fresh:false, ageMs:null, generatedAt:p.generated_at_utc || 'unknown'};
    const ageMs = Date.now() - generatedMs;
    return {fresh: ageMs >= -5 * 60 * 1000 && ageMs <= VOICE_FRESH_MS, ageMs, generatedAt:p.generated_at_utc};
  }

  function voiceState(p, label) {
    const meta = inspectVoice(p);
    const age = meta.ageMs === null ? 'timestamp unavailable' : ageText(meta.ageMs);
    return {
      ok:true,
      fresh:meta.fresh,
      generatedAt:meta.generatedAt,
      ageMs:meta.ageMs,
      detail:`readable · ${label} · ${p.human_capabilities.length} capability records · ${age}${meta.fresh ? '' : ' · stale for operator-action use'}`,
    };
  }

  function render() {
    const card = ensureCard();
    if (!card) return;
    const checks = [state.hostedVoice, state.staticVoice, state.edge];
    const pending = checks.some(x => x.ok === null);
    const voiceReadable = state.hostedVoice.ok === true || state.staticVoice.ok === true;
    const voiceFresh = (state.hostedVoice.ok === true && state.hostedVoice.fresh === true) || (state.staticVoice.ok === true && state.staticVoice.fresh === true);
    const hardFailure = state.edge.ok === false || (!pending && !voiceReadable);
    const degraded = !pending && !hardFailure && (checks.some(x => x.ok === false) || !voiceFresh);
    const pill = $('.pill', card);
    const evidence = $('.evidence', card);
    const detail = $('.eh-detail', card);

    if (pending) {
      pill.className = 'pill running';
      pill.textContent = 'Running';
      evidence.textContent = 'Checking evidence readability and freshness…';
    } else if (hardFailure) {
      pill.className = 'pill failed';
      pill.textContent = 'Attention';
      evidence.textContent = 'Required evidence function unavailable · Aurum/system work, not your action';
    } else if (degraded) {
      pill.className = 'pill waiting';
      pill.textContent = 'Waiting';
      if (!voiceFresh && voiceReadable) {
        evidence.textContent = 'Voice evidence is readable but stale · current action/capability truth may lag · Aurum/system work, not your action';
      } else if (state.hostedVoice.ok === false && state.staticVoice.ok === true) {
        evidence.textContent = 'Evidence redundancy degraded · hosted voice route unavailable · repository mirror fresh/readable · Aurum/system work, not your action';
      } else if (state.hostedVoice.ok === true && state.staticVoice.ok === false) {
        evidence.textContent = 'Evidence redundancy degraded · hosted voice route fresh/readable · repository fallback unavailable · Aurum/system work, not your action';
      } else {
        evidence.textContent = 'Evidence redundancy/freshness degraded · Aurum/system work, not your action';
      }
    } else {
      pill.className = 'pill success';
      pill.textContent = 'Verified';
      evidence.textContent = 'Voice evidence is fresh/readable and edge status is readable.';
    }

    detail.innerHTML = `<b>Hosted voice endpoint:</b> ${esc(state.hostedVoice.detail)}<br><b>Repository voice mirror:</b> ${esc(state.staticVoice.detail)}<br><b>Edge status:</b> ${esc(state.edge.detail)}<br><br>Voice/action evidence older than six hours remains readable history but is not treated as current operator truth. Stale or unavailable evidence never creates a human task by itself.`;
  }

  async function checkHostedVoice() {
    try {
      const r = await fetch('/aurum/voice-status.json', {cache:'no-store'});
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      state.hostedVoice = voiceState(await r.json(), 'hosted endpoint');
    } catch (e) {
      state.hostedVoice = {ok:false, fresh:false, detail:`unavailable · ${e?.message || 'request failed'}`};
    }
  }

  async function checkStaticVoice() {
    try {
      const r = await fetch(STATIC_VOICE, {cache:'no-store'});
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      state.staticVoice = voiceState(await r.json(), 'public Git mirror');
    } catch (e) {
      state.staticVoice = {ok:false, fresh:false, detail:`unavailable · ${e?.message || 'request failed'}`};
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
    state.hostedVoice = {ok:null, fresh:null, detail:'Checking hosted voice endpoint…'};
    state.staticVoice = {ok:null, fresh:null, detail:'Checking repository voice mirror…'};
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
