import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react';
import { createPortal } from 'react-dom';
import { Compass, X } from 'lucide-react';
import { Button } from '../ui/button';
import { t } from '../../i18n/index.mjs';
import { createPictideGuide } from '../../onboarding/pictide-adapter.mjs';
import { getUiState, requestUiAction, subscribeUiActions, subscribeUiState } from '../../shared/ui-state.mjs';
import { subscribeTargets, targetSnapshot, visibleTarget, visibleTargets } from '../../shared/ui-targets';
import '../../styles/onboarding.css';

type Action = { label: string; name: string };
type GuideSnapshot = { status: string; stepId: string | null; messages: string[]; targets: string[]; expectedRoute?: string; primary?: Action; secondary?: Action };
type Box = { name: string; x: number; y: number; width: number; height: number };
type Layout = { boxes: Box[]; top: number; bottom: number };
function storage() { try { return window.localStorage; } catch { return undefined; } }

export function GuideLayer() {
  const [guide] = useState(() => createPictideGuide({ readFacts: getUiState, subscribeFacts: subscribeUiState,
    navigate: (route: string) => requestUiAction('navigate', route), storage: storage() }));
  const view = useSyncExternalStore(guide.subscribe, guide.getSnapshot) as GuideSnapshot;
  const facts = useSyncExternalStore(subscribeUiState, getUiState) as Record<string, unknown>;
  const registration = useSyncExternalStore(subscribeTargets, targetSnapshot);
  const card = useRef<HTMLElement>(null);
  const [layout, setLayout] = useState<Layout>({ boxes: [], top: -1, bottom: 12 });
  const active = view.status !== 'idle';
  const away = view.status === 'active' && view.expectedRoute && facts.route !== view.expectedRoute;
  const targetKey = away ? '' : view.targets.join('|');

  useEffect(() => {
    const stop = subscribeUiActions((name: string) => { if (name === 'onboarding.restart') guide.act('restart'); });
    return () => { stop(); guide.dispose(); };
  }, [guide]);
  useEffect(() => {
    if (!active) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !event.defaultPrevented && !document.querySelector('[role="dialog"],[role="alertdialog"],[data-slot="popover-content"][data-state="open"]')) {
        guide.act('dismiss');
      }
    };
    document.addEventListener('keydown', escape);
    return () => document.removeEventListener('keydown', escape);
  }, [active, guide]);

  useLayoutEffect(() => {
    if (!active) return;
    let frame = 0;
    const measure = () => {
      frame = 0;
      const viewport = window.visualViewport;
      const top = viewport?.offsetTop ?? 0;
      const left = viewport?.offsetLeft ?? 0;
      const height = viewport?.height ?? innerHeight;
      const width = viewport?.width ?? innerWidth;
      const bottom = top + height;
      const navigation = visibleTarget('app.navigation')?.getBoundingClientRect();
      const inset = navigation && navigation.width > navigation.height && navigation.bottom <= bottom + 2
        ? Math.max(0, bottom - navigation.top) : 0;
      const elements = targetKey.split('|').filter(Boolean).map(name => ({ name, element: visibleTarget(name) })).filter(item => item.element);
      const boxes = elements.map(({ name, element }) => {
        const rect = element!.getBoundingClientRect();
        const x = Math.max(left + 4, rect.left - 4), y = Math.max(top + 4, rect.top - 4);
        return { name, x, y, width: Math.max(0, Math.min(left + width - 4, rect.right + 4) - x),
          height: Math.max(0, Math.min(bottom - 4, rect.bottom + 4) - y) };
      }).filter(box => box.width > 0 && box.height > 0);
      const cardRect = card.current?.getBoundingClientRect();
      const cardHeight = cardRect?.height ?? 100;
      const preferred = bottom - inset - cardHeight - 12;
      // Keep normal controls usable too, e.g. browsing while a clear hint stays on screen.
      const controls = visibleTargets().filter(element => element.matches('button,input,textarea,select,[role="button"]')).map(element => {
        const rect = element.getBoundingClientRect();
        return { x: rect.left, y: rect.top, width: rect.width, height: rect.height };
      });
      const obstacles = [...boxes, ...controls].filter(box => box.height < height * 0.65 && box.y + box.height > top && box.y < bottom
        && (!cardRect || box.x < cardRect.right && box.x + box.width > cardRect.left));
      const positions = [preferred, ...obstacles.flatMap(box => [box.y - cardHeight - 12, box.y + box.height + 12])]
        .filter(y => y >= top + 8 && y + cardHeight <= bottom - inset - 8).sort((a, b) => b - a);
      const cardTop = positions.find(y => !obstacles.some(box => box.y < y + cardHeight + 8 && box.y + box.height > y - 8)) ?? preferred;
      const next = { boxes, top: Math.max(top + 8, cardTop), bottom: inset + 12 };
      setLayout(previous => JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(measure); };
    const observer = new ResizeObserver(schedule);
    const roots = new Set<HTMLElement>();
    for (const name of [...targetKey.split('|'), 'app.navigation']) {
      const element = visibleTarget(name);
      if (element) {
        // A sibling's text/visibility can move a target without resizing it.
        let root = element;
        while (root.parentElement && root.parentElement !== document.body) {
          observer.observe(root);
          root = root.parentElement;
        }
        roots.add(root);
      }
    }
    const mutations = new MutationObserver(schedule);
    for (const root of roots) mutations.observe(root, { subtree: true, childList: true, characterData: true, attributes: true });
    if (card.current) observer.observe(card.current);
    // Layout-only changes (panel resizing, text wrapping) need no business notification.
    observer.observe(document.documentElement);
    document.addEventListener('scroll', schedule, true);
    window.addEventListener('resize', schedule);
    window.visualViewport?.addEventListener('resize', schedule);
    window.visualViewport?.addEventListener('scroll', schedule);
    schedule();
    return () => {
      cancelAnimationFrame(frame); observer.disconnect(); mutations.disconnect();
      document.removeEventListener('scroll', schedule, true);
      window.removeEventListener('resize', schedule);
      window.visualViewport?.removeEventListener('resize', schedule);
      window.visualViewport?.removeEventListener('scroll', schedule);
    };
  }, [active, targetKey, registration, view.stepId]);

  useEffect(() => {
    if (!active || !targetKey) return;
    const element = visibleTarget(targetKey.split('|')[0]);
    if (!element) return;
    const rect = element.getBoundingClientRect();
    if (rect.top < 0 || rect.bottom > (window.visualViewport?.height ?? innerHeight)) {
      element.scrollIntoView({ block: rect.height > innerHeight * 0.65 ? 'start' : 'center', behavior: 'instant' });
    }
  }, [active, view.stepId, targetKey, registration]);

  if (!active) return null;
  const action = (item: Action | undefined, primary = false) => item && <Button variant={primary ? 'default' : 'ghost'}
    type="button" onClick={() => guide.act(item.name)}>{t(item.label)}</Button>;
  return createPortal(<div className="guide-layer">
    {layout.boxes.map(box => <div key={box.name} data-guide-focus={box.name} className="guide-focus" aria-hidden="true"
      style={{ left: box.x, top: box.y, width: box.width, height: box.height }} />)}
    <section ref={card} className="guide-card" data-guide-step={view.stepId ?? view.status} aria-label={t('新手引导')}
      style={layout.top >= 0 ? { top: layout.top } : { bottom: layout.bottom }}>
      <Compass className="guide-mark" aria-hidden="true" />
      <div className="guide-content">
        <div id="guide-message" className="guide-message" role="status" aria-live="polite" aria-atomic="true">
          {(away ? ['回到当前步骤，继续一起探索。'] : view.messages).map(message => <p key={message}>{t(message)}</p>)}
        </div>
        <div className="guide-actions">
          {away ? <Button type="button" onClick={() => requestUiAction('navigate', view.expectedRoute)}>{t('回到当前步骤')}</Button> : action(view.primary, true)}
          {view.secondary?.name !== 'dismiss' || view.status !== 'active' ? action(view.secondary) : null}
        </div>
      </div>
      {view.status === 'active' && <Button className="guide-dismiss" variant="ghost" size="icon-sm" type="button"
        aria-label={t('结束引导')} onClick={() => guide.act('dismiss')}><X aria-hidden="true" /></Button>}
    </section>
  </div>, document.body);
}
