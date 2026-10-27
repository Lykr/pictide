import { t, tr, locale } from '../i18n/index.mjs';
import { backendCapabilities } from './backend-controls.mjs';
function boundedGenerationCount(raw, label) {
  const value = Number(raw);
  if (!['string', 'number'].includes(typeof raw) || typeof raw === 'string' && !raw.trim() || !Number.isSafeInteger(value) || value < 1 || value > 10) {
    throw new Error(tr`${label}须为 1–10 之间的整数。`);
  }
  return value;
}

export const generationCount = raw => boundedGenerationCount(raw, t("每次数量"));
export const generationRepetitions = raw => boundedGenerationCount(raw, t("生成次数"));

/** Pixel presets are display choices; an existing draft keeps its exact size. */
export function generationSizes(backend, pools) {
  if (!backendCapabilities(backend).dimensions) return [];
  const sizes = pools.find(pool => pool.id === backend?.canvas_pool_id)?.sizes || [];
  return sizes.filter(size => backend.kind !== 'comfyui' || !(size.width % 8 || size.height % 8))
    .map(size => ({value: `${size.width}x${size.height}`, label: `${size.width}×${size.height}`}));
}

export function generationSizeFields(value, backend) {
  if (!value) return {};
  const match = /^([1-9][0-9]{0,4})x([1-9][0-9]{0,4})$/.exec(value);
  if (!match || Number(match[1]) > 16384 || Number(match[2]) > 16384) throw new Error(t('请选择有效的画幅尺寸。'));
  const width = Number(match[1]), height = Number(match[2]);
  if (!backendCapabilities(backend).dimensions || backend.kind === 'comfyui' && (width % 8 || height % 8)) {
    throw new Error(t('当前生图 API 不支持所选像素尺寸。'));
  }
  return {width, height};
}

/** Keep manually submitted images outside the recommendation feed. */
export function artifactPath(view, cursor = null, tags = []) {
  const query = new URLSearchParams({ limit: view === 'liked' ? '100' : '200', source: view === 'liked' ? 'all' : view === 'generate' ? 'generate' : 'roam' });
  if (view === 'liked') {
    query.set('liked', '1');
    for (const tag of new Set(tags)) query.append('tag', tag);
  }
  if (cursor) query.set('before', cursor);
  return `/api/artifacts?${query}`;
}

export function matchesLikedTags(artifact, tags = []) {
  const terms = new Set(String(artifact.source_prompts?.positive ?? artifact.positive ?? '').split(',').map(text => text.trim()).filter(Boolean));
  return tags.every(tag => terms.has(tag));
}
