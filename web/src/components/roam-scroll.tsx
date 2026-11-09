import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Heart, LoaderCircle } from 'lucide-react';
import { t } from '../i18n/index.mjs';
import { useApplication, useUiFact } from '../shared/application-context';
import { createRoamScroll } from '../controllers/roam-scroll.mjs';
import { ScrollPrivacyImage } from './scroll-privacy';
import './roam-scroll.css';

type Picture = { id: string; width?: number; height?: number; feedback?: number | null };
type Loaded = { width: number; height: number };

/** React owns the pictures; refs only measure and animate the strip between model updates. */
export function RoamScroll({ artifacts, currentId, active, speed, busy, blurred }: {
  artifacts: Picture[]; currentId: string; active: boolean; speed: string; busy: boolean; blurred: boolean;
}) {
  const app = useApplication();
  const playback = useUiFact('playback', { playing: false });
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [loadVersion, setLoadVersion] = useState(0);
  const viewport = useRef<HTMLDivElement>(null), track = useRef<HTMLDivElement>(null);
  const motion = useMemo(() => createRoamScroll(), []);
  const loaded = useRef(new Map<string, Loaded>());
  const markerPositions = useRef(new Map<string, number>());
  const reported = useRef('');
  const requested = useRef('');
  const measured = useRef(false);
  const clock = useRef(0);
  const animation = useRef<{ revision: number; effect: Animation } | null>(null);
  const height = Math.max(1, size.height - 24);
  const pictures = useMemo(() => {
    const chronological = [...artifacts].reverse();
    const index = Math.max(0, chronological.findIndex(item => item.id === currentId));
    const width = (item: Picture) => {
      const pixels = loaded.current.get(item.id) ?? item;
      return height * ((pixels.width || 3) / (pixels.height || 4));
    };
    // Cover the viewport plus preload space on each side, with a bounded DOM window.
    let first = index, last = index, left = 0, right = 0;
    while (first > 0 && index - first < 15 && (index - first < 3 || left < size.width)) left += width(chronological[--first]) + 12;
    while (last < chronological.length - 1 && last - index < 15 && (last - index < 3 || right < size.width)) right += width(chronological[++last]) + 12;
    return chronological.slice(first, last + 1).map(item => ({ ...item, displayWidth: width(item) }));
  }, [artifacts, currentId, height, size.width, loadVersion]);
  const latest = useRef({ active, busy, speed, playback, artifacts });
  latest.current = { active, busy, speed, playback, artifacts };

  function paint(snapshot = motion.snapshot()) {
    if (!measured.current) return;
    const strip = track.current, path = snapshot.animation;
    if (strip) {
      if (path && Math.abs(path.to - path.from) > .01) {
        if (animation.current?.revision !== path.revision) {
          animation.current?.effect.cancel();
          const distance = path.to - path.from;
          const start = path.velocity * path.duration / (3 * distance);
          const end = 1 - path.endVelocity * path.duration / (3 * distance);
          const effect = strip.animate([
            { transform: `translate3d(${path.from}px,0,0)` },
            { transform: `translate3d(${path.to}px,0,0)` },
          ], { duration: path.duration * 1000, easing: `cubic-bezier(${1 / 3},${start},${2 / 3},${end})`, fill: 'both' });
          effect.startTime = (clock.current || performance.now()) - path.elapsed * 1000;
          animation.current = { revision: path.revision, effect };
        }
        const effect = animation.current!.effect;
        if (latest.current.busy || document.hidden) {
          effect.pause(); effect.currentTime = path.elapsed * 1000;
        } else if (effect.playState === 'paused') {
          effect.play(); effect.startTime = (clock.current || performance.now()) - path.elapsed * 1000;
        }
      } else {
        strip.style.transform = `translate3d(${snapshot.offset}px,0,0)`;
        animation.current?.effect.cancel(); animation.current = null;
      }
    }
    if (viewport.current) {
      viewport.current.dataset.focus = snapshot.focus ?? '';
      viewport.current.dataset.moving = String(snapshot.moving);
      viewport.current.dataset.offset = String(snapshot.offset);
      for (const marker of viewport.current.querySelectorAll<HTMLElement>('[data-liked-marker]')) {
        const tile = marker.parentElement!;
        const id = tile.dataset.artifactId!;
        if (!markerPositions.current.has(id)) {
          const tileLeft = tile.offsetLeft + snapshot.offset;
          markerPositions.current.set(id, Math.max(12, Math.min(tile.offsetWidth - 40, 12 - tileLeft)));
        }
        marker.style.left = `${markerPositions.current.get(id)}px`;
      }
    }
    const pixels = loaded.current.get(snapshot.focus ?? '');
    const signature = `${snapshot.focus}:${pixels?.width}:${pixels?.height}`;
    if (latest.current.active && signature !== reported.current) {
      reported.current = signature;
      app.scrollFrame({ ...snapshot, ready: !!pixels, ...pixels });
    }
  }
  function advance(time: number) {
    const now = Math.max(time, clock.current);
    const elapsed = clock.current ? (now - clock.current) / 1000 : 0;
    clock.current = now;
    const current = latest.current;
    return measured.current && !document.hidden && !current.busy
      ? motion.tick(elapsed, current.playback.playing, current.speed) : motion.snapshot();
  }
  function more(direction: string) {
    const current = latest.current.artifacts;
    const signature = `${direction}:${motion.snapshot().focus}:${current[0]?.id}:${current.at(-1)?.id}`;
    if (requested.current === signature) return;
    requested.current = signature;
    void app.scrollMore(direction).then((available: boolean) => {
      if (!available && motion.snapshot().pending) paint(motion.freeze());
    });
  }
  useLayoutEffect(() => {
    const node = viewport.current!;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width && height) setSize({ width, height });
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  useLayoutEffect(() => {
    measured.current = active && size.width > 0 && size.height > 0;
    if (!measured.current) return;
    const ids = new Set(pictures.map(item => item.id));
    for (const id of loaded.current.keys()) if (!ids.has(id)) { loaded.current.delete(id); markerPositions.current.delete(id); }
    for (const item of pictures) if (item.feedback !== 1) markerPositions.current.delete(item.id);
    paint(motion.layout(pictures.map(item => ({ id: item.id, width: item.displayWidth, ready: loaded.current.has(item.id) })), size.width, currentId));
  }, [pictures, size.width, size.height, active]);
  useLayoutEffect(() => app.bindScroll({
    navigate(direction: string) {
      advance(performance.now());
      requested.current = '';
      const found = motion.navigate(direction);
      paint();
      if (!found) more(direction);
    },
    freeze() { advance(performance.now()); paint(motion.freeze()); },
  }), [app, motion]);
  useLayoutEffect(() => {
    if (!active) {
      animation.current?.effect.cancel(); animation.current = null;
      motion.freeze(); reported.current = ''; clock.current = 0; return;
    }
    let frame = 0;
    const animate = (time: number) => {
      if (measured.current) {
        const snapshot = advance(time);
        paint(snapshot);
        if ('waiting' in snapshot && snapshot.waiting) more('newer');
      }
      frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);
    return () => { cancelAnimationFrame(frame); animation.current?.effect.cancel(); animation.current = null; clock.current = 0; };
  }, [active, app, motion]);

  return <div ref={viewport} className="roam-scroll" data-testid="roam-scroll" aria-label={t('画轴')}>
    <div ref={track} className="roam-scroll-track">
      {pictures.map(item => <button key={item.id} type="button" className="roam-scroll-picture" data-artifact-id={item.id} data-touch-navigation
        data-selected={item.id === currentId && !playback.playing} data-liked={item.feedback === 1}
        style={{ width: item.displayWidth, height }} aria-label={t('查看这张图片')} aria-current={item.id === currentId ? 'true' : undefined}
        onClick={() => { advance(performance.now()); app.pauseScroll(); motion.select(item.id); paint(); }}>
        <ScrollPrivacyImage src={`/api/artifacts/${encodeURIComponent(item.id)}/image`} height={height} blurred={blurred}
          onLoad={image => {
            loaded.current.set(item.id, { width: image.naturalWidth, height: image.naturalHeight });
            setLoadVersion(version => version + 1);
          }} onError={() => app.scrollImageFailed(item.id)} />
        {!loaded.current.has(item.id) && <span className="roam-scroll-loading" aria-label={t('正在读取图片…')}><LoaderCircle aria-hidden="true" /></span>}
        {item.feedback === 1 && <span className="roam-scroll-liked" data-liked-marker aria-label={t('已喜欢')}><Heart aria-hidden="true" /></span>}
      </button>)}
    </div>
  </div>;
}
