/** Navigation uses newest-first artifact order. */
export function destinationIndex(index, length, direction) {
  if (!Number.isInteger(index) || index < 0 || index >= length) return null;
  const destination = index + (direction === 'newer' ? -1 : direction === 'older' ? 1 : 0);
  if (!['newer', 'older'].includes(direction) || destination < 0 || destination >= length) return null;
  return destination;
}

export function keyboardAction(event, context) {
  if (event.repeat || event.ctrlKey || event.altKey || event.metaKey || event.shiftKey || context.editing || context.dialogOpen || !['feed', 'liked', 'generate'].includes(context.view) || context.feedbackPending) return null;
  if (['feed', 'generate', 'liked'].includes(context.view) && (event.key === ' ' || event.key === 'Spacebar')) return 'privacy';
  if (['generate', 'liked'].includes(context.view)) return null;
  return { ArrowLeft: 'older', ArrowRight: 'newer', ArrowUp: 'increase', ArrowDown: 'decrease' }[event.key] || null;
}

export function feedbackValue(current, target, toggle = true) {
  if (target !== 1 && target !== -1) throw new TypeError('Feedback must be 1 or -1');
  return toggle && current === target ? null : target;
}

/** Move one level through disliked (-1), unrated (null), liked (1). */
export function steppedFeedbackValue(current, direction) {
  const next = Math.max(-1, Math.min(1, (current ?? 0) + direction));
  return next === 0 ? null : next;
}

export function mergeArtifacts(existing, incoming, append = false) {
  const seen = new Set();
  return (append ? [...existing, ...incoming] : [...incoming, ...existing]).filter((item) => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

export function requestKey(payload) {
  return JSON.stringify([payload.backend_id, payload.positive, payload.negative, payload.seed, payload.count ?? 1, payload.repetitions ?? 1, payload.candidate ?? null]);
}

export function requestIdentity(payload, pending, createId) {
  const key = requestKey(payload);
  return pending.get(key) || { key, payload: { ...payload, request_id: createId() } };
}

export function configuredWorkflowMode(config = {}) {
  if (config.workflow_mode === 'default' || config.workflow_mode === 'custom') return config.workflow_mode;
  return config.workflow && typeof config.workflow === 'object' && Object.keys(config.workflow).length ? 'custom' : 'default';
}

export function effectiveWorkflowMode(selected, source = '') {
  return selected === 'custom' && source.trim() ? 'custom' : 'default';
}
