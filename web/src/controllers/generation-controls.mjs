function boundedGenerationCount(raw, label) {
  const value = Number(raw);
  if (!['string', 'number'].includes(typeof raw) || typeof raw === 'string' && !raw.trim() || !Number.isSafeInteger(value) || value < 1 || value > 10) {
    throw new Error(`${label}须为 1–10 之间的整数。`);
  }
  return value;
}

export const generationCount = raw => boundedGenerationCount(raw, '每次数量');
export const generationRepetitions = raw => boundedGenerationCount(raw, '生成次数');

/** Keep manually submitted images outside the recommendation feed. */
export function artifactPath(view, cursor = null, tags = []) {
  const query = new URLSearchParams({ limit: '200', source: view === 'liked' ? 'all' : view === 'generate' ? 'generate' : 'roam' });
  if (view === 'liked') {
    query.set('liked', '1');
    for (const tag of new Set(tags)) query.append('tag', tag);
  }
  if (cursor) query.set('before', cursor);
  return `/api/artifacts?${query}`;
}

export function matchesLikedTags(artifact, tags = []) {
  const terms = new Set(String(artifact.positive || '').split(',').map(text => text.trim()).filter(Boolean));
  return tags.every(tag => terms.has(tag));
}
