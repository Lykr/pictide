/** Bind horizontal single-finger navigation to an image stage, preserving scroll and pinch zoom. */
export function bindTouchNavigation(element, { navigate, enabled = () => true }) {
  let gesture = null;
  const cancel = () => { gesture = null; };
  const start = event => {
    cancel();
    if (!enabled() || event.touches.length !== 1 || event.target?.closest?.('button,a,input,textarea,select,[role="button"],[contenteditable="true"]')) return;
    const touch = event.touches[0];
    gesture = { id: touch.identifier, x: touch.clientX, y: touch.clientY, started: event.timeStamp, horizontal: false };
  };
  const move = event => {
    if (!gesture) return;
    if (event.touches.length !== 1 || !enabled()) return cancel();
    const touch = event.touches[0];
    if (touch.identifier !== gesture.id) return cancel();
    const dx = Math.abs(touch.clientX - gesture.x), dy = Math.abs(touch.clientY - gesture.y);
    // Once a gesture starts vertically it remains scrolling, even if it later turns sideways.
    if (!gesture.horizontal && Math.max(dx, dy) >= 12) {
      if (dy >= dx) return cancel();
      gesture.horizontal = dx >= dy * 1.5;
    }
    if (gesture.horizontal && event.cancelable) event.preventDefault();
  };
  const end = event => {
    const current = gesture;
    cancel();
    if (!current || event.touches.length || !enabled() || event.timeStamp - current.started > 1000) return;
    const touch = Array.from(event.changedTouches).find(item => item.identifier === current.id);
    if (!touch) return;
    const dx = touch.clientX - current.x, dy = touch.clientY - current.y;
    const threshold = Math.max(44, Math.min(80, element.clientWidth * 0.12));
    if (Math.abs(dx) >= threshold && Math.abs(dx) >= Math.abs(dy) * 1.5) navigate(dx < 0 ? 'newer' : 'older');
  };
  element.addEventListener('touchstart', start, { passive: true });
  element.addEventListener('touchmove', move, { passive: false });
  element.addEventListener('touchend', end, { passive: true });
  element.addEventListener('touchcancel', cancel, { passive: true });
  return () => {
    cancel();
    element.removeEventListener('touchstart', start);
    element.removeEventListener('touchmove', move);
    element.removeEventListener('touchend', end);
    element.removeEventListener('touchcancel', cancel);
  };
}
