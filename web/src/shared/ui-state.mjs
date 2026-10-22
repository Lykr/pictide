// Read-only UI facts and explicit user intents, shared independently of consumers.
let facts = {};
const listeners = new Set();
const actions = new Set();
export const getUiState = () => facts;
export const subscribeUiState = callback => { listeners.add(callback); return () => listeners.delete(callback); };
export function publishUiState(patch) {
  if (Object.entries(patch).every(([key, value]) => Object.is(facts[key], value))) return;
  facts = { ...facts, ...patch };
  for (const callback of listeners) callback();
}
export const subscribeUiActions = callback => { actions.add(callback); return () => actions.delete(callback); };
export function requestUiAction(name, value) { for (const callback of actions) callback(name, value); }

// The mounted application supplies commands; unlike document events, requests
// have a single owner, a result, and normal error propagation.
let commands = {};
export function bindUiCommands(next) { commands = next; return () => { if (commands === next) commands = {}; }; }
export function runUiCommand(name, value) {
  if (!commands[name]) throw new Error(`Unavailable UI command: ${name}`);
  return commands[name](value);
}
