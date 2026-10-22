/** Small per-feature observable model. Drafts are ordinary data, never DOM nodes. */
export function createModel(data) {
  let revision = 0;
  const listeners = new Set();
  return {
    data,
    snapshot: () => revision,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    changed() { revision++; for (const listener of listeners) listener(); },
  };
}
