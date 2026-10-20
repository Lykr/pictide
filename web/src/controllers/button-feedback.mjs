import { t, messageKey } from '../i18n/index.mjs';
import { notify } from '../shared/notifications.mjs';
// Controller-owned buttons keep their shadcn styling and disabled state.
export function createButtonFeedback(button, createIcon, { announce = notify } = {}) {
  const original = [...button.childNodes];
  const attributes = ['aria-label', 'data-tooltip', 'aria-busy'];
  const saved = attributes.map(name => [name, button.getAttribute(name)]);
  const label = button.getAttribute('aria-label') || button.textContent.trim();
  function reset() {
    button.replaceChildren(...original);
    for (const [name, value] of saved) {
      if (value === null) button.removeAttribute(name);
      else button.setAttribute(name, t(messageKey(value)));
    }
    delete button.dataset.feedback;
  }
  function show(status, text, detail = text) {
    reset();
    if (status !== 'pending') {
      announce(detail, { kind: status, ...(button.id ? { id: `button-${button.id}` } : {}) });
      return;
    }
    const icon = createIcon('LoaderCircle');
    icon.classList.add('animate-spin');
    // Keep the original caption and footprint while the operation is in flight.
    button.replaceChildren(...original.map(node => node.nodeName?.toLowerCase() === 'svg' ? icon : node));
    const announcement = button.ownerDocument.createElement('span');
    announcement.className = 'sr-only'; announcement.setAttribute('role', 'status');
    announcement.textContent = detail; button.append(announcement);
    button.dataset.feedback = status;
    button.setAttribute('aria-label', `${t(messageKey(label))}: ${detail}`);
    button.dataset.tooltip = detail;
    button.setAttribute('aria-busy', 'true');
  }
  return { show, reset };
}
