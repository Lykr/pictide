import Sortable from "sortablejs";

export function sortFixedTags(element, onMove) {
  const sortable = new Sortable(element, {
    handle: ".cooc-fixed-handle", draggable: ".cooc-fixed-row", animation: 150,
    ghostClass: "cooc-fixed-ghost",
    onEnd({ item, from, oldIndex, newIndex }) {
      if (oldIndex === undefined || newIndex === undefined || oldIndex === newIndex) return;
      // Restore the DOM before React applies the new array order.
      item.remove();
      from.insertBefore(item, from.children[oldIndex] ?? null);
      onMove(oldIndex, newIndex);
    },
  });
  return () => sortable.destroy();
}
