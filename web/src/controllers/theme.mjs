import { emitSignal } from '../shared/signals.mjs';
import { applyLanguage, tr } from '../i18n/index.mjs';
import { applyImageTransitions } from './image-transitions.mjs';
const systemAppearance = window.matchMedia('(prefers-color-scheme: dark)');
let selectedTheme = 'system';

/** Return the saved choice, independently of the current system appearance. */
export function currentTheme() {
  return selectedTheme;
}

function renderTheme() {
  const dark = selectedTheme === 'dark' || (selectedTheme === 'system' && systemAppearance.matches);
  document.documentElement.classList.toggle('dark', dark);
  const chrome = document.querySelector('meta[name="theme-color"]');
  if (chrome) chrome.setAttribute('content', dark ? '#0a0a0a' : '#ffffff');
  emitSignal("theme-changed");
}

export function applyTheme(theme) {
  selectedTheme = theme;
  renderTheme();
}

systemAppearance.addEventListener('change', () => {
  if (selectedTheme === 'system') renderTheme();
});
renderTheme();

let settingsRevision = 0, pendingWrites = 0, readSerial = 0, appliedRead = 0;
async function requestTheme(options = {}) {
  const writing = options.method === 'PUT';
  if (writing) { pendingWrites++; settingsRevision++; }
  const revision = settingsRevision, serial = ++readSerial;
  try {
    const response = await fetch('/api/settings/general', options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || tr`请求失败（${response.status}）`);
    // Older SSE reads must not undo a newer user choice.
    if (writing || !pendingWrites && revision === settingsRevision && serial >= appliedRead) {
      appliedRead = serial;
      applyTheme(data.theme);
      applyLanguage(data.language);
      applyImageTransitions(data.image_transitions);
    }
    return data.theme;
  } finally { if (writing) { pendingWrites--; settingsRevision++; } }
}

export const loadTheme = () => requestTheme();
export const saveTheme = theme => requestTheme({ method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ theme }) });

export const saveLanguage = language => requestTheme({ method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ language }) });

export const saveImageTransitions = image_transitions => requestTheme({ method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image_transitions }) });
