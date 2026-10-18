import { t, tr, locale } from '../i18n/index.mjs';
export const API_KEY_MASK = '••••••••';

// The server never returns the saved secret. Keep the mask out of all requests.
export function apiKeyFields(value, hasSavedKey) {
  if (hasSavedKey && value === API_KEY_MASK) return {};
  if (value.includes('•')) throw new Error(t("请完整替换密钥遮罩，或清空输入框后保存。"));
  return { api_key: value };
}

export function customWorkflowName(names) {
  const existing = new Set(names.map(name => name.normalize('NFKC').trim().toLocaleLowerCase()));
  let name = t("自定义工作流"), index = 2;
  while (existing.has(name.toLocaleLowerCase())) name = tr`自定义工作流 ${index++}`;
  return name;
}
