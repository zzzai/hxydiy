import assert from 'node:assert/strict';
import test from 'node:test';
import { startSharedDraftPolling } from '../src/sharedDraftPolling.ts';

function clock() {
  let nextId = 0;
  const timers = new Map<number, { callback: () => void; delay: number }>();
  return {
    timers,
    setTimer: ((callback: () => void, delay: number) => {
      const id = ++nextId;
      timers.set(id, { callback, delay });
      return id as unknown as ReturnType<typeof setTimeout>;
    }) as typeof setTimeout,
    clearTimer: ((id: ReturnType<typeof setTimeout>) => { timers.delete(id as number); }) as typeof clearTimeout,
    fire: () => {
      const [id, timer] = [...timers][0];
      timers.delete(id);
      timer.callback();
    },
    delay: () => [...timers.values()][0]?.delay,
  };
}

const settle = async () => { await Promise.resolve(); await Promise.resolve(); };

test('slow shared draft request never overlaps; visibility and online resume once', async () => {
  const timers = clock();
  let available = true;
  let calls = 0;
  let finish!: () => void;
  const poller = startSharedDraftPolling({
    poll: () => { calls++; return new Promise<void>((resolve) => { finish = resolve; }); },
    canPoll: () => available,
    isTerminal: () => false,
    onTerminal: () => assert.fail('unexpected terminal'),
    intervalMs: 3000,
    ...timers,
  });
  assert.equal(calls, 1);
  assert.equal(timers.timers.size, 0);
  poller.resume();
  poller.resume();
  assert.equal(calls, 1);
  finish();
  await settle();
  assert.equal(timers.delay(), 0);
  timers.fire();
  assert.equal(calls, 2);
  available = false;
  poller.pause();
  finish();
  await settle();
  assert.equal(timers.timers.size, 0);
  available = true;
  poller.resume();
  assert.equal(calls, 3);
  poller.stop();
  finish();
  await settle();
  assert.equal(timers.timers.size, 0);
});

test('shared draft failures back off; auth expiry stops polling and late response is ignored', async () => {
  const timers = clock();
  let calls = 0;
  let terminal = 0;
  const poller = startSharedDraftPolling({
    poll: async () => { calls++; throw calls === 3 ? new Error('expired') : new Error('network'); },
    canPoll: () => true,
    isTerminal: (error) => error instanceof Error && error.message === 'expired',
    onTerminal: () => { terminal++; },
    intervalMs: 3000,
    ...timers,
  });
  await settle();
  assert.equal(timers.delay(), 6000);
  timers.fire();
  await settle();
  assert.equal(timers.delay(), 12000);
  timers.fire();
  await settle();
  assert.equal(terminal, 1);
  assert.equal(timers.timers.size, 0);
  poller.resume();
  assert.equal(calls, 3);
});

test('unmount aborts the active read and cannot apply a late result', async () => {
  const timers = clock();
  let complete!: () => void;
  let applied = 0;
  let aborted = false;
  const poller = startSharedDraftPolling({
    poll: async (signal) => {
      await new Promise<void>((resolve) => { complete = resolve; });
      aborted = signal.aborted;
      if (!signal.aborted) applied++;
    },
    canPoll: () => true,
    isTerminal: () => false,
    onTerminal: () => assert.fail('unexpected terminal'),
    ...timers,
  });
  poller.stop();
  complete();
  await settle();
  assert.equal(aborted, true);
  assert.equal(applied, 0);
  assert.equal(timers.timers.size, 0);
});
