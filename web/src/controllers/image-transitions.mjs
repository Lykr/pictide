// One shared image-only effect for DOM roam and React viewers.
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
let enabled = true;
const active = new Map();
export const imageTransitionsEnabled = () => enabled;
export function cancelImageTransition(image) {
  const animation = active.get(image);
  if (animation) { active.delete(image); animation.cancel(); }
}
function cancelAll() {
  for (const image of active.keys()) cancelImageTransition(image);
}
export function applyImageTransitions(value) {
  enabled = value !== false;
  if (!enabled) cancelAll();
  document.dispatchEvent(new Event('pictide:image-transitions-changed'));
}
reducedMotion.addEventListener('change', () => {
  if (reducedMotion.matches) cancelAll();
});
export function playImageTransition(image) {
  cancelImageTransition(image);
  if (!enabled || reducedMotion.matches) return;
  const animation = image.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 180, easing: 'ease-out' });
  active.set(image, animation);
  const release = () => { if (active.get(image) === animation) active.delete(image); };
  animation.addEventListener('finish', release, { once: true });
  animation.addEventListener('cancel', release, { once: true });
}
