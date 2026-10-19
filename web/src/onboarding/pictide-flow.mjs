// Pure Pictide guide rules. No DOM, application controller, or API calls.
export const GUIDE_VERSION = 1;
export const GUIDE_STORAGE_KEY = 'pictide.first-run-guide.v1';
const like = value => value === 'like' || value === 'liked' || value === 1;
const readyImage = facts => Boolean(facts.imageId && facts.imageReady);
const tested = facts => facts.apiTestedRevision >= 0 && facts.apiTestedRevision === facts.apiDraftRevision;
const saved = facts => facts.apiSavedRevision >= 0 && facts.apiSavedRevision === facts.apiDraftRevision;
const feed = facts => facts.route === 'feed';
const at = (progress, stepId, context = {}) => ({ ...progress, stepId, context: { ...progress.context, ...context } });
const activeSteps = new Set(['api-config', 'api-save', 'api-ready', 'roam-start', 'roam-pending', 'roam-reveal', 'roam-feedback', 'anchors-open', 'anchors-pick', 'anchors-next', 'anchors-clear', 'cleared-next', 'liked-open', 'liked-reveal', 'finish']);

export function newProgress(facts) {
  return {
    status: 'active', stepId: facts.backendCount > 0 ? 'roam-start' : 'api-config',
    context: { firstImage: !facts.imageId, imageId: facts.imageId || null, liked: false, initialDraftRevision: facts.apiDraftRevision },
  };
}

export function restoreProgress(record) {
  if (record?.version !== GUIDE_VERSION) return null;
  if (record.status === 'done' || record.status === 'dismissed') return { status: 'idle', stepId: null, context: {} };
  if (record.status === 'active' && activeSteps.has(record.stepId)) {
    // Deliberately whitelist progress only: form values and observed facts are never stored.
    const savedContext = record.context || {};
    const context = {};
    for (const key of ['firstImage', 'imageId', 'liked', 'likedImageId', 'anchorImageId', 'clearImageId']) {
      if (['string', 'boolean', 'number'].includes(typeof savedContext[key]) || savedContext[key] === null) context[key] = savedContext[key];
    }
    return { status: 'resume', stepId: record.stepId, context };
  }
  return null;
}

export function resumeProgress(progress, facts) {
  let resumed = { ...progress, status: 'active' };
  if (facts.ready && facts.backendCount === 0 && !progress.stepId.startsWith('api-')) {
    return at(resumed, 'api-config', { initialDraftRevision: facts.apiDraftRevision });
  }
  if (progress.stepId === 'anchors-next' && !facts.anchorCount) resumed = at(resumed, 'anchors-open');
  if (progress.stepId === 'anchors-clear' && facts.anchorCount === 0) resumed = at(resumed, 'cleared-next', { clearImageId: facts.imageId });
  if (progress.stepId === 'anchors-next') resumed = at(resumed, resumed.stepId, { anchorRevision: facts.anchorRevision });
  // Revision counters belong to the current page. A resumed edit starts from
  // the live anchors, even if a previous page had already observed a change.
  if (progress.stepId === 'anchors-pick') resumed = at(resumed, 'anchors-pick', { anchorPickRevision: facts.anchorRevision });
  return advanceProgress(resumed, facts, facts);
}

