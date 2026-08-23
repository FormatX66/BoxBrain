/* AURUM_EVIDENCE_HEALTH_V1_3_CANONICAL
 * AURUM_EVIDENCE_HEALTH_V1_2_CANONICAL compatibility marker.
 * AURUM_EVIDENCE_HEALTH_V1_1_CANONICAL compatibility marker.
 * Canonical website owner: FormatX66/ClusterSites.
 * Separates transport/readability from freshness and hosted-mirror deployment configuration.
 * Voice/action evidence uses a six-hour operator-action window.
 * A missing BoxBrain hosted-mirror configuration is Aurum/system work and never invents a human task.
 */
(() => {
  'use strict';
  if (window.__aurumEvidenceHealthV13) return;
  window.__aurumEvidenceHealthV13 = true;

  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const REPO = 'FormatX66/BoxBrain';
  const STATIC_VOICE = `https://raw.githubusercontent.com/${REPO}/main/Web/Aurum-Arkmatx/voice-status.json`;
  const RESULTS = `https://api.github.com/repos/${REPO}/contents/Projects/AurumBridge/results?ref=main`;
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
    hostedDeploy: {ok:null, configured:null, detail:'Checking BoxBrain hosted-mirror deployment lane…'},
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
      <p>Health, redundancy, freshness, and publication configuration of the read-only sources that feed capability, node, and action truth into this command center.</p>
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

  async function json(url) {
    const r = await fetch(url, {cache:'no-store', headers:{Accept:'application/vnd.github+json'}});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }

  function deploymentReceiptRank(name) {
    const m = String(name || '').match(/^web(-static)?-mirror-(\d+)(?:-attempt-(\d+))?\.json$/i);
    if (!m) return null;
    return {run:Number(m[2]), attempt:Number(m[3] || 0), static:Boolean(m[1])};
  }

  function render() {
    const card = ensureCard();
    if (!card) return;
    const checks = [state.hostedVoice, state.staticVoice, state.hostedDeploy, state.edge];
    const pending = checks.some(x => x.ok === null);
    const voiceReadable = state.hostedVoice.ok === true || state.staticVoice.ok === true;
    const voiceFresh = (state.hostedVoice.ok === true && state.hostedVoice.fresh === true) || (state.staticVoice.ok === true && state.staticVoice.fresh === true);
    const hostedLaneUnconfigured = state.hostedDeploy.ok === true && state.hostedDeploy.configured === false;
    const hardFailure = state.edge.ok === false || (!pending && !voiceReadable);
    const degraded = !pending && !hardFailure && (checks.some(x => x.ok === false) || !voiceFresh || hostedLaneUnconfigured);
    const pill = $('.pill', card);
    const evidence = $('.evidence', card);
    const detail = $('.eh-detail', card);

    if (pending) {
      pill.className = 'pill running';
      pill.textContent = 'Running';
      evidence.textContent = 'Checking evidence readability, freshness, and publication configuration…';
    } else if (hardFailure) {
      pill.className = 'pill failed';
      pill.textContent = 'Attention';
      evidence.textContent = 'Required evidence function unavailable · Aurum/system work, not your action';
    } else if (degraded) {
      pill.className = 'pill waiting';
      pill.textContent = 'Waiting';
      if (!voiceFresh && voiceReadable) {
        evidence.textContent = 'Voice evidence is readable but stale · current action/capability truth may lag · Aurum/system work, not your action';
      } else if (hostedLaneUnconfigured && state.staticVoice.ok === true) {
        evidence.textContent = 'Evidence redundancy degraded · BoxBrain hosted mirror lane is not configured · repository mirror remains readable · Aurum/system work, not your action';
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
      evidence.textContent = 'Voice evidence is fresh/readable, publication lane is configured, and edge status is readable.';
    }

    detail.innerHTML =
      `<b>Hosted voice endpoint:</b> ${esc(state.hostedVoice.detail)}` +
      `<br><b>Repository voice mirror:</b> ${esc(state.staticVoice.detail)}` +
      `<br><b>BoxBrain hosted mirror lane:</b> ${esc(state.hostedDeploy.detail)}` +
      `<br><b>Edge status:</b> ${esc(state.edge.detail)}` +
      `<br><br>Voice/action evidence older than six hours remains readable history but is not treated as current operator truth. ` +
      `A missing hosted-mirror configuration is a system/deployment condition, not a request for credentials from you. ` +
      `Stale or unavailable evidence never creates a human task by itself.`;
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

  async function checkHostedDeploy() {
    try {
      const list = await json(RESULTS);
      const receipts = Array.isArray(list)
        ? list.map(meta => ({meta, rank: meta?.type === 'file' ? deploymentReceiptRank(meta.name) : null}))
            .filter(x => x.rank)
            .sort((a,b) => (b.rank.run - a.rank.run) || (b.rank.attempt - a.rank.attempt))
        : [];
      if (!receipts.length) throw new Error('no deployment receipt');
      const latest = receipts[0];
      const payload = await json(latest.meta.download_url);
      if (payload?.schema === 'aurum-web-static-mirror-receipt-v1' && payload?.hosted_deployment?.configured === false) {
        const missing = Array.isArray(payload.hosted_deployment.missing) ? payload.hosted_deployment.missing.filter(Boolean) : [];
        state.hostedDeploy = {
          ok:true,
          configured:false,
          receipt:latest.meta.name,
          observedAt:payload.observed_at || null,
          missing,
          detail:`not configured in BoxBrain hosted-mirror workflow · ${missing.length ? `${missing.length} required settings absent` : 'required settings absent'} · receipt ${latest.meta.name}`,
        };
        return;
      }
      if (payload?.schema === 'aurum-web-mirror-receipt-v1' && payload?.state === 'WEB_MIRROR_OK') {
        state.hostedDeploy = {
          ok:true,
          configured:true,
          receipt:latest.meta.name,
          observedAt:payload.observed_at || null,
          missing:[],
          detail:`configured and last verified by ${latest.meta.name}`,
        };
        return;
      }
      throw new Error('unrecognized deployment receipt');
    } catch (e) {
      state.hostedDeploy = {ok:false, configured:null, detail:`configuration evidence unavailable · ${e?.message || 'request failed'}`};
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
    state.hostedDeploy = {ok:null, configured:null, detail:'Checking BoxBrain hosted-mirror deployment lane…'};
    state.edge = {ok:null, detail:'Checking edge status…'};
    render();
    await Promise.all([checkHostedVoice(), checkStaticVoice(), checkHostedDeploy(), checkEdge()]);
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
