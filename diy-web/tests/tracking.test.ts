import assert from 'node:assert/strict';
import test from 'node:test';

import { createTracker, runTrackedOperation, type StorageLike, type TrackingEvent } from '../src/tracking.ts';

function memoryStorage(): StorageLike {
  const values = new Map<string, string>();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value); },
    removeItem: (key) => { values.delete(key); },
  };
}

test('DIY 埋点携带匿名身份、浏览会话和本次服务上下文', () => {
  const local = memoryStorage();
  const session = memoryStorage();
  const tracker = createTracker({
    localStorage: local,
    sessionStorage: session,
    randomId: () => 'fixed-id',
    now: () => new Date('2026-08-14T12:00:00.000Z'),
    send: async () => undefined,
  });
  tracker.setContext({
    store_id: 1,
    selection_session_id: 'selection-1',
    position_id: 8,
    source: 'personal_qr',
  });

  tracker.track('selection_submit_success', { revision_no: 2 }, '/diy');

  assert.deepEqual(tracker.queuedEvents(), [{
    event: 'selection_submit_success',
    page: '/diy',
    ts: '2026-08-14T12:00:00.000Z',
    data: {
      anonymous_id: 'fixed-id',
      client_session_id: 'fixed-id',
      store_id: 1,
      selection_session_id: 'selection-1',
      position_id: 8,
      source: 'personal_qr',
      revision_no: 2,
    },
  } satisfies TrackingEvent]);
});

test('埋点发送失败保留队列，成功后只移除已发送事件', async () => {
  const local = memoryStorage();
  const session = memoryStorage();
  let fail = true;
  const sent: TrackingEvent[][] = [];
  const tracker = createTracker({
    localStorage: local,
    sessionStorage: session,
    randomId: () => 'queue-id',
    now: () => new Date('2026-08-14T12:00:00.000Z'),
    send: async (events) => {
      sent.push(events);
      if (fail) throw new Error('offline');
    },
  });
  tracker.track('diy_entry_view');
  tracker.track('project_view', { project_id: 3 });

  await tracker.flush();
  assert.equal(tracker.queuedEvents().length, 2);

  fail = false;
  await tracker.flush();
  assert.equal(tracker.queuedEvents().length, 0);
  assert.equal(sent.length, 2);
  assert.equal(sent[1].length, 2);
});

test('关键操作统一记录尝试、成功和可分析的失败原因', async () => {
  const emitted: Array<{ event: string; data: Record<string, unknown> }> = [];
  const emit = (event: string, data: Record<string, unknown>) => { emitted.push({ event, data }); };

  const result = await runTrackedOperation(
    'selection_submit',
    { selection_session_id: 'selection-2' },
    async () => ({ revision_no: 3 }),
    emit,
  );
  assert.equal(result.revision_no, 3);
  assert.deepEqual(emitted.slice(0, 2), [
    { event: 'selection_submit_attempt', data: { selection_session_id: 'selection-2' } },
    { event: 'selection_submit_success', data: { selection_session_id: 'selection-2' } },
  ]);

  await assert.rejects(() => runTrackedOperation(
    'phone_login',
    {},
    async () => { throw Object.assign(new Error('验证码错误'), { code: 'SMS_CODE_INVALID', status: 400 }); },
    emit,
  ));
  assert.deepEqual(emitted[3], {
    event: 'phone_login_fail',
    data: { error_code: 'SMS_CODE_INVALID', http_status: 400 },
  });
});
