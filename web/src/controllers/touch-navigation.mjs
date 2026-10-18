/** Single-finger image gestures; vertical feedback is opt-in for installed apps. */
export function bindTouchNavigation(element, { navigate, adjustFeedback = null, verticalEnabled = () => false, enabled = () => true }) {
  let gesture = null;
  const cancel = () => { gesture = null; };
  const start = event => {
    cancel();
    if (!enabled() || event.touches.length !== 1 || event.target?.closest?.('button,a,input,textarea,select,[role="button"],[contenteditable="true"]')) return;
    const touch = event.touches[0];
    gesture = { id: touch.identifier, x: touch.clientX, y: touch.clientY, started: event.timeStamp, axis: null };
  };
  const move = event => {
    if (!gesture) return;
    if (event.touches.length !== 1 || !enabled()) return cancel();
    const touch = event.touches[0];
    if (touch.identifier !== gesture.id) return cancel();
    const dx = Math.abs(touch.clientX - gesture.x), dy = Math.abs(touch.clientY - gesture.y);
    // Lock to the first clear direction; browser vertical scrolling remains untouched.
    if (!gesture.axis && Math.max(dx, dy) >= 12) {
      if (dx >= dy * 1.5) gesture.axis = 'horizontal';
      else if (dy >= dx * 1.5 && adjustFeedback && verticalEnabled()) gesture.axis = 'vertical';
      else return cancel();
    }
    if (gesture.axis && event.cancelable) event.preventDefault();
  };
  const end = event => {
    const current = gesture;
    cancel();
    if (!current || event.touches.length || !enabled() || event.timeStamp - current.started > 1000) return;
    const touch = Array.from(event.changedTouches).find(item => item.identifier === current.id);
    if (!touch) return;
    const dx = touch.clientX - current.x, dy = touch.clientY - current.y;
    const threshold = Math.max(44, Math.min(80, element.clientWidth * 0.12));
    if (current.axis !== 'vertical' && Math.abs(dx) >= threshold && Math.abs(dx) >= Math.abs(dy) * 1.5) {
      navigate(dx < 0 ? 'newer' : 'older');
    } else if (current.axis !== 'horizontal' && adjustFeedback && verticalEnabled()
        && Math.abs(dy) >= threshold && Math.abs(dy) >= Math.abs(dx) * 1.5) {
      adjustFeedback(dy < 0 ? 1 : -1);
    }
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
