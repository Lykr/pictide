import { createGuideMachine } from './core.mjs';
import { actProgress, GUIDE_STORAGE_KEY, GUIDE_VERSION, presentProgress, restoreProgress, settleProgress } from './pictide-flow.mjs';

export function createPictideGuide({ readFacts, subscribeFacts, navigate, storage }) {
  let facts = readFacts();
  let record;
  try { record = JSON.parse(storage?.getItem(GUIDE_STORAGE_KEY) || 'null'); } catch { record = null; }
  const restored = restoreProgress(record);
  if (!restored) record = null;
  let previous = facts;
  const machine = createGuideMachine({
    initialState: restored || { status: facts.ready ? 'invite' : 'idle', stepId: null, context: {} },
    transition(state, event) {
      if (event.type === 'facts') {
        if (!restored && !record && state.status === 'idle' && facts.ready) return { status: 'invite', stepId: null, context: {} };
        return settleProgress(state, facts, previous);
      }
      return settleProgress(actProgress(state, event.name, facts), facts);
    },
    project: state => presentProgress(state, facts),
  });
  const persist = status => {
    const state = machine.getState();
    // An invitation is not a decision. Early component publications must not
    // suppress it before bootstrap is ready, nor on the following visit.
    if (!status && (state.status === 'invite' || (state.status === 'idle' && !record))) return;
    const persistedStatus = status || (state.status === 'resume' ? 'active' : state.status === 'idle' && ['dismissed', 'done'].includes(record?.status) ? record.status : state.status);
    record = { version: GUIDE_VERSION, status: persistedStatus, stepId: state.stepId, context: {} };
    for (const key of ['firstImage', 'imageId', 'liked', 'likedImageId', 'anchorImageId', 'clearImageId']) {
      if (key in state.context) record.context[key] = state.context[key];
    }
    try { storage?.setItem(GUIDE_STORAGE_KEY, JSON.stringify(record)); } catch { /* Private browsing may deny storage. */ }
  };
  const unsubscribe = subscribeFacts(() => {
    previous = facts;
    facts = readFacts();
    // Reproject the same step when its factual wording/target changes.
    machine.dispatch({ type: 'facts' });
    persist();
  });
  return {
    getSnapshot: machine.getSnapshot,
    subscribe: machine.subscribe,
    act(name) {
      const snapshot = machine.getSnapshot();
      if (!['dismiss', 'restart', snapshot.primary?.name, snapshot.secondary?.name].includes(name)) return;
      machine.dispatch({ type: 'action', name });
      persist(name === 'dismiss' ? 'dismissed' : name === 'finish' ? 'done' : undefined);
      if (['start', 'restart', 'resume', 'back-to-roam'].includes(name)) {
        const snapshot = machine.getSnapshot();
        navigate(snapshot.expectedRoute || 'feed');
      }
    },
    dispose() { unsubscribe(); machine.dispose(); },
  };
}
