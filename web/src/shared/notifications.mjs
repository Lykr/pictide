/** Shared notification state for React views and feature actions. */
/** @typedef {string | (() => string)} Message */
/** @typedef {{label: Message, onClick: () => unknown}} Action */
/** @typedef {{id?: string, kind?: 'error'|'success'|'warning'|'info', action?: Action, duration?: number}} Options */
/** @typedef {{id: string, sequence: number, message: Message, kind: string, action?: Action, duration: number, open: boolean}} Notice */
/** @type {Notice[]} */
let notices = [];
let sequence = 0;
const listeners = new Set();
export const notificationSnapshot = () => notices;
export const subscribeNotifications = callback => { listeners.add(callback); return () => listeners.delete(callback); };
export const notificationText = message => typeof message === 'function' ? message() : String(message || '');
const publish = () => { for (const listener of listeners) listener(); };

/** @param {Message} message @param {Options} [options] */
export function notify(message, options = {}) {
  const text = notificationText(message).trim();
  if (!text) return '';
  const kind = options.kind || 'info';
  const id = options.id || `${kind}:${text}`;
  const existing = notices.find(item => item.id === id);
  if (existing?.open && existing.kind === kind && notificationText(existing.message) === text) return id;
  const duration = options.duration ?? (kind === 'error' || kind === 'warning' ? 10000 : 4500);
  notices = [{ id, sequence: ++sequence, message, kind, action: options.action, duration, open: true },
    ...notices.filter(item => item.id !== id)].slice(0, 3);
  publish();
  return id;
}

/** @param {Message} message @param {Options} [options] */
export const notifyError = (message, options = {}) => notify(message, { ...options, kind: 'error' });
/** @param {Message} message @param {Options} [options] */
export const notifySuccess = (message, options = {}) => notify(message, { ...options, kind: 'success' });

export function dismissNotification(id) {
  const item = notices.find(notice => notice.id === id && notice.open);
  if (!item) return;
  notices = notices.map(notice => notice === item ? { ...notice, open: false } : notice);
  publish();
  setTimeout(() => {
    notices = notices.filter(notice => notice.sequence !== item.sequence);
    publish();
  }, 200);
}
