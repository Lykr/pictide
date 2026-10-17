import test from 'node:test';
import assert from 'node:assert/strict';
import { artifactPath, matchesLikedTags } from '../web/src/controllers/generation-controls.mjs';
import { applyArtifactPage } from '../web/src/controllers/history-controls.mjs';

test('likes retain exact multi-tag and cursor values without leaking filters to generation', () => {
  const tags = ['black hair', 'glasses', 'black hair', '窗边 & 日光'];
  const query = new URL(artifactPath('liked', 'cursor ?&', tags), 'http://localhost').searchParams;
  assert.deepEqual(query.getAll('tag'), ['black hair', 'glasses', '窗边 & 日光']);
  assert.equal(query.get('before'), 'cursor ?&');
  assert.equal(query.get('liked'), '1');
  for (const view of ['generate', 'feed']) {
    assert.deepEqual(new URL(artifactPath(view, null, tags), 'http://localhost').searchParams.getAll('tag'), []);
  }
});

test('local feedback updates match complete positive fragments using AND', () => {
  const image = {positive:' black hair, glasses, black hair, sitting by a window ', negative:'blurry'};
  assert.equal(matchesLikedTags(image, ['black hair','glasses']), true);
  assert.equal(matchesLikedTags(image, ['hair']), false);
  assert.equal(matchesLikedTags(image, ['black hair','blurry']), false);
  assert.equal(matchesLikedTags(image, ['sitting by a window']), true);
});

test('global counts never overwrite filtered pagination totals', () => {
  const store = {artifactRevision:0, likedTags:['glasses'], likedArtifacts:[], generatedArtifacts:[], artifacts:[], pages:{liked:{loadedMore:false}, generate:{loadedMore:false}, feed:{loadedMore:false}}};
  applyArtifactPage(store,'liked',{revision:0,artifacts:[{id:'match'}],total:2,has_more:true,next_cursor:'match',counts:{liked:99}});
  assert.equal(store.pages.liked.total,2);
  assert.equal(store.pages.liked.hasMore,true);
  applyArtifactPage(store,'generate',{revision:0,artifacts:[],total:0,counts:{liked:99}});
  assert.equal(store.pages.liked.total,2);
});
