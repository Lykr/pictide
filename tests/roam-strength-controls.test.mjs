import test from 'node:test';
import assert from 'node:assert/strict';
import { strongCandidateMultiplier, mergeRoamDraft, roamGenerationChanged } from '../web/src/controllers/roam-controls.mjs';

test('strong multiplier validates the configured integer range', () => {
  assert.equal(strongCandidateMultiplier('2'), 2);
  assert.equal(strongCandidateMultiplier(5), 5);
  for (const value of [0, 6, 1.5, '', null]) assert.throws(() => strongCandidateMultiplier(value));
});

test('recommendation strength preserves the window and unrelated settings drafts', () => {
  const previous = { recommendation_strength: 'standard', strong_candidate_multiplier: 2, candidate_count: 4 };
  const saved = { ...previous, recommendation_strength: 'strong' };
  assert.equal(roamGenerationChanged(previous, saved), false);
  assert.equal(roamGenerationChanged(previous, { ...previous, strong_candidate_multiplier: 5 }), false);
  assert.deepEqual(mergeRoamDraft(previous, saved, { recommendation_strength: 'standard', strong_candidate_multiplier: '3', candidate_count: '8' }, ['recommendation_strength']), {
    recommendation_strength: 'strong', strong_candidate_multiplier: '3', candidate_count: '8',
  });
});
