/** Generated results are newest first; never skip an unloaded older neighbour. */
export function generatedNeighbour(items, activeId, direction) {
  const index = items.findIndex(item => item.id === activeId);
  if (index < 0) return null;
  return items[index + (direction === 'older' ? 1 : -1)]?.id ?? null;
}

export function generatedReplacement(items, previousIndex) {
  return items[Math.max(0, Math.min(previousIndex, items.length - 1))]?.id ?? null;
}

/** Native controls and auxiliary dialogs own their keyboard input. */
export function generatedShortcut(key, { repeat = false, busy = false, blocked = false } = {}) {
  if (busy || blocked) return null;
  if (key === 'ArrowLeft') return 'older';
  if (key === 'ArrowRight') return 'newer';
  if (key === 'ArrowUp') return 'like';
  if (repeat) return null;
  if (key === ' ' || key === 'Spacebar') return 'privacy';
  return null;
}
