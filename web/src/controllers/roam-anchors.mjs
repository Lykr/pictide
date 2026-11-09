const normalize = text => text.trim().replaceAll("_", " ");
export const anchorKey = text => normalize(text).toLowerCase().replace(/\s+/g, " ").trim();

// Preserve complete fixed entries that contain commas before splitting other tags.
export function anchorTerms(positive, pins, fixed, excluded = []) {
  const known = [...new Set([...fixed, ...pins, ...excluded].map(normalize))];
  const groups = known.map(text => ({ text, parts: text.split(",").map(anchorKey) }))
    .sort((a, b) => b.parts.length - a.parts.length);
  const parts = positive.split(",").map(normalize).filter(Boolean);
  const keys = parts.map(anchorKey);
  const current = [];
  for (let index = 0; index < parts.length;) {
    const group = groups.find(item => item.parts.every((part, offset) => keys[index + offset] === part));
    current.push(group && group.parts.length > 1 ? group.text : parts[index]);
    index += group ? group.parts.length : 1;
  }
  const labels = new Map();
  for (const text of [...fixed.map(normalize), ...current, ...pins.map(normalize), ...excluded.map(normalize)]) {
    const key = anchorKey(text);
    if (!labels.has(key)) labels.set(key, text);
  }
  return [...labels.values()];
}
