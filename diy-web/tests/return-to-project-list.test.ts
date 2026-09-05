import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

// Execute the actual click handler; stub only React setters and API boundaries.
const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const body = app.split('const returnToProjectListAfterSubmit = async () => {')[1].split('\n  const loadMap =')[0].replace(/\};\s*$/, '');
const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor;

function scenario(status: string, map: () => Promise<unknown>) {
  const states: string[] = [];
  const cleared: unknown[] = [];
  const entered: string[] = [];
  const messages: string[] = [];
  let drafts = 0;
  const deps = {
    serviceStatus: { occupancy_status: status }, occupancy: { status },
    session: { id: 10 }, accessToken: 'test-only', position: {}, positionCode: 'sofa-01',
    query: { storeId: 1, positionCode: 'sofa-01' },
    setBoot: (s: string) => states.push(s), setBootMessage: () => {},
    setOccupancy: () => {},
    getServicePositionMap: map, setPositions: () => {},
    resolveRequestedPosition: (positions: unknown[]) => positions[0],
    resolveActivePositionCode: (code: string) => code,
    shouldRestartStoredEntry: (s: { requestedPositionFound: boolean; hasActiveOccupancy: boolean }) => s.requestedPositionFound && !s.hasActiveOccupancy,
    clearRecord: (...args: unknown[]) => cleared.push(args),
    startFreshSelectionDraft: () => { drafts++; },
    enterPosition: async (code: string, _recovered?: boolean, startNew?: boolean) => { entered.push(`${code}:${Boolean(startNew)}`); },
    persistCurrent: () => {}, flash: (message: string) => messages.push(message),
  };
  return { run: () => new AsyncFunction(...Object.keys(deps), body)(...Object.values(deps)),
    states, cleared, entered, messages, drafts: () => drafts };
}

test('服务结束且顾客仍在原位，返回列表并创建独立的新选购', async () => {
  const s = scenario('post_service_present', async () => { throw new Error('不应先等待地图'); });
  await s.run();
  assert.equal(s.states.at(-1), 'ready');
  assert.deepEqual(s.cleared, []);
  assert.deepEqual(s.entered, ['sofa-01:true']);
  assert.equal(s.drafts(), 1);
});

test('网络失败不吞掉返回动作，并提示顾客当前只能浏览', async () => {
  const s = scenario('cleaning', async () => { throw new Error('offline'); });
  await s.run();
  assert.equal(s.states.at(-1), 'ready');
  assert.equal(s.messages.length, 1);
  assert.deepEqual(s.cleared, []);
});

test('慢网时无需等服务位查询返回就进入列表', async () => {
  let resolve!: (value: unknown) => void;
  const s = scenario('released', () => new Promise(done => { resolve = done; }));
  const pending = s.run();
  assert.equal(s.states.at(-1), 'ready');
  resolve({ positions: [] });
  await pending;
  assert.deepEqual(s.entered, []);
});

test('确认原服务位已释放才创建新选购会话', async () => {
  const s = scenario('released', async () => ({ positions: [{ occupancy: null }] }));
  await s.run();
  assert.deepEqual(s.entered, ['sofa-01:false']);
  assert.deepEqual(s.cleared, []);
});

test('未结束的已提交服务仍直接返回空白追加草稿', async () => {
  const s = scenario('waiting_service', async () => { throw new Error('must not query'); });
  await s.run();
  assert.deepEqual(s.states, ['ready']);
  assert.equal(s.drafts(), 1);
  assert.deepEqual(s.entered, []);
});
