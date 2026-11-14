import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { build } from 'esbuild';

const root = fileURLToPath(new URL('../../', import.meta.url));
const runtimeRequire = createRequire(import.meta.url);
const React = runtimeRequire('react');
const { create, act } = runtimeRequire('react-test-renderer');
const runtime = await mkdtemp(path.join(tmpdir(), 'hxy-consumption-hook-test-'));
const bundle = path.join(runtime, 'hook.cjs');
let useCustomerConsumption;
try {
  await build({
    entryPoints: [path.join(root, 'diy-web/src/components/useCustomerConsumption.ts')],
    outfile: bundle, bundle: true, platform: 'node', format: 'cjs', jsx: 'automatic',
    plugins: [{ name: 'same-react-runtime', setup(build) {
      build.onResolve({ filter: /^react(\/.*)?$/ }, args => ({ path: runtimeRequire.resolve(args.path), external: true }));
    } }],
  });
  useCustomerConsumption = runtimeRequire(bundle).useCustomerConsumption;
} finally {
  await rm(runtime, { recursive: true, force: true });
}

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
};
const settle = async () => {
  for (let index = 0; index < 4; index++) await act(async () => { await new Promise(done => setImmediate(done)); });
};
const overview = (marker, opts = {}) => ({
  marker,
  bills: opts.bills ?? [],
  pagination: { offset: opts.offset ?? 0, limit: 20, total: opts.total ?? 0, has_more: opts.hasMore ?? false },
  savings: { status: 'verified', amount_cents: opts.amountCents ?? null, bill_count: opts.billCount ?? null, note: 'n' },
  coverage: { source: 's', store_ids: [1], history: 'returned', applied_batch_count: 1, complete: true, query_range_start: '2026-11-01T00:00:00Z', query_range_end: '2026-11-14T00:00:00Z', observed_at: '2026-11-14T00:00:00Z', coverage_gaps: null, conflict_bill_groups: 0, note: 'n' },
});
const bill = id => ({ id, source_bill_no: id, bill_type: 'service', bill_status: 'normal_settled', store_id: 1, currency: 'CNY', occurred_at: null, settled_at: null, store_price_total_cents: null, settled_total_cents: null, coupon_payment_cents: null, card_principal_debit_cents: null, card_bonus_debit_cents: null, cash_payment_cents: null, other_payment_cents: null, savings: { status: 'verified', amount_cents: 100, reason: null }, lines: [] });
let latest;
function Harness({ open, token, loader, onAuthFailure }) {
  latest = useCustomerConsumption(open, token, onAuthFailure, loader);
  return null;
}

test('delayed consumption response never leaks the previous account', async () => {
  const first = deferred();
  const second = deferred();
  const loader = token => token === 'token-a' ? first.promise : second.promise;
  let root;
  await act(async () => { root = create(React.createElement(Harness, { open: true, token: 'token-a', loader, onAuthFailure: () => {} })); });
  assert.equal(latest.data, null);
  assert.equal(latest.loading, true);

  await act(async () => { root.update(React.createElement(Harness, { open: true, token: 'token-b', loader, onAuthFailure: () => {} })); });
  assert.equal(latest.data, null);
  assert.equal(latest.loading, true);

  await act(async () => { first.resolve(overview('a')); });
  await settle();
  assert.equal(latest.data, null, 'late response from the old token must be ignored');

  await act(async () => { second.resolve(overview('b')); });
  await settle();
  assert.equal(latest.data.marker, 'b');

  await act(async () => { root.update(React.createElement(Harness, { open: false, token: 'token-b', loader, onAuthFailure: () => {} })); });
  assert.equal(latest.data, null);
  assert.equal(latest.loading, false);
  await act(async () => root.unmount());
});

test('consumption 401/session-replaced clears the customer session and results', async () => {
  const response = deferred();
  let failures = 0;
  let root;
  const loader = () => response.promise;
  await act(async () => { root = create(React.createElement(Harness, { open: true, token: 'token-expired', loader, onAuthFailure: () => { failures += 1; } })); });
  await act(async () => { response.reject({ status: 401, code: 'SESSION_REPLACED' }); });
  await settle();
  assert.equal(failures, 1);
  assert.equal(latest.data, null);
  assert.equal(latest.error, '');
  await act(async () => root.unmount());
});

