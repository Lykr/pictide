const systemAppearance = window.matchMedia('(prefers-color-scheme: dark)');
let selectedTheme = 'system';

/** Return the saved choice, independently of the current system appearance. */
export function currentTheme() {
  return selectedTheme;
}

function renderTheme() {
  const dark = selectedTheme === 'dark' || (selectedTheme === 'system' && systemAppearance.matches);
  document.documentElement.classList.toggle('dark', dark);
  document.dispatchEvent(new Event('pictide:theme-changed'));
}

export function applyTheme(theme) {
  selectedTheme = theme;
  renderTheme();
}

systemAppearance.addEventListener('change', () => {
  if (selectedTheme === 'system') renderTheme();
});
renderTheme();

async function requestTheme(options = {}) {
  const response = await fetch('/api/settings/general', options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败（${response.status}）`);
  applyTheme(data.theme);
  return data.theme;
}

export const loadTheme = () => requestTheme();
export const saveTheme = theme => requestTheme({ method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ theme }) });
