export function playbackInterval(value) {
  if (!['number', 'string'].includes(typeof value) || String(value).trim() === '') throw new Error('请输入展示秒数。');
  const seconds = Number(value);
  if (!Number.isInteger(seconds) || seconds < 1 || seconds > 600) throw new Error('展示时间须为 1–600 秒之间的整数。');
  return seconds;
}

/** One timeout per loaded picture; unavailable next images are resumed by gallery events. */
export function createRoamPlayback({ advance, changed = () => {}, cancelWait = () => {}, schedule = setTimeout, cancel = clearTimeout, now = () => performance.now() }) {
  let playing = false, seconds = 5, timer, startedAt = null, cycle = 0;
  let quickMode = false, quickFactor = 0.5;
  const duration = () => seconds * 1000 * (quickMode ? quickFactor : 1);
  let imageId = null, ready = false, active = false, busy = false, blocked = false;
  let due = false, advancing = false, revision = 0;
  const clear = () => { if (timer !== undefined) cancel(timer); timer = undefined; startedAt = null; };
  const notify = () => changed({ playing, canPlay: active && !!imageId && !blocked, startedAt, durationMs: duration(), quickMode, cycle, waiting: due });
  const go = async () => {
    if (!playing || !active || !ready || busy || blocked || advancing) return;
    advancing = true;
    const token = revision;
    try { await advance(() => playing && token === revision); }
    finally { advancing = false; }
  };
  const arm = () => {
    if (timer !== undefined || !playing || !active || !ready || busy || blocked || due || !imageId) return;
    startedAt = now(); cycle++;
    timer = schedule(() => { timer = undefined; startedAt = null; due = true; notify(); void go(); }, duration());
  };
  function pause() {
    const ownedWait = playing && due;
    playing = false; due = false; revision++; clear();
    if (ownedWait) cancelWait();
    notify();
  }
  return {
    get playing() { return playing; },
    update(next) {
      if (next.imageId !== imageId) { clear(); due = false; imageId = next.imageId; }
      ready = next.ready; active = next.active; busy = next.busy; blocked = next.blocked;
      if (!active || blocked) { pause(); return; }
      if (!ready || busy) clear();
      arm(); notify();
    },
    toggle() {
      if (playing) pause();
      else if (active && imageId && !blocked) { playing = true; due = false; revision++; arm(); notify(); }
    },
    pause,
    restart() {
      const ownedWait = playing && due;
      clear(); due = false; revision++;
      if (ownedWait) cancelWait();
      arm(); notify();
    },
    setQuickMode(enabled, factor = 0.5) {
      if (quickMode === enabled && quickFactor === factor) return;
      const previousDuration = duration(), previousMode = quickMode;
      quickMode = enabled; quickFactor = factor;
      if (quickMode !== previousMode || duration() !== previousDuration) this.restart();
      else notify();
    },
    setInterval(value) {
      const next = playbackInterval(value);
      if (next === seconds) return;
      seconds = next;
      if (!due) { clear(); arm(); }
      notify();
    },
    retry() { if (due) void go(); else arm(); notify(); },
  };
}