test('loaded A then B: B loading/error is visible and retry actually reloads B', async () => {
  const loadedA = deferred(), failedB = deferred(), retriedB = deferred();
  let calls = [];
  const loader = token => {
    calls.push(token);
    if (token === 'token-a') return loadedA.promise;
    return calls.filter(item => item === token).length === 1 ? failedB.promise : retriedB.promise;
  };
  let root;
  await act(async () => { root = create(React.createElement(Harness, { open: true, token: 'token-a', loader, onAuthFailure: () => {} })); });
  await act(async () => { loadedA.resolve(overview('a')); });
  await settle();
  assert.equal(latest.data.marker, 'a');

  await act(async () => { root.update(React.createElement(Harness, { open: true, token: 'token-b', loader, onAuthFailure: () => {} })); });
  assert.equal(latest.data, null);
  assert.equal(latest.loading, true);
  await act(async () => { failedB.reject(new TypeError('offline')); });
  await settle();
  assert.equal(latest.data, null);
  assert.equal(latest.loading, false);
  assert.match(latest.error, /网络/);
  await act(async () => { latest.retry(); });
  assert.equal(latest.loading, true);
  await act(async () => { retriedB.resolve(overview('b-retry')); });
  await settle();
  assert.equal(latest.data.marker, 'b-retry');
  assert.equal(latest.error, '');
  await act(async () => root.unmount());
});

test('a late 401 from the old token cannot log out the new account', async () => {
  const old = deferred(), current = deferred();
  let failures = 0;
  const loader = token => token === 'token-old' ? old.promise : current.promise;
  let root;
  await act(async () => { root = create(React.createElement(Harness, { open: true, token: 'token-old', loader, onAuthFailure: () => { failures += 1; } })); });
  await act(async () => { root.update(React.createElement(Harness, { open: true, token: 'token-new', loader, onAuthFailure: () => { failures += 1; } })); });
  await act(async () => { old.reject({ status: 401, code: 'SESSION_REPLACED' }); });
  await settle();
  assert.equal(failures, 0);
  assert.equal(latest.data, null);
  await act(async () => { current.resolve(overview('new')); });
  await settle();
  assert.equal(latest.data.marker, 'new');
  await act(async () => root.unmount());
});

test('closing the profile ignores a late 401 from its in-flight request', async () => {
  const pending = deferred(); let failures = 0; let root;
  const loader = () => pending.promise;
  await act(async () => { root = create(React.createElement(Harness, { open: true, token: 'token-close', loader, onAuthFailure: () => { failures += 1; } })); });
  await act(async () => { root.update(React.createElement(Harness, { open: false, token: 'token-close', loader, onAuthFailure: () => { failures += 1; } })); });
  assert.equal(latest.loading, false);
  await act(async () => { pending.reject({ status: 401, code: 'SESSION_REPLACED' }); });
  await settle();
  assert.equal(failures, 0);
  assert.equal(latest.data, null);
  await act(async () => root.unmount());
});

test('loadMore appends the next page and updates hasMore', async () => {
  let offsets = [];
  const loader = (token, offset, limit) => {
    offsets.push(offset);
    if (offset === 0) return Promise.resolve(overview('p0', { bills: [bill('b1')], total: 2, hasMore: true }));
    return Promise.resolve(overview('p1', { bills: [bill('b2')], offset: 1, total: 2, hasMore: false }));
  };
  let root;
  await act(async () => { root = create(React.createElement(Harness, { open: true, token: 'token-p', loader, onAuthFailure: () => {} })); });
  await settle();
  assert.deepEqual(latest.bills.map(b => b.source_bill_no), ['b1']);
  assert.equal(latest.hasMore, true);

  await act(async () => { latest.loadMore(); });
  await settle();
  assert.deepEqual(offsets, [0, 1]);
  assert.deepEqual(latest.bills.map(b => b.source_bill_no), ['b1', 'b2']);
  assert.equal(latest.hasMore, false);
  assert.equal(latest.loadingMore, false);
  await act(async () => root.unmount());
});

test('a late loadMore from the old token cannot append to the new account', async () => {
  const first = deferred(), second = deferred();
  let loadMoreOffset = -1;
  const loader = (token, offset, limit) => {
    if (token === 'token-a') return offset === 0 ? first.promise : Promise.resolve(overview('a-more', { bills: [bill('a-more')] }));
    if (offset === 0) return second.promise;
    loadMoreOffset = offset;
    return Promise.resolve(overview('b-more', { bills: [bill('b-more')] }));
  };
  let root;
  await act(async () => { root = create(React.createElement(Harness, { open: true, token: 'token-a', loader, onAuthFailure: () => {} })); });
  await act(async () => { first.resolve(overview('a', { bills: [bill('a1')], total: 2, hasMore: true })); });
  await settle();
  assert.deepEqual(latest.bills.map(b => b.source_bill_no), ['a1']);

  await act(async () => { latest.loadMore(); });  // in-flight loadMore for token-a
  await act(async () => { root.update(React.createElement(Harness, { open: true, token: 'token-b', loader, onAuthFailure: () => {} })); });
  await act(async () => { second.resolve(overview('b', { bills: [bill('b1')], total: 1, hasMore: false })); });
  await settle();
  assert.deepEqual(latest.bills.map(b => b.source_bill_no), ['b1'], 'late token-a loadMore must be ignored');
  assert.equal(latest.hasMore, false);
  await act(async () => root.unmount());
});
