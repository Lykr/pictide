// Non-state lifecycle signals (language changes, closing transient overlays).
const listeners = new Map();
export function onSignal(name, listener) {
  if (!listeners.has(name)) listeners.set(name, new Set());
  listeners.get(name).add(listener);
  return () => offSignal(name, listener);
}
export function offSignal(name, listener) { listeners.get(name)?.delete(listener); }
export function emitSignal(name, detail) { for (const listener of listeners.get(name) || []) listener(detail); }
