import test from 'node:test';
import assert from 'node:assert/strict';
import { backendCapabilities, cloudConfigFields, imageSeedLabel } from '../web/src/controllers/backend-controls.mjs';

test('cloud config omits empty optional values and excludes the other protocol fields', () => {
  assert.deepEqual(cloudConfigFields('openai', { model:' image-model ', size:'', quality:'high', image_size:'1K' }), { model:'image-model', quality:'high' });
  assert.deepEqual(cloudConfigFields('gemini', { model:'image-model', size:'1024x1024', aspect_ratio:' 4:3 ' }), { model:'image-model', aspect_ratio:'4:3' });
  assert.throws(() => cloudConfigFields('gemini', {model:' '}));
});

test('cloud capabilities do not inherit workflow bindings and historical seed hints retain meaning', () => {
  assert.deepEqual(backendCapabilities({kind:'openai', bindings:{negative:{}, seed:{}}}), {negative_prompt:false,seed:false,cloud:true});
  assert.equal(backendCapabilities({kind:'comfyui', bindings:{negative:{},seed:{}}}).seed, true);
  assert.equal(imageSeedLabel({seed_applied:false, backend_kind:'gemini'}), '模型不支持图像种子');
  assert.equal(imageSeedLabel({seed_applied:false}), '使用工作流种子设置');
});
