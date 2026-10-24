import { t } from '../i18n/index.mjs';
import { DetailField } from './image-prompt-details';

export type RenderedPrompt = { positive: string; negative: string; preparation_id: string };
export function NaturalPrompt({ prompt }: { prompt?: RenderedPrompt | null }) {
  if (!prompt) return null;
  return <div className="image-prompt-details min-w-0" aria-label={t('自然语言提示词')}>
    <DetailField title={t('自然语言提示词')} text={prompt.positive} />
    {prompt.negative && <DetailField title={t('负向提示词')} text={prompt.negative} />}
  </div>;
}