export function advanceProgress(progress, facts, previous = facts) {
  if (progress.status !== 'active' || !facts.ready) return progress;
  const c = progress.context;
  if (['roam-reveal', 'roam-feedback'].includes(progress.stepId) && facts.imageId && facts.imageId === previous.imageId && like(facts.imageFeedback) && !like(previous.imageFeedback) && c.likedImageId !== facts.imageId) {
    return at(progress, progress.stepId, { likedImageId: facts.imageId });
  }
  switch (progress.stepId) {
    case 'api-config':
      if (tested(facts) && !facts.apiTestPending) return at(progress, 'api-save');
      return progress;
    case 'api-save':
      if (!tested(facts)) return at(progress, 'api-config');
      if (saved(facts) && !facts.apiSavePending && facts.backendCount > 0) return at(progress, 'api-ready');
      return progress;
    case 'roam-start':
      if (!feed(facts)) return progress;
      if (readyImage(facts)) return at(progress, 'roam-reveal', { imageId: facts.imageId });
      if (facts.waiting) return at(progress, 'roam-pending');
      return progress;
    case 'roam-pending':
      if (!feed(facts)) return progress;
      if (readyImage(facts)) return at(progress, 'roam-reveal', { imageId: facts.imageId });
      if (!facts.waiting) return at(progress, 'roam-start');
      return progress;
    case 'roam-reveal':
      if (feed(facts) && readyImage(facts) && !facts.roamPrivacy) {
        return at(progress, 'roam-feedback', { imageId: facts.imageId });
      }
      return progress;
    case 'roam-feedback':
      if (!feed(facts) || !readyImage(facts)) return progress;
      if (facts.roamPrivacy) return at(progress, 'roam-reveal', { imageId: facts.imageId });
      if (like(facts.imageFeedback) && facts.imageId === c.likedImageId) {
        return at(progress, 'anchors-open', { imageId: facts.imageId, liked: true });
      }
      if (facts.imageId !== c.imageId) return at(progress, 'roam-feedback', { imageId: facts.imageId, firstImage: false });
      return progress;
    case 'anchors-open':
      if (feed(facts) && facts.anchorOpen) return at(progress, 'anchors-pick', { anchorPickRevision: facts.anchorRevision });
      return progress;
    case 'anchors-pick':
      if (!facts.anchorCount && facts.anchorRevision !== c.anchorPickRevision) {
        return at(progress, 'anchors-pick', { anchorPickRevision: facts.anchorRevision });
      }
      if (feed(facts) && facts.anchorOpen && facts.anchorsEditable && facts.anchorCount > 0 && facts.anchorRevision !== c.anchorPickRevision) {
        return at(progress, 'anchors-next', { anchorImageId: facts.imageId, anchorRevision: facts.anchorRevision });
      }
      return progress;
    case 'anchors-next':
      if (!facts.anchorCount) return at(progress, 'anchors-pick', { anchorPickRevision: facts.anchorRevision });
      // Changing anchors rebases the image boundary; an older pending image cannot finish this step.
      if (facts.anchorRevision !== c.anchorRevision) return at(progress, 'anchors-next', { anchorImageId: facts.imageId, anchorRevision: facts.anchorRevision });
      if (feed(facts) && readyImage(facts) && facts.imageId !== c.anchorImageId) {
        return at(progress, 'anchors-clear', { clearImageId: facts.imageId });
      }
      return progress;
    case 'anchors-clear':
      if (feed(facts) && facts.anchorCount === 0 && previous.anchorCount > 0 && facts.anchorRevision !== previous.anchorRevision) {
        return at(progress, 'cleared-next', { clearImageId: facts.imageId });
      }
      return progress;
    case 'cleared-next':
      if (feed(facts) && readyImage(facts) && facts.imageId !== c.clearImageId) return at(progress, 'liked-open');
      return progress;
    case 'liked-open':
      if (facts.route === 'liked') return at(progress, 'liked-reveal');
      return progress;
    case 'liked-reveal':
      if (facts.route === 'liked' && !facts.likedLoading && (!facts.likedPrivacy || facts.likedTotal === 0)) return at(progress, 'finish');
      return progress;
    default: return progress;
  }
}

export function settleProgress(progress, facts, previous = facts) {
  // A fast image or already-revealed view may satisfy adjacent steps in one publication.
  for (let i = 0; i < activeSteps.size; i++) {
    const next = advanceProgress(progress, facts, previous);
    if (next === progress) return progress;
    progress = next;
    previous = facts;
  }
  return progress;
}

export function actProgress(progress, action, facts) {
  if (action === 'dismiss') return { status: 'idle', stepId: null, context: {} };
  if (action === 'restart' || action === 'start') return newProgress(facts);
  if (action === 'resume' && progress.status === 'resume') return resumeProgress(progress, facts);
  if (progress.status !== 'active') return progress;
  if (action === 'back-to-roam' && progress.stepId === 'api-ready') return at(progress, 'roam-start');
  if (action === 'learn-anchors' && progress.stepId === 'roam-feedback') return at(progress, 'anchors-open');
  if (action === 'skip-anchors' && progress.stepId.startsWith('anchors-')) return at(progress, 'liked-open');
  if (action === 'finish' && progress.stepId === 'finish') return { status: 'idle', stepId: null, context: {} };
  return progress;
}

