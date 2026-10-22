import { Children, isValidElement, type ReactNode } from 'react';
import { t } from '../i18n/index.mjs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';

type Props = { id?: string; value: string; onValueChange: (value: string) => void; children?: ReactNode; options?: { value: string; label: string }[]; disabled?: boolean; required?: boolean; size?: 'sm' | 'default'; 'aria-label'?: string; 'data-tooltip'?: string };
/** A controlled shared Select; option children are data, never hidden controls. */
export function FormSelect({ id, value, onValueChange, children, options, disabled, required, size, ...props }: Props) {
  const items = options ?? Children.toArray(children).filter(isValidElement).map(child => {
    const option = child.props as { value: string; children: ReactNode };
    return { value: option.value, label: option.children };
  });
  return <Select value={value || '__empty__'} onValueChange={next => onValueChange(next === '__empty__' ? '' : next)} disabled={disabled} required={required}>
    <SelectTrigger id={id} className="w-full min-w-0" size={size} {...props}><SelectValue placeholder={t('选择')} /></SelectTrigger>
    <SelectContent position="popper" align="start">{items.map(item => <SelectItem key={item.value} value={item.value || '__empty__'}>{item.label}</SelectItem>)}</SelectContent>
  </Select>;
}
