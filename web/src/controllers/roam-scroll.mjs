/** Pixel motion only. The application retains navigation, feedback and generation ownership. */
export const scrollSpeeds = { slow: 24, normal: 48, fast: 80 };
const blend = progress => progress * progress * (3 - 2 * progress);
const tangent = (motion, progress) => motion.duration * (motion.velocity * progress * (1 - progress) ** 2
  + motion.endVelocity * progress * progress * (progress - 1));
const speedAt = (motion, progress) => (motion.to - motion.from) * 6 * progress * (1 - progress) / motion.duration
  + motion.velocity * (1 - 4 * progress + 3 * progress * progress)
  + motion.endVelocity * (3 * progress * progress - 2 * progress);

export function createRoamScroll() {
  let items = [], viewport = 0, offset = 0, initialized = false;
  let velocity = 0, drift = 0, animationRevision = 0;
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
  const endVelocity = id => {
    const index = items.findIndex(item => item.id === id);
    return items[index + 1]?.ready ? drift : 0;
  };
  function seek(id) {
    const item = find(id);
    if (!item?.ready) { pending = { id }; return; }
    const to = centerOffset(item);
    motion = { id, revision: ++animationRevision, from: offset, to, velocity, endVelocity: endVelocity(id), elapsed: 0,
      duration: Math.max(.28, Math.min(.6, Math.abs(to - offset) / 1100)) };
    pending = null;
  }
  function snapshot() {
    const focus = itemAtCenter();
    return { offset, focus: focus?.id ?? null,
      moving: !!motion, pending: !!pending, target: motion?.id ?? pending?.id ?? null,
      animation: motion ? { ...motion } : null };
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
          // Rebase geometry without restarting either position or velocity.
          const time = Math.min(1, motion.elapsed / motion.duration), progress = blend(time);
          const to = centerOffset(target);
          const from = progress < 1 ? (offset - to * progress - tangent(motion, time)) / (1 - progress) : offset;
          if (Math.abs(from - motion.from) > 1e-5 || Math.abs(to - motion.to) > 1e-5) {
            motion = { ...motion, from, to, revision: ++animationRevision };
          }
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
    freeze() { motion = null; pending = null; velocity = 0; return snapshot(); },
    tick: function tick(seconds, playing, speed = 'normal') {
      let waiting = false;
      drift = playing ? -(scrollSpeeds[speed] ?? scrollSpeeds.normal) : 0;
      if (motion) {
        const ending = endVelocity(motion.id);
        if (ending !== motion.endVelocity) {
          motion = { ...motion, revision: ++animationRevision, from: offset, velocity, endVelocity: ending, elapsed: 0,
            duration: Math.max(.08, motion.duration - motion.elapsed) };
        }
        const elapsed = Math.min(Math.max(0, seconds), motion.duration - motion.elapsed);
        motion.elapsed += elapsed;
        const progress = Math.min(1, motion.elapsed / motion.duration);
        offset = motion.from + (motion.to - motion.from) * blend(progress) + tangent(motion, progress);
        velocity = speedAt(motion, progress);
        if (progress === 1) {
          motion = null;
          if (seconds > elapsed) return tick(seconds - elapsed, playing, speed);
        }
      } else if (playing && !pending && initialized) {
        const index = items.findIndex(item => item.id === itemAtCenter()?.id);
        if (index >= 0 && items[index].ready) {
          let lastReady = index;
          while (items[lastReady + 1]?.ready) lastReady++;
          const limit = centerOffset(items[lastReady]);
          offset = Math.min(offset, Math.max(limit, offset + Math.max(0, seconds) * drift));
          waiting = offset <= limit;
          velocity = waiting ? 0 : drift;
        }
        else velocity = 0;
      } else velocity = 0;
      return { ...snapshot(), waiting };
    },
  };
}