const button = (label, name) => ({ label, name });
export function presentProgress(progress, facts) {
  const result = { status: progress.status, stepId: progress.stepId, title: '新手引导', messages: [], targets: [] };
  if (progress.status === 'idle') return result;
  if (progress.status === 'invite') return { ...result, messages: ['欢迎来到 Pictide，一起试试漫游？'], primary: button('带我看看', 'start'), secondary: button('自己探索', 'dismiss') };
  if (progress.status === 'resume') return { ...result, messages: ['继续上次的漫游引导？'], primary: button('继续引导', 'resume'), secondary: button('自己探索', 'dismiss') };
  const c = progress.context;
  result.title = progress.stepId.startsWith('api-') ? '生图 API' : progress.stepId === 'anchors-pick' ? '编辑锚点'
    : progress.stepId.startsWith('anchors-') ? '锚点' : progress.stepId.startsWith('liked-') || progress.stepId === 'finish' ? '喜欢' : '漫游';
  result.secondary = button('结束引导', 'dismiss');
  const show = (messages, targets, expectedRoute) => Object.assign(result, { messages, targets, expectedRoute });
  switch (progress.stepId) {
    case 'api-config':
      return show([facts.apiDraftRevision !== c.initialDraftRevision ? '填好后，测试一下连接。' : '先连一个生图服务。'], ['api.form', 'api.test'], 'settings/backend');
    case 'api-save': return show(['连接成功，保存就好。'], ['api.save'], 'settings/backend');
    case 'api-ready':
      result.primary = button('回到漫游', 'back-to-roam');
      return show(['保存好了，开始漫游吧。'], [], 'settings/backend');
    case 'roam-start': return show([c.firstImage ? '点「开始漫游」，看看第一张。' : '点「开始漫游」，继续看看。'], ['roam.start'], 'feed');
    case 'roam-pending': return show(['图片正在准备，稍等一下。'], ['roam.pending'], 'feed');
    case 'roam-reveal': return show(['图片好了，点这里关掉毛玻璃。'], ['roam.privacy'], 'feed');
    case 'roam-feedback':
      result.primary = button('先了解锚点', 'learn-anchors');
      return show([c.firstImage ? '第一张图片来了。喜欢就点个心，也可以看下一张。' : '喜欢就点个心，也可以看下一张。'], ['roam.like', 'roam.next'], 'feed');
    case 'anchors-open':
      result.secondary = button('跳过锚点', 'skip-anchors');
      return show([c.liked ? '找到喜欢的了！打开锚点，留住感兴趣的元素。' : '打开锚点，留住感兴趣的元素。'], ['anchors.trigger'], 'feed');
    case 'anchors-pick':
      result.secondary = button('跳过锚点', 'skip-anchors');
      return show([facts.anchorsEditable ? '点选标签，调整想保留的元素。' : '当前无法编辑锚点，可以先继续探索。'], [facts.anchorOpen ? 'anchors.terms' : 'anchors.trigger'], 'feed');
    case 'anchors-next':
      result.secondary = button('跳过锚点', 'skip-anchors');
      return show(['再看一张，沿着这个方向继续。'], ['roam.next'], 'feed');
    case 'anchors-clear':
      result.secondary = button('跳过锚点', 'skip-anchors');
      return show([facts.anchorOpen ? '想换个方向时，点这里清空锚点。' : '打开锚点，试试换个方向。'], [facts.anchorOpen ? 'anchors.clear' : 'anchors.trigger'], 'feed');
    case 'cleared-next': return show(['清空好了，看看新的画面吧。'], ['roam.next'], 'feed');
    case 'liked-open':
      return show([c.liked || facts.likedTotal > 0 ? '刚才喜欢的图片，也都留着呢。点「喜欢」，回去看看。' : '点「喜欢」，看看收藏图片的地方。'], ['nav.liked'], 'feed');
    case 'liked-reveal': return show(['这里也有毛玻璃，点一下就能看。'], ['liked.privacy'], 'liked');
    case 'finish':
      result.primary = button('继续漫游', 'finish');
      return show([facts.likedTotal > 0 ? '喜欢的画面，随时都能回来重看。' : '点过喜欢的图片，会收在这里。', '接下来，按你的心意漫游吧。'], ['liked.collection'], 'liked');
    default: return result;
  }
}
