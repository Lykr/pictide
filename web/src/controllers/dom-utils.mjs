import { t, locale } from '../i18n/index.mjs';

export const $ = (id) => document.getElementById(id);
export const localizedMessages = new Map();
export function setStatusText(id, message) {
  if (typeof message === 'function') localizedMessages.set(id, message); else localizedMessages.delete(id);
  const text = typeof message === 'function' ? message() : message;
  $(id).textContent = text;
  return text;
}
export function describeAction(element, label) { element.setAttribute('aria-label', label); element.dataset.tooltip = label; }
export function inlineStatus(id, message, visible = true) { const element = $(id); setStatusText(id, message); element.hidden = !visible; }
export function translatedOption(value, key) { const item = option(value, t(key)); item.dataset.i18nKey = key; return item; }
export function option(value, label) { const item = document.createElement('option'); item.value = value; item.textContent = label; return item; }
export function dateLabel(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '' : date.toLocaleString(locale(), { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }); }
