/** Keep one native transform effect for the strip, including pauses and autoplay. */
export function createScrollAnimation(strip) {
  let native = null, revision = null, heldOffset = NaN, endpoint = NaN;
  const transform = offset => `translate3d(${offset}px,0,0)`;
  const keyframes = (from, to = from) => [{ transform: transform(from) }, { transform: transform(to) }];
  return {
    paint(frame, time, paused = false) {
      if (!native) {
        native = strip.animate(keyframes(frame.offset), { duration: 1, fill: 'both' });
        native.pause(); native.currentTime = 0;
      }
      const effect = native.effect, path = frame.animation;
      // A naturally completed curve already holds this position. Rewriting it
      // at arrival needlessly invalidates WebKit's composited image surface.
      if (!paused && !path && revision !== null && Math.abs(frame.offset - endpoint) < .01) return;
      if (paused || !path || Math.abs(path.to - frame.offset) < .01) {
        if (revision !== null || heldOffset !== frame.offset) {
          native.pause();
          effect.setKeyframes(keyframes(frame.offset));
          effect.updateTiming({ duration: 1, easing: 'linear', fill: 'both' });
          native.currentTime = 0;
          revision = null; heldOffset = frame.offset;
        }
        return;
      }
      if (revision === path.revision) return;
      // Start at the visible position. Replaying an earlier part of the trajectory
      // can expose its first frame while WebKit installs the updated animation.
      const duration = Math.max(.001, path.duration - path.elapsed);
      const distance = path.to - frame.offset;
      const start = frame.velocity * duration / (3 * distance);
      const end = 1 - path.endVelocity * duration / (3 * distance);
      native.pause();
      effect.setKeyframes(keyframes(frame.offset, path.to));
      effect.updateTiming({ duration: duration * 1000, easing: `cubic-bezier(${1 / 3},${start},${2 / 3},${end})`, fill: 'both' });
      native.currentTime = 0;
      native.play(); native.startTime = time;
      revision = path.revision; heldOffset = NaN; endpoint = path.to;
    },
    dispose() { native?.cancel(); native = null; },
  };
}
