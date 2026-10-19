// Semantic component references; presentation clients never need business selectors.
const targets = new Map<string, Set<HTMLElement>>();
const listeners = new Set<() => void>();
let revision = 0;
export const targetSnapshot = () => revision;
export const subscribeTargets = (callback: () => void) => { listeners.add(callback); return () => { listeners.delete(callback); }; };
const changed = () => { revision++; for (const callback of listeners) callback(); };
export function uiTarget(name: string) {
  let previous: HTMLElement | null = null;
  return (element: HTMLElement | null) => {
    if (previous === element) return;
    if (previous) targets.get(name)?.delete(previous);
    previous = element;
    if (element) {
      element.dataset.uiTarget = name;
      if (!targets.has(name)) targets.set(name, new Set());
      targets.get(name)!.add(element);
    }
    changed();
  };
}
export function visibleTarget(name: string) {
  return [...(targets.get(name) ?? [])].find(element => {
    if (!element.isConnected || element.closest('[hidden],[inert]') || !element.getClientRects().length) return false;
    const style = getComputedStyle(element);
    return style.visibility !== 'hidden' && style.display !== 'none';
  });
}
export function visibleTargets() {
  return [...targets.keys()].map(visibleTarget).filter((element): element is HTMLElement => Boolean(element));
}
