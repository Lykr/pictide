// Geometry only: callers supply measured component and viewport rectangles.
const right = box => box.x + box.width;
const bottom = box => box.y + box.height;
const clamp = (value, min, max) => Math.max(min, Math.min(value, Math.max(min, max)));
const overlap = (a, b, gap = 8) => a.x < right(b) + gap && right(a) > b.x - gap && a.y < bottom(b) + gap && bottom(a) > b.y - gap;
const distance = (a, b) => Math.hypot(Math.max(a.x - right(b), b.x - right(a), 0), Math.max(a.y - bottom(b), b.y - bottom(a), 0));

/**
 * @typedef {{ x: number, y: number, width: number, height: number }} Rect
 * @param {{ viewport: Rect, card: { width: number, height: number }, targets?: Rect[], controls?: Rect[], bottomInset?: number }} input
 */
export function placeGuide({ viewport, card, targets = [], controls = [], bottomInset = 0 }) {
  const minX = viewport.x + 12, minY = viewport.y + 12;
  const maxX = right(viewport) - card.width - 12;
  const maxY = bottom(viewport) - bottomInset - card.height - 12;
  const fit = (x, y) => ({ x: clamp(x, minX, maxX), y: clamp(y, minY, maxY), ...card });
  const fallback = fit(viewport.x + (viewport.width - card.width) / 2, maxY);
  // Prefer a button over a surrounding form; large regions remain highlighted.
  const anchor = [...targets].sort((a, b) => a.width * a.height - b.width * b.height)[0];
  if (!anchor) return { ...fallback, arrow: null };
  const cx = anchor.x + anchor.width / 2, cy = anchor.y + anchor.height / 2;
  const positions = [
    fit(cx - card.width / 2, bottom(anchor) + 16),
    fit(cx - card.width / 2, anchor.y - card.height - 16),
    fit(right(anchor) + 16, cy - card.height / 2),
    fit(anchor.x - card.width - 16, cy - card.height / 2),
    fallback,
  ];
  const obstacles = [...controls, ...targets.filter(box => box.height < viewport.height * 0.65)];
  for (const box of obstacles) {
    positions.push(fit(cx - card.width / 2, box.y - card.height - 16), fit(cx - card.width / 2, bottom(box) + 16));
  }
  const score = box => obstacles.filter(other => overlap(box, other)).length * 100000
    + Number(overlap(box, anchor)) * 100000 + distance(box, anchor);
  positions.sort((a, b) => score(a) - score(b));
  const chosen = positions[0];
  let arrow;
  if (chosen.y >= bottom(anchor)) arrow = { side: 'top', x: clamp(cx, chosen.x + 20, right(chosen) - 20), y: chosen.y };
  else if (bottom(chosen) <= anchor.y) arrow = { side: 'bottom', x: clamp(cx, chosen.x + 20, right(chosen) - 20), y: bottom(chosen) };
  else if (chosen.x >= right(anchor)) arrow = { side: 'left', x: chosen.x, y: clamp(cy, chosen.y + 20, bottom(chosen) - 20) };
  else if (right(chosen) <= anchor.x) arrow = { side: 'right', x: right(chosen), y: clamp(cy, chosen.y + 20, bottom(chosen) - 20) };
  return { ...chosen, arrow: arrow ?? null };
}
