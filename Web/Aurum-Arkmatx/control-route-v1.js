/* AURUM_CONTROL_ROUTE_V1_1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Surfaces the read-only GitHub -> main PC -> BoxBrain Pi4 -> Hopper control path.
 * Route failures are Aurum/system work; this component never invents a human task.
 * GitHub directory entries are resolved through raw download URLs before state parsing.
 */
(() => {
  'use strict';
  if (window.__aurumControlRouteV11) return;
  window.__aurumControlRouteV11 = true;

  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const API = 'https://api.github.com/repos/FormatX66/BoxBrain/contents';
  const REQUESTS = `${API}/Projects/AurumBridge/requests/boxbrain-hopper-route?ref=main`;
  const RESULTS = `${API}/Projects/AurumBridge/results?ref=main`;
  const REFRESH = 60 * 1000;

  const style = document.createElement('style');
  style.textContent = `
    .control-route-card .cr-detail{display:none;margin-top:10px;padding-top:10px;border-top:1px solid #252b39;font-size:10px;line-height:1.5;color:#8f9bad}
    .control-route-card[aria-expanded="true"] .cr-detail{display:block}
    .control-route-card .cr-detail b{color:#c9c6ff}.control-route-card .cr-hint{margin-top:8px;font-size:8.5px;color:#747f92;font-weight:750}
    .control-route-card .cr-path{display:flex;gap:5px;flex-wrap:wrap;margin:8px 0}.control-route-card .cr-hop{border:1px solid #343164;background:#17162a;color:#bcb7ff;border-radius:999px;padding:4px 7px;font-size:8.5px;font-weight:750}
  `;
  document.head.appendChild(style);

  let routeState = {phase:'checking', request:null, result:null, detail:'Checking control-route evidence…', checkedAt:0};

  function publish() {
    window.__aurumControlRouteState = {...routeState};
    window.dispatchEvent(new CustomEvent('aurum-control-route-state', {detail:{...routeState}}));
  }

  async function json(url) {
    const r = await fetch(url, {cache:'no-store', headers:{Accept:'application/vnd.github+json'}});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }

  async function rawJson(url) {
    if (!url) throw new Error('GitHub raw download URL missing');
    const r = await fetch(url, {cache:'no-store'});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }

  function requestEpoch(request) {
    const id = String(request?.id || '');
    const m = id.match(/(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})Z/);
    return m ? Date.UTC(+m[1], +m[2]-1, +m[3], +m[4], +m[5]) : 0;
  }

  async function latestRequest() {
    const list = await json(REQUESTS);
    const files = Array.isArray(list) ? list.filter(x => x.type === 'file' && /^route-test-.*\.json$/i.test(x.name)).sort((a,b)=>b.name.localeCompare(a.name)) : [];
    if (!files.length) return null;
    return rawJson(files[0].download_url);
  }

  async function latestResult() {
    const list = await json(RESULTS);
    const files = Array.isArray(list) ? list.filter(x => x.type === 'file' && /^boxbrain-hopper-route-\d+\.json$/i.test(x.name)).sort((a,b)=>b.name.localeCompare(a.name)) : [];
    if (!files.length) return null;
    const payload = await rawJson(files[0].download_url);
    return {name:files[0].name, payload};
  }

  function ensureCard() {
    const systems = $('#systems');
    if (!systems) return null;
    let card = $('[data-id="route"]', systems);
    if (card) return card;
    card = document.createElement('article');
    card.className = 'system-card control-route-card';
    card.dataset.id = 'route';
    card.tabIndex = 0;
    card.setAttribute('role','button');
    card.setAttribute('aria-expanded','false');
    card.innerHTML = `
      <div class="card-head"><div class="card-icon">⇢</div><span class="pill running">Running</span></div>
      <h3>BoxBrain → Hopper Route</h3>
      <p>Read-only control and evidence path from GitHub through the main-PC runner and BBPI4 to Hopper.</p>
      <div class="evidence">Checking control-route evidence…</div>
      <div class="cr-hint">Tap to expand route proof →</div>
      <div class="cr-detail"></div>`;
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
    const pill = $('.pill', card), evidence = $('.evidence', card), detail = $('.cr-detail', card);
    if (routeState.phase === 'checking') {
      pill.className='pill running'; pill.textContent='Running'; evidence.textContent='Checking latest route request and proof…';
    } else if (routeState.phase === 'proven') {
      pill.className='pill success'; pill.textContent='Verified'; evidence.textContent='GitHub → main PC → BBPI4 → Hopper read-only route proven.';
    } else if (routeState.phase === 'pending') {
      pill.className='pill waiting'; pill.textContent='Waiting'; evidence.textContent='Read-only route proof requested; result not yet recorded · Aurum/system work, not your action.';
    } else if (routeState.phase === 'failed') {
      pill.className='pill failed'; pill.textContent='Attention'; evidence.textContent=`Route proof returned ${routeState.result?.state || 'an unresolved state'} · Aurum/system diagnosis, not your action.`;
    } else {
      pill.className='pill unknown'; pill.textContent='Unknown'; evidence.textContent='Control-route evidence is currently unreadable · no human task inferred.';
    }
    const r = routeState.result || {}, h = r.hopper || {}, request = routeState.request || {};
    detail.innerHTML = `<div class="cr-path"><span class="cr-hop">GitHub</span><span class="cr-hop">main PC runner</span><span class="cr-hop">SSH</span><span class="cr-hop">BBPI4</span><span class="cr-hop">LAN</span><span class="cr-hop">Hopper</span></div><b>Latest request:</b> ${esc(request.id || 'none recorded')}<br><b>Mode:</b> ${esc(request.mode || 'read-only')}<br><b>Latest result:</b> ${esc(r.state || 'not recorded')}<br><b>Observed:</b> ${esc(r.observed_at || 'not yet')}<br><b>Hopper checks:</b> resolution ${esc(h.resolved ?? 'unknown')} · ping ${esc(h.ping ?? 'unknown')} · self-debug ${esc(h.self_debug_8768 ?? 'unknown')} · echo ${esc(h.echo_proof_8767 ?? 'unknown')} · GUI ${esc(h.gui_8765 ?? 'unknown')}<br><br><b>Ownership:</b> this is a read-only system proof. A missing or failed route remains Aurum/system work unless a separate verified physical gate explicitly names a human step.`;
  }

  async function refresh() {
    routeState = {phase:'checking', request:routeState.request, result:routeState.result, detail:'Checking control-route evidence…', checkedAt:Date.now()};
    render(); publish();
    try {
      const [request, resultWrap] = await Promise.all([latestRequest(), latestResult()]);
      const result = resultWrap?.payload || null;
      const reqAt = requestEpoch(request);
      const resAt = result?.observed_at ? Date.parse(result.observed_at) : 0;
      let phase = 'pending';
      if (!request && !result) phase = 'unknown';
      else if (request && (!result || (reqAt && (!resAt || resAt < reqAt)))) phase = 'pending';
      else if (result?.state === 'BOXBRAIN_TO_HOPPER_ROUTE_PROVEN') phase = 'proven';
      else if (result) phase = 'failed';
      routeState = {phase, request, result, resultName:resultWrap?.name || null, checkedAt:Date.now()};
    } catch (e) {
      routeState = {phase:'unknown', request:null, result:null, detail:e?.message || 'request failed', checkedAt:Date.now()};
    }
    render(); publish();
  }

  function boot() {
    if (!$('#systems')) { setTimeout(boot, 250); return; }
    refresh();
    setInterval(refresh, REFRESH);
  }
  boot();
})();
