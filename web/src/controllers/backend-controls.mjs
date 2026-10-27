import { t } from '../i18n/index.mjs';

export const backendDefaults = {
  comfyui: { name: 'ComfyUI', base_url: 'http://127.0.0.1:8188' },
  openai: { name: 'OpenAI Images', base_url: 'https://api.openai.com/v1' },
  gemini: { name: 'Gemini', base_url: 'https://generativelanguage.googleapis.com/v1beta' },
};

export function backendCapabilities(backend) {
  const cloud = ['openai', 'gemini'].includes(backend?.kind);
  return { negative_prompt: !cloud && !!backend?.bindings?.negative, seed: !cloud && !!backend?.bindings?.seed, dimensions: backend?.kind === 'openai' || !cloud && !!backend?.bindings?.width && !!backend?.bindings?.height, cloud, ...backend?.capabilities };
}

export function imageSeedLabel(item) {
  if (item.seed_applied !== false) return `seed ${item.seed ?? '—'}`;
  return ['openai', 'gemini'].includes(item.backend_kind) ? t('模型不支持图像种子') : t('使用工作流种子设置');
}

export function cloudConfigFields(kind, values) {
  const model = values.model.trim();
  if (!model) throw new Error(t('请填写生图模型 ID。'));
  const fields = kind === 'openai' ? ['size', 'quality'] : ['aspect_ratio', 'image_size'];
  return { model, ...Object.fromEntries(fields.filter(key => values[key]?.trim()).map(key => [key, values[key].trim()])) };
}
