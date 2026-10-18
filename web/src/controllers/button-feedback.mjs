import { t, messageKey } from '../i18n/index.mjs';
// Controller-owned buttons keep their shadcn styling and disabled state.
export function createButtonFeedback(button, createIcon, { delay = 2000, schedule = setTimeout, cancel = clearTimeout } = {}) {
  const original = [...button.childNodes];
  const attributes = ['aria-label', 'data-tooltip', 'aria-busy'];
  const saved = attributes.map(name => [name, button.getAttribute(name)]);
  const label = button.getAttribute('aria-label') || button.textContent.trim();
  const iconOnly = !button.textContent.trim();
  let timer, revision = 0;
  function reset() {
    revision++; cancel(timer);
    button.replaceChildren(...original);
    for (const [name, value] of saved) {
      if (value === null) button.removeAttribute(name);
      else button.setAttribute(name, t(messageKey(value)));
    }
    delete button.dataset.feedback;
  }
  function show(status, text, detail = text) {
    const token = ++revision; cancel(timer);
    const icon = createIcon(status === 'pending' ? 'LoaderCircle' : status === 'success' ? 'Check' : status === 'warning' ? 'CircleHelp' : 'CircleX');
    if (status === 'pending') icon.classList.add('animate-spin');
    button.replaceChildren(icon);
    if (!iconOnly) button.append(button.ownerDocument.createTextNode(text));
    const announcement = button.ownerDocument.createElement('span');
    announcement.className = 'sr-only'; announcement.setAttribute('role', 'status');
    announcement.textContent = detail; button.append(announcement);
    button.dataset.feedback = status;
    button.setAttribute('aria-label', `${t(messageKey(label))}: ${detail}`);
    button.dataset.tooltip = detail;
    button.setAttribute('aria-busy', String(status === 'pending'));
    // Errors and uncertain submissions stay available until the next attempt.
    if (status === 'success') timer = schedule(() => { if (token === revision) reset(); }, delay);
  }
  return { show, reset };
}
