/** The browser scrolls the document only when the mobile CSS selects it. */
export function createPageScroll({ window: win = window, document: doc = document } = {}) {
  const positions = new Map();
  const enabled = () => win.getComputedStyle(doc.documentElement).getPropertyValue('--pictide-document-scroll').trim() === '1';
  let current = null, revision = 0, pending = false;
  return {
    save() {
      if (current !== null && !pending && enabled()) positions.set(current, win.scrollY);
    },
    restore(view) {
      if (view === current) return;
      current = view;
      const token = ++revision;
      pending = enabled();
      if (!pending) return;
      win.requestAnimationFrame(() => {
        if (token !== revision) return;
        pending = false;
        if (enabled()) win.scrollTo({ left: 0, top: positions.get(view) ?? 0, behavior: 'instant' });
      });
    },
  };
}
