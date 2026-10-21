import test from 'node:test';
import assert from 'node:assert/strict';
import { generatedNeighbour, generatedReplacement, generatedShortcut } from '../../src/controllers/generated-viewer-controls.mjs';

const items = [{ id: 'new' }, { id: 'middle' }, { id: 'old' }];
test('newest-first navigation follows left older and right newer without wrapping', () => {
  assert.equal(generatedNeighbour(items, 'middle', 'older'), 'old');
  assert.equal(generatedNeighbour(items, 'middle', 'newer'), 'new');
  assert.equal(generatedNeighbour(items, 'old', 'older'), null);
  assert.equal(generatedNeighbour(items, 'new', 'newer'), null);
  assert.equal(generatedNeighbour(items, 'missing', 'older'), null);
});
test('removing a selected item keeps its nearest available slot or closes an empty collection', () => {
  assert.equal(generatedReplacement([items[0], items[2]], 1), 'old');
  assert.equal(generatedReplacement([items[0]], 2), 'new');
  assert.equal(generatedReplacement([], 0), null);
});
test('down never deletes or rates an image; privacy ignores repeated presses', () => {
  for (const context of [{}, { repeat: true }, { busy: true }, { blocked: true }]) {
    assert.equal(generatedShortcut('ArrowDown', context), null);
  }
  assert.equal(generatedShortcut(' '), 'privacy');
  assert.equal(generatedShortcut(' ', { repeat: true }), null);
  assert.equal(generatedShortcut('ArrowUp', { repeat: true }), 'like');
  assert.equal(generatedShortcut('ArrowLeft', { busy: true }), null);
  assert.equal(generatedShortcut(' ', { blocked: true }), null);
  assert.equal(generatedShortcut('Escape'), null);
});
