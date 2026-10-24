import { t } from '../i18n/index.mjs';
import { useApplication, useModel } from '../shared/application-context';
import { Label } from './ui/label';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Checkbox } from './ui/checkbox';
import { FormSelect } from './form-select';

export function WorkflowNodeFields() {
  const { backendSettings: service } = useApplication();
  const state = useModel(service.model);
  return <div id="node-parameter-fields" hidden={state.editorMode === 'json'}>{state.nodes.map((node: any) => <fieldset key={node.id} className="node-parameter-group">
    <legend>{node.id} · {node.title}</legend><div className="node-input-grid">{node.inputs.map((input: any) => {
      const key = `${node.id}:${input.name}`, value = state.nodeDrafts[key] ?? input.value;
      const label = `${node.id} ${node.classType} ${input.name}`;
      const update = (value: unknown) => service.editNode(node, input, value);
      const error = state.nodeErrors[key];
      const props = { 'aria-label': label, 'aria-invalid': !!error };
      const long = input.kind === 'string' && (String(value).length > 100 || String(value).includes('\n'));
      return <Label key={key} className={input.kind === 'boolean' ? 'checkbox-label' : `node-input-field${long ? ' wide-node-input' : ''}`}>
        <span className="node-input-caption">{input.name}</span>
        {input.options?.length ? <FormSelect {...props} value={String(value)} onValueChange={update} options={[...new Set([value, ...input.options])].map(item => ({ value: String(item), label: String(item) }))} />
          : input.kind === 'boolean' ? <Checkbox {...props} checked={value} onCheckedChange={checked => update(checked === true)} />
          : long ? <Textarea {...props} rows={3} value={String(value)} onChange={event => update(event.target.value)} />
          : <Input {...props} type={['integer', 'number'].includes(input.kind) ? 'number' : 'text'} step={input.kind === 'integer' ? 1 : 'any'} required={['integer', 'number'].includes(input.kind)} value={String(value)} onChange={event => update(event.target.value)} />}
        {error && <span className="sr-only">{error}</span>}
      </Label>;
    })}</div>
  </fieldset>)}</div>;
}

export function WorkflowOutputs() {
  const { backendSettings: service } = useApplication();
  const state = useModel(service.model);
  return <div id="output-nodes" role="group" aria-label={t('输出节点')} className="grid w-full min-w-0 max-h-44 gap-1.5 overflow-y-auto p-1">{state.outputs.map((item: any) => <Label key={item.value}>
    <Checkbox checked={state.draft.outputs.includes(item.value)} onCheckedChange={checked => service.edit('outputs', checked ? [...state.draft.outputs, item.value] : state.draft.outputs.filter((value: string) => value !== item.value))} /><span className="min-w-0 wrap-anywhere leading-normal">{item.label}</span>
  </Label>)}</div>;
}
