/** Clipboard API needs HTTPS; LAN HTTP can still use the user-initiated copy command. */
export async function copyText(text: string) {
  if (navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(text); return; } catch { /* Try the browser's local copy command. */ }
  }
  const focused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const selection = document.getSelection();
  const ranges = selection ? Array.from({ length: selection.rangeCount }, (_, i) => selection.getRangeAt(i).cloneRange()) : [];
  const field = document.createElement("textarea");
  field.value = text;
  field.readOnly = true;
  field.tabIndex = -1;
  field.style.cssText = "position:fixed;inset:0 auto auto 0;width:1px;height:1px;opacity:0;font-size:16px";
  (focused?.closest("[data-slot=dialog-content]") ?? document.body).append(field);
  try {
    field.select();
    field.setSelectionRange(0, text.length);
    if (!document.execCommand("copy")) throw new Error("浏览器不允许复制，请选中文本复制。");
  } finally {
    field.remove();
    focused?.focus({ preventScroll: true });
    if (selection) { selection.removeAllRanges(); for (const range of ranges) selection.addRange(range); }
  }
}
