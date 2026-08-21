/* AURUM_ACTIVITY_CLARITY_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Groups repetitive idempotent proof receipts in Recent Activity without deleting audit evidence.
 * A routine receipt is proof of continued validity, not a new frontier advance or human task.
 */
(() => {
  'use strict';
  if (window.__aurumActivityClarityV1) return;
  window.__aurumActivityClarityV1 = true;

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  const style = document.createElement('style');
  style.textContent = `
    .aurum-routine-proof{border-left:2px solid #6c63ff55;padding-left:9px}
    .aurum-routine-chip{display:inline-flex;margin-top:5px;padding:3px 6px;border:1px solid #353a58;border-radius:999px;background:#201f3c;color:#bcb7ff;font-size:8.5px;font-weight:850;letter-spacing:.04em;text-transform:uppercase}
    .aurum-routine-group{border:1px solid #282e3c;border-radius:11px;background:#0e121a;margin:7px 0 3px;overflow:hidden}
    .aurum-routine-group summary{cursor:pointer;padding:9px 11px;color:#8f9bad;font-size:9.5px;font-weight:760;list-style:none}
    .aurum-routine-group summary::-webkit-details-marker{display:none}
    .aurum-routine-group summary::before{content:'›';display:inline-block;margin-right:7px;color:#8f8aff;transition:transform .15s ease}
    .aurum-routine-group[open] summary::before{transform:rotate(90deg)}
    .aurum-routine-group .row{margin:0 10px;border-bottom-color:#202634}
    .aurum-routine-note{margin-top:8px;padding:9px 10px;border:1px solid #292f3d;border-radius:10px;background:#0d1118;color:#7f899d;font-size:9.5px;line-height:1.45}
    .aurum-routine-note b{color:#b8b3ff}
    .aurum-routine-note a{color:#b8b3ff;text-decoration:none;font-weight:760}
  `;
  document.head.appendChild(style);

  function routineKey(message) {
    const text = String(message || '').replace(/\s+/g, ' ').trim();
    const flash = text.match(/^Record Aurum PC-01 flash receipt state=(ALREADY_COMPLETE|FLASH_OK)\b/i);
    if (flash) return `pc01-flash:${flash[1].toUpperCase()}`;
    const mirror = text.match(/^Record Aurum static dashboard voice mirror state=(WEB_STATIC_MIRROR_OK)\b/i);
    if (mirror) return `voice-mirror:${mirror[1].toUpperCase()}`;
    return '';
  }

  function labelFor(key) {
    if (key.startsWith('pc01-flash:ALREADY_COMPLETE')) return 'PC-01 flash already verified';
    if (key.startsWith('pc01-flash:FLASH_OK')) return 'PC-01 flash verified';
    if (key.startsWith('voice-mirror:')) return 'voice mirror verified';
    return 'routine proof';
  }

  function compact() {
    const root = $('#activity');
    if (!root) return;
    const rows = $$('#activity > .row');
    if (!rows.length) return;

    const groups = new Map();
    for (const row of rows) {
      const message = $('b', row)?.textContent?.trim() || '';
      const key = routineKey(message);
      if (!key) continue;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    }

    let groupedReceipts = 0;
    let groupedKinds = 0;
    for (const [key, items] of groups.entries()) {
      if (items.length < 2) continue;
      groupedKinds += 1;
      groupedReceipts += items.length - 1;
      const newest = items[0];
      newest.classList.add('aurum-routine-proof');
      if (!$('.aurum-routine-chip', newest)) {
        const chip = document.createElement('span');
        chip.className = 'aurum-routine-chip';
        chip.textContent = `${labelFor(key)} ×${items.length}`;
        const body = newest.children[newest.children.length - 1] || newest;
        body.appendChild(chip);
      }

      const details = document.createElement('details');
      details.className = 'aurum-routine-group';
      details.dataset.routineKey = key;
      const summary = document.createElement('summary');
      summary.textContent = `Show ${items.length - 1} earlier routine proof${items.length === 2 ? '' : 's'} — full audit preserved`;
      details.appendChild(summary);
      const holder = document.createElement('div');
      holder.className = 'aurum-routine-history';
      for (const row of items.slice(1)) holder.appendChild(row);
      details.appendChild(holder);
      newest.insertAdjacentElement('afterend', details);
      details.addEventListener('click', event => event.stopPropagation());
    }

    let note = $('.aurum-routine-note', root);
    if (groupedReceipts > 0) {
      if (!note) {
        note = document.createElement('div');
        note.className = 'aurum-routine-note';
        root.appendChild(note);
      }
      note.innerHTML = `<b>${groupedReceipts} repetitive receipt${groupedReceipts === 1 ? '' : 's'} grouped across ${groupedKinds} routine proof type${groupedKinds === 1 ? '' : 's'}.</b> These are idempotent confirmations, not new frontier progress and not work for you. The individual Git commits remain available in the <a href="https://github.com/FormatX66/BoxBrain/commits/main" target="_blank" rel="noopener">full repository history ↗</a>.`;
      const state = $('#repoState');
      if (state && !/routine proof/i.test(state.textContent || '')) {
        state.dataset.aurumBaseText = state.textContent || '';
        state.textContent = `${state.dataset.aurumBaseText} · routine proofs grouped`;
      }
    } else if (note) {
      note.remove();
    }
  }

  let queued = false;
  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      compact();
    });
  }

  function boot() {
    const root = $('#activity');
    if (!root) {
      setTimeout(boot, 250);
      return;
    }
    new MutationObserver(schedule).observe(root, {childList:true, subtree:true, characterData:true});
    schedule();
  }
  boot();
})();
