import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Heart, LoaderCircle } from 'lucide-react';
import { t } from '../i18n/index.mjs';
import { useApplication, useUiFact } from '../shared/application-context';
import { createRoamScroll } from '../controllers/roam-scroll.mjs';
import './roam-scroll.css';

type Picture = { id: string; width?: number; height?: number; feedback?: number | null };
type Loaded = { width: number; height: number };

/** React owns the pictures; refs only measure and animate the strip between model updates. */
export function RoamScroll({ artifacts, currentId, active, speed, busy }: {
  artifacts: Picture[]; currentId: string; active: boolean; speed: string; busy: boolean;
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
  const latest = useRef({ active, busy, speed, playback, pictures });
  latest.current = { active, busy, speed, playback, pictures };

  function paint(snapshot = motion.snapshot()) {
    if (track.current) track.current.style.transform = `translate3d(${snapshot.offset}px,0,0)`;
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
    const signature = `${snapshot.focus}:${snapshot.oldest}:${pixels?.width}:${pixels?.height}`;
    if (latest.current.active && signature !== reported.current) {
      reported.current = signature;
      app.scrollFrame({ ...snapshot, ready: !!pixels, ...pixels });
    }
  }
  function more(direction: string) {
    const signature = `${direction}:${motion.snapshot().focus}:${artifacts[0]?.id}:${artifacts.at(-1)?.id}`;
    if (requested.current === signature) return;
    requested.current = signature;
    void app.scrollMore(direction).then((available: boolean) => {
      if (!available && motion.snapshot().pending) paint(motion.freeze());
    });
  }
  useLayoutEffect(() => {
    const node = viewport.current!;
    const observer = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  useLayoutEffect(() => {
    const ids = new Set(pictures.map(item => item.id));
    for (const id of loaded.current.keys()) if (!ids.has(id)) { loaded.current.delete(id); markerPositions.current.delete(id); }
    for (const item of pictures) if (item.feedback !== 1) markerPositions.current.delete(item.id);
    paint(motion.layout(pictures.map(item => ({ id: item.id, width: item.displayWidth, ready: loaded.current.has(item.id) })), size.width, currentId));
  }, [pictures, size.width]);
  useLayoutEffect(() => app.bindScroll({
    navigate(direction: string) {
      requested.current = '';
      const found = motion.navigate(direction);
      paint();
      if (!found) more(direction);
    },
    freeze() { paint(motion.freeze()); },
  }), [app, motion, artifacts]);
  useLayoutEffect(() => {
    if (!active) { motion.freeze(); reported.current = ''; return; }
    let frame = 0, previous = 0;
    const animate = (time: number) => {
      const elapsed = previous ? Math.min(.05, (time - previous) / 1000) : 0;
      previous = time;
      const current = latest.current;
      if (!document.hidden && !current.busy) {
        const snapshot = motion.tick(elapsed, current.playback.playing, current.speed);
        paint(snapshot);
        if (snapshot.waiting) more('newer');
      }
      frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [active, app, motion, artifacts]);

  return <div ref={viewport} className="roam-scroll" data-testid="roam-scroll" aria-label={t('画轴')}>
    <div ref={track} className="roam-scroll-track">
      {pictures.map(item => <button key={item.id} type="button" className="roam-scroll-picture" data-artifact-id={item.id}
        data-selected={item.id === currentId && !playback.playing} data-liked={item.feedback === 1}
        style={{ width: item.displayWidth, height }} aria-label={t('查看这张图片')} aria-current={item.id === currentId ? 'true' : undefined}
        onClick={() => { app.pauseScroll(); motion.select(item.id); paint(); }}>
        <img alt={t('生成的图片')} draggable={false} src={`/api/artifacts/${encodeURIComponent(item.id)}/image`} decoding="async"
          onLoad={event => {
            const image = event.currentTarget;
            loaded.current.set(item.id, { width: image.naturalWidth, height: image.naturalHeight });
            setLoadVersion(version => version + 1);
          }} onError={() => app.scrollImageFailed(item.id)} />
        {!loaded.current.has(item.id) && <span className="roam-scroll-loading" aria-label={t('正在读取图片…')}><LoaderCircle aria-hidden="true" /></span>}
        {item.feedback === 1 && <span className="roam-scroll-liked" data-liked-marker aria-label={t('已喜欢')}><Heart aria-hidden="true" /></span>}
      </button>)}
    </div>
  </div>;
}
