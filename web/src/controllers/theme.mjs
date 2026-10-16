export function currentTheme() {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
}

export function applyTheme(theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark');
  document.dispatchEvent(new Event('pictide:theme-changed'));
}

async function requestTheme(options = {}) {
  const response = await fetch('/api/settings/general', options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败（${response.status}）`);
  applyTheme(data.theme);
  return data.theme;
}

export const loadTheme = () => requestTheme();
export const saveTheme = theme => requestTheme({ method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ theme }) });
