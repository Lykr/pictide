/** A single idle timeout; focused/hovered controls stay available. */
export function createAutoHideControls({ visible, held, delay = 2000, schedule = setTimeout, cancel = clearTimeout }) {
  let active = false, timer;
  const clear = () => { if (timer !== undefined) cancel(timer); timer = undefined; };
  const wake = () => {
    if (!active) return;
    clear(); visible(true);
    if (!held()) timer = schedule(() => { timer = undefined; if (active && !held()) visible(false); }, delay);
  };
  return {
    start() { active = true; wake(); },
    wake,
    stop() { active = false; clear(); visible(true); },
  };
}

/** Reuse the mounted image and buttons in native fullscreen, with a viewport fallback. */
export function createImmersiveViewer({ card, toolbar, entry, focusReturn = entry, exit = /** @type {HTMLElement | null} */ (null), eligible, changed = () => {}, document: doc = document, window: win = window }) {
  let active = false, mode = null, revision = 0, hovered = false, keyboard = false;
  let restoreInert = [];
  const toolbars = [...new Set([toolbar, exit?.parentElement].filter(Boolean))];
  const inControls = node => toolbars.some(bar => bar.contains(node));
  const controls = createAutoHideControls({
    held: () => hovered || (keyboard && inControls(doc.activeElement)),
    visible: show => {
      if (!show && inControls(doc.activeElement)) card.focus({ preventScroll: true });
      card.classList.toggle('immersive-controls-hidden', !show);
      for (const bar of toolbars) {
        bar.inert = !show;
        bar.setAttribute('aria-hidden', String(!show));
      }
    },
  });
  const pointerMove = () => controls.wake();
  const pointerDown = event => {
    keyboard = false;
    if (event.pointerType === 'touch') hovered = false;
    if (!inControls(event.target)) card.focus({ preventScroll: true });
    controls.wake();
  };
  const enterToolbar = event => { if (event.pointerType !== 'touch') { hovered = true; controls.wake(); } };
  const leaveToolbar = () => { hovered = false; controls.wake(); };
  const focus = () => controls.wake();
  const key = event => {
    keyboard = true; controls.wake();
    if (event.key === 'Escape') { event.preventDefault(); leave(); }
  };
  const fullscreen = () => {
    if (doc.fullscreenElement === card && active) mode = 'native';
    else if (active && mode === 'native') leave(false);
  };
  const suspend = () => leave();
  const restoreFocus = () => {
    if (focusReturn.isConnected && !focusReturn.hidden && !focusReturn.disabled && !focusReturn.closest('[hidden],[inert]')) focusReturn.focus({ preventScroll: true });
  };
  const leaveNative = () => {
    try { return Promise.resolve(doc.exitFullscreen()).catch(() => {}); }
    catch { return Promise.resolve(); }
  };
  function isolate() {
    restoreInert = [];
    for (let node = card; node?.parentElement && node !== doc.body; node = node.parentElement) {
      for (const sibling of node.parentElement.children) {
        if (sibling === node) continue;
        restoreInert.push([sibling, sibling.inert]); sibling.inert = true;
      }
    }
  }
  function leave(requestExit = true) {
    if (!active) return;
    active = false; mode = null; revision++;
    controls.stop(); hovered = false; keyboard = false;
    card.classList.remove('immersive'); doc.body.classList.remove('pictide-immersive');
    if (exit) exit.hidden = true;
    entry.setAttribute('aria-pressed', 'false');
    for (const [node, previous] of restoreInert) node.inert = previous;
    restoreInert = [];
    card.removeEventListener('pointermove', pointerMove); card.removeEventListener('pointerdown', pointerDown);
    for (const bar of toolbars) { bar.removeEventListener('pointerenter', enterToolbar); bar.removeEventListener('pointerleave', leaveToolbar); }
    card.removeEventListener('focusin', focus); card.removeEventListener('focusout', focus);
    doc.removeEventListener('keydown', key, true); doc.removeEventListener('fullscreenchange', fullscreen);
    win.removeEventListener('pagehide', suspend);
    changed(false);
    if (requestExit && doc.fullscreenElement === card) return leaveNative().then(restoreFocus);
    else restoreFocus();
  }
  function enter() {
    if (active || !eligible()) return;
    active = true; mode = 'browser'; const token = ++revision;
    doc.dispatchEvent(new Event('pictide:close-image-info'));
    card.classList.add('immersive'); doc.body.classList.add('pictide-immersive');
    if (exit) exit.hidden = false;
    entry.setAttribute('aria-pressed', 'true');
    isolate();
    card.addEventListener('pointermove', pointerMove); card.addEventListener('pointerdown', pointerDown);
    for (const bar of toolbars) { bar.addEventListener('pointerenter', enterToolbar); bar.addEventListener('pointerleave', leaveToolbar); }
    card.addEventListener('focusin', focus); card.addEventListener('focusout', focus);
    doc.addEventListener('keydown', key, true); doc.addEventListener('fullscreenchange', fullscreen);
    win.addEventListener('pagehide', suspend);
    changed(true); controls.start(); card.focus({ preventScroll: true });
    // Keep this call synchronous with the genuine click for browser user activation.
    try {
      if (card.requestFullscreen) Promise.resolve(card.requestFullscreen()).then(() => {
        if (!active || token !== revision) {
          if (doc.fullscreenElement === card) leaveNative().then(restoreFocus);
        } else if (doc.fullscreenElement === card) mode = 'native';
      }).catch(() => {}); // A denied/unsupported native request keeps the viewport fallback.
    } catch {} // Some embedded browsers throw instead of returning a rejected promise.
  }
  entry.addEventListener('click', enter); exit?.addEventListener('click', () => leave());
  return { get active() { return active; }, leave, wake: controls.wake };
}
