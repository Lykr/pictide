// Preserve complete fixed entries that contain commas before splitting other tags.
export function anchorTerms(positive, pins, fixed) {
  const normalize = text => text.trim().replaceAll("_", " ");
  const known = [...new Set([...pins, ...fixed].map(normalize))];
  const groups = known.map(text => ({ text, parts: text.split(",").map(normalize) }))
    .sort((a, b) => b.parts.length - a.parts.length);
  const parts = positive.split(",").map(normalize).filter(Boolean);
  const current = [];
  for (let index = 0; index < parts.length;) {
    const group = groups.find(item => item.parts.every((part, offset) => parts[index + offset] === part));
    current.push(group ? group.text : parts[index]);
    index += group ? group.parts.length : 1;
  }
  return [...new Set([...known, ...current])];
}
