import assert from 'node:assert/strict';
import test from 'node:test';

let version = 0;
const freshStore = () => import(`../../src/shared/notifications.mjs?test=${++version}`);

test('repeated active failures coalesce and the visible queue stays bounded', async () => {
  const store = await freshStore();
  let changes = 0;
  const unsubscribe = store.subscribeNotifications(() => changes++);
  const id = store.notifyError('Connection failed');
  const snapshot = store.notificationSnapshot();
  store.notifyError('Connection failed');
  assert.equal(store.notificationSnapshot(), snapshot);
  assert.equal(changes, 1);
  for (const message of ['Second', 'Third', 'Fourth']) store.notify(message);
  assert.equal(store.notificationSnapshot().length, 3);
  assert(!store.notificationSnapshot().some(notice => notice.id === id));
  unsubscribe();
  store.notify('After unsubscribe');
  assert.equal(changes, 4);
});

test('an old close animation cannot remove a replacement or suppress a retry', async context => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  const store = await freshStore();
  store.notifyError('Connection failed', { id: 'connection' });
  store.dismissNotification('connection');
  assert.equal(store.notificationSnapshot()[0].open, false);
  store.notifyError('Connection failed', { id: 'connection' });
  context.mock.timers.tick(200);
  assert.equal(store.notificationSnapshot().length, 1);
  assert.equal(store.notificationSnapshot()[0].open, true);
  store.dismissNotification('connection');
  context.mock.timers.tick(200);
  assert.equal(store.notificationSnapshot().length, 0);
});

test('dynamic text and retry actions retain their current values', async () => {
  const store = await freshStore();
  assert.equal(store.notify('   '), '');
  let language = 'en', retries = 0;
  store.notifyError(() => language === 'en' ? 'Failed' : '失败', {
    action: { label: () => language === 'en' ? 'Retry' : '重试', onClick: () => retries++ },
  });
  const notice = store.notificationSnapshot()[0];
  language = 'zh';
  assert.equal(store.notificationText(notice.message), '失败');
  assert.equal(store.notificationText(notice.action.label), '重试');
  notice.action.onClick();
  assert.equal(retries, 1);
});
