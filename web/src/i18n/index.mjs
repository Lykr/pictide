import { emitSignal } from '../shared/signals.mjs';
import english from './messages/en/index.mjs';

// Chinese source phrases are stable message keys; only product UI calls t().
// User content is rendered verbatim. Register a dictionary here to add a locale.
export const languages = [
  { value: 'system', label: '跟随系统' },
  { value: 'zh-CN', label: '简体中文' },
  { value: 'en', label: 'English' },
];
const dictionaries = { 'zh-CN': {}, en: english };
const sourceKeys = new Map(Object.entries(english).map(([key, value]) => [value, key]));
export function messageKey(text) { return sourceKeys.get(text) ?? text; }
let choice = 'system';
const listeners = new Set();

export function resolveLanguage(preferred = '') {
  const name = String(preferred).toLowerCase().replaceAll('_', '-');
  if (name === 'zh' || /^zh-hans(?:-|$)/.test(name) || /^zh-(cn|sg)(?:-|$)/.test(name)) return 'zh-CN';
  return 'en';
}
export function language() { return choice; }
export function locale() { return choice === 'system' ? resolveLanguage(globalThis.navigator?.language) : choice; }
export function snapshot() { return `${choice}:${locale()}`; }
export function subscribe(callback) { listeners.add(callback); return () => listeners.delete(callback); }
export function t(key, params = {}) {
  const translated = dictionaries[locale()]?.[key] ?? key;
  return translated.replace(/\{(\w+)\}/g, (match, name) => Object.hasOwn(params, name) ? String(params[name]) : match);
}
export function tr(strings, ...values) {
  return t(strings.reduce((key, text, index) => key + (index ? `{${index - 1}}` : '') + text, ''), Object.fromEntries(values.map((value, index) => [index, value])));
}
function publish() {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = locale();
    document.title = t('Pictide · 图片漫游');
  }
  for (const listener of listeners) listener();
  if (typeof document !== 'undefined') emitSignal("language-changed");
}
export function applyLanguage(value) {
  const next = value || 'system';
  if (!languages.some(item => item.value === next)) throw new Error(`Unsupported interface language: ${next}`);
  const previous = snapshot(); choice = next;
  if (snapshot() !== previous) publish();
  else if (typeof document !== 'undefined') document.documentElement.lang = locale();
}
if (typeof window !== 'undefined' && window.addEventListener) window.addEventListener('languagechange', () => { if (choice === 'system') publish(); });
if (typeof document !== 'undefined') publish();
