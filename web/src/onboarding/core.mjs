// A small observable state machine. Product rules and side effects stay outside.
export function createGuideMachine({ initialState, transition, project }) {
  let state = initialState;
  let snapshot = project(state);
  const listeners = new Set();
  return {
    getState: () => state,
    getSnapshot: () => snapshot,
    subscribe(callback) {
      listeners.add(callback);
      return () => listeners.delete(callback);
    },
    dispatch(event) {
      const next = transition(state, event);
      state = next;
      const projected = project(state);
      if (JSON.stringify(projected) === JSON.stringify(snapshot)) return;
      snapshot = projected;
      for (const callback of listeners) callback();
    },
    dispose() { listeners.clear(); },
  };
}
