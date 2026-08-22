/* AURUM_PROGRESS_TRUTH_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Stable idempotent confirmations remain healthy proof but are not counted as frontier movement.
 * This layer corrects semantic progress without turning stable proof into Needs Work or Your Actions.
 */
(() => {
  'use strict';
  if (window.__aurumProgressTruthV1) return;
  window.__aurumProgressTruthV1 = true;

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const PHYSICAL_FORK = new Set(['hopper', 'pi4']);
  const ADVANCING = new Set(['Verified', 'Running', 'Experiment']);
  const STABLE_PROOF = /\bALREADY_COMPLETE\b|idempotent confirmation|routine proof|already complete/i;

  const style = document.createElement('style');
  style.textContent = '.cc32-progress.stable{color:#8ea8ff}.cc32-row .stable-proof{color:#8ea8ff;font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.06em}';
  document.head.appendChild(style);

  function cards() { return $$('#systems .system-card,#systems .card'); }
  function info(card) {
    return {
      id: card.dataset.id || (card.dataset.circleciCard ? 'circleci' : ''),
      name: $('h3', card)?.textContent?.trim() || 'System',
      status: $('.pill', card)?.textContent?.trim() || 'Unknown',
      evidence: $('.evidence', card)?.textContent?.trim() || 'No current evidence.',
      card,
    };
  }
  function all() { return cards().map(info); }
  function stable(x) { return x.status === 'Verified' && STABLE_PROOF.test(x.evidence); }
  function advancing(x) {
    if (stable(x)) return false;
    return ADVANCING.has(x.status) || (x.status === 'Waiting' && PHYSICAL_FORK.has(x.id));
  }

  function apply() {
    const items = all();
    let count = 0;
    let stableCount = 0;
    for (const x of items) {
      const isStable = stable(x);
      x.card.dataset.aurumProgressKind = isStable ? 'stable-proof' : '';
      if (isStable) {
        stableCount++;
        let note = $('.cc32-progress', x.card);
        if (!note) {
          note = document.createElement('div');
          note.className = 'cc32-progress';
          x.card.appendChild(note);
        }
        note.className = 'cc32-progress stable';
        note.textContent = '✓ verified stable · no new frontier movement';
      } else if (advancing(x)) {
        count++;
      }
    }
    const metric = $('#cc32Progress');
    if (metric && metric.textContent !== String(count)) metric.textContent = String(count);
    const floor = $('#cc32Floor');
    if (floor && stableCount > 0) {
      const base = floor.textContent.replace(/\s*•\s*\d+ stable proof checkpoint(?:s)? excluded from movement\.?$/i, '');
      floor.textContent = `${base} • ${stableCount} stable proof checkpoint${stableCount === 1 ? '' : 's'} excluded from movement.`;
    }
  }

  function renderProgressDrawer() {
    const drawer = $('.cc32-drawer');
    if (!drawer) return;
    const items = all().filter(advancing);
    const rows = items.map(x => `<div class="cc32-row"><b>${esc(x.name)}</b><span class="cc32-owner none">No action</span><p><b style="color:#d8dced">${esc(x.status)}</b><br>${esc(x.evidence)}</p></div>`).join('');
    drawer.innerHTML = `<div class="cc32-head"><div><p class="eyebrow">COMMAND DETAIL</p><h2>Frontiers Advancing</h2><p>Executing jobs, experiments, verified frontiers with live movement, and physical holds whose independent fork continues. Stable idempotent confirmations stay Healthy / Verified but are excluded from movement.</p></div><button class="cc32-close" type="button">×</button></div>${rows ? `<div class="cc32-list">${rows}</div>` : '<div class="cc32-empty">No frontier currently has evidence of movement. Stable proof remains visible under Healthy / Verified.</div>'}`;
    drawer.classList.add('show');
    const close = $('.cc32-close', drawer);
    if (close) close.onclick = () => {
      drawer.classList.remove('show');
      $$('.cc32-metric').forEach(x => x.setAttribute('aria-expanded', 'false'));
    };
  }

  function wireProgressMetric() {
    const metric = $('.cc32-metric[data-k="progress"]');
    if (!metric || metric.dataset.progressTruthV1) return;
    metric.dataset.progressTruthV1 = '1';
    metric.addEventListener('click', () => setTimeout(renderProgressDrawer, 0));
  }

  let pending = false;
  function schedule() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      wireProgressMetric();
      apply();
    });
  }

  const root = $('#systems') || document.body;
  new MutationObserver(schedule).observe(root, {subtree:true, childList:true, characterData:true, attributes:true, attributeFilter:['class']});
  schedule();
  setTimeout(schedule, 1000);
  setInterval(schedule, 3200);
})();
