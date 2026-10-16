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
export function artifactPath(view, cursor = null) {
  const query = new URLSearchParams({ limit: '200', source: view === 'liked' ? 'all' : view === 'generate' ? 'generate' : 'roam' });
  if (view === 'liked') query.set('liked', '1');
  if (cursor) query.set('before', cursor);
  return `/api/artifacts?${query}`;
}
