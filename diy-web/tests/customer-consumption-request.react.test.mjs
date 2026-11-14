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
const overview = marker => ({ marker, bills: [], savings: { amount_cents: null, bill_count: null } });
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
