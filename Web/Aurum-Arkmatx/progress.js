/* Aurum semantic progression overlay.
 * "Advancing" means meaningful frontier movement, not merely a runner being busy this second.
 */
(() => {
  'use strict';
  if (window.__aurumProgressOverlay) return;
  window.__aurumProgressOverlay = true;

  const advancingStatuses = new Set(['Verified', 'Running', 'Experiment']);
  const forkablePhysical = new Set(['hopper', 'pi4']);

  function apply() {
    const running = document.querySelector('#mRunning');
    if (!running) return;
    const metric = running.closest('.metric');
    const label = metric?.querySelector('span');
    if (label) label.textContent = 'frontiers advancing';

    let advancing = 0;
    let held = 0;
    document.querySelectorAll('#systems .card').forEach(card => {
      const id = card.dataset.id || '';
      const pill = card.querySelector('.pill');
      const status = (pill?.textContent || '').trim();
      let note = card.querySelector('.progress-state');
      if (!note) {
        note = document.createElement('div');
        note.className = 'progress-state';
        note.style.cssText = 'margin-top:7px;font-size:10px;font-weight:750;color:#8fa0b2';
        card.appendChild(note);
      }
      if (advancingStatuses.has(status)) {
        advancing += 1;
        note.textContent = status === 'Running' ? '↗ Progress: executing now' : '↗ Progress: next frontier remains active';
        note.style.color = '#8ce7b2';
      } else if (status === 'Waiting' && forkablePhysical.has(id)) {
        advancing += 1;
        held += 1;
        note.textContent = '↗ Progress: physical proof held; independent fork continues';
        note.style.color = '#f0c76a';
      } else if (status === 'Attention') {
        note.textContent = '■ Progress: stalled — inspect details';
        note.style.color = '#ff9da6';
      } else {
        note.textContent = '○ Progress: frontier evidence needed';
        note.style.color = '#8fa0b2';
      }
    });
    running.textContent = String(advancing);
    running.title = held ? `${held} physical frontier${held === 1 ? '' : 's'} held while independent forks continue` : 'Semantic frontier advancement';
  }

  const observer = new MutationObserver(() => window.requestAnimationFrame(apply));
  const systems = document.querySelector('#systems');
  if (systems) observer.observe(systems, {childList:true, subtree:true, characterData:true});
  apply();
  window.setInterval(apply, 15000);
})();
