// Each open panel owns its request; closing or switching images discards it.
export function loadImagePreferenceScore(imageId, receive) {
  const controller = new AbortController();
  let active = true;
  void fetch(`/api/artifacts/${encodeURIComponent(imageId)}/preference-score`, { signal: controller.signal })
    .then(async response => {
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      return data;
    })
    .then(data => { if (active) receive(data); })
    .catch(error => {
      if (active) receive({ status: 'unavailable', score: null, love_score: null,
        score_min: null, score_max: null, reason: error.message });
    });
  return () => { active = false; controller.abort(); };
}
