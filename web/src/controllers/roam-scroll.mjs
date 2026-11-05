/** Pixel motion only. The application retains navigation, feedback and generation ownership. */
export const scrollSpeeds = { slow: 24, normal: 48, fast: 80 };
const ease = progress => progress < .5 ? 4 * progress ** 3 : 1 - (-2 * progress + 2) ** 3 / 2;

export function createRoamScroll() {
  let items = [], viewport = 0, offset = 0, initialized = false;
  let motion = null, pending = null;
  const centerOffset = item => viewport / 2 - item.center;
  const itemAtCenter = () => {
    const center = viewport / 2 - offset;
    return items.reduce((best, item) => {
      const distance = Math.max(item.left - center, center - item.left - item.width, 0);
      return !best || distance < best.distance ? { item, distance } : best;
    }, null)?.item;
  };
  const find = id => items.find(item => item.id === id);
  function seek(id) {
    const item = find(id);
    if (!item?.ready) { pending = { id }; return; }
    const to = centerOffset(item);
    motion = { id, from: offset, to, elapsed: 0, duration: Math.max(.36, Math.min(.72, Math.abs(to - offset) / 900)) };
    pending = null;
  }
  function snapshot() {
    const focus = itemAtCenter();
    // Persist the oldest still-visible picture, so cleanup cannot remove a neighbor on screen.
    const oldest = items.find(item => item.left + item.width + offset > 0 && item.left + offset < viewport);
    return { offset, focus: focus?.id ?? null, oldest: oldest?.id ?? focus?.id ?? null,
      moving: !!motion, pending: !!pending, target: motion?.id ?? pending?.id ?? null };
  }
  return {
    snapshot,
    layout(next, width, initialId, gap = 12) {
      const pivot = itemAtCenter(), previous = pivot ? offset + pivot.left : 0;
      const previousViewport = viewport;
      let left = 0;
      items = next.map(item => {
        const result = { ...item, left, center: left + item.width / 2 };
        left += item.width + gap;
        return result;
      });
      viewport = width;
      if (!items.length || !viewport) return snapshot();
      if (!initialized || !pivot || !find(pivot.id)) {
        const initial = find(initialId) || items[0];
        offset = centerOffset(initial); initialized = true;
      } else offset = previous - find(pivot.id).left + (viewport - previousViewport) / 2;
      if (motion) {
        const target = find(motion.id);
        if (target) {
          // A model refresh must not restart easing at zero velocity halfway through a seek.
          const progress = ease(Math.min(1, motion.elapsed / motion.duration));
          motion.to = centerOffset(target);
          motion.from = progress < 1 ? (offset - motion.to * progress) / (1 - progress) : offset;
        }
        else motion = null;
      }
      if (pending?.id && find(pending.id)?.ready) seek(pending.id);
      else if (pending?.direction) {
        const base = items.findIndex(item => item.id === pending.base);
        const item = base < 0 ? null : items[base + (pending.direction === 'newer' ? 1 : -1)];
        if (item) seek(item.id);
      }
      return snapshot();
    },
    navigate(direction) {
      const base = motion?.id ?? pending?.id ?? itemAtCenter()?.id;
      const index = items.findIndex(item => item.id === base);
      const item = items[index + (direction === 'newer' ? 1 : -1)];
      if (index < 0 || !item) {
        pending = { direction, base }; return false;
      }
      seek(item.id); return true;
    },
    select(id) { motion = null; pending = null; seek(id); },
    freeze() { motion = null; pending = null; return snapshot(); },
    tick(seconds, playing, speed = 'normal') {
      let waiting = false;
      if (motion) {
        motion.elapsed += Math.max(0, seconds);
        const progress = Math.min(1, motion.elapsed / motion.duration);
        const eased = ease(progress);
        offset = motion.from + (motion.to - motion.from) * eased;
        if (progress === 1) motion = null;
      } else if (playing && !pending && initialized) {
        const index = items.findIndex(item => item.id === itemAtCenter()?.id);
        if (index >= 0 && items[index].ready) {
          let lastReady = index;
          while (items[lastReady + 1]?.ready) lastReady++;
          const limit = centerOffset(items[lastReady]);
          offset = Math.min(offset, Math.max(limit, offset - Math.max(0, seconds) * (scrollSpeeds[speed] ?? scrollSpeeds.normal)));
          waiting = offset <= limit;
        }
      }
      return { ...snapshot(), waiting };
    },
  };
}
