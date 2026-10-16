import { requestKey } from './feed-controls.mjs';

export const MAX_RULE_SEED = Number.MAX_SAFE_INTEGER;
export const MAX_SEQUENCE_STEP = 1000;

export function ruleVisibility(source, mode, autoGenerate) {
  const rules = source === 'rules';
  return {
    rules,
    seed: rules && mode !== 'random_each_run',
    sequence: rules && mode === 'sequence',
    positiveRequired: !rules || !autoGenerate,
  };
}

export function counterAfter(value, control, maximum, random = Math.random) {
  if (control === 'increment') return Math.min(maximum, value + 1);
  if (control === 'decrement') return Math.max(0, value - 1);
  if (control === 'randomize') return Math.min(maximum, Math.max(0, Math.floor(random() * (maximum + 1))));
  return value;
}

export function nextRuleCounters(current, result, random = Math.random) {
  const seeded = current.mode === 'fixed_seed' || current.mode === 'sequence';
  const sequenceSeed = result.sequence?.seed ?? current.seed;
  const seed = current.mode === 'sequence' ? sequenceSeed : result.seed;
  return {
    seed: seeded ? counterAfter(seed, current.seedControl, MAX_RULE_SEED, random) : current.seed,
    step: current.mode === 'sequence' ? counterAfter(current.step, current.stepControl, MAX_SEQUENCE_STEP, random) : current.step,
  };
}

// Resolve an uncertain image request before drawing a new set of prompt terms.
export function submissionDecision(payload, pending, rulesAutoGenerate) {
  const retry = pending.get(requestKey(payload)) || null;
  return { retry, generatePrompts: !!rulesAutoGenerate && !retry };
}

export function afterPromptEdit(source, autoGenerate) {
  return source === 'rules' ? false : autoGenerate;
}
