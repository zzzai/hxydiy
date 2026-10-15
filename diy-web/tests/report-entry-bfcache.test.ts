import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import ts from 'typescript';
import * as api from '../src/api.ts';
import * as auth from '../src/customerAuth.ts';
import * as reports from '../src/tcmReports.ts';
import * as entry from '../src/returnEntry.ts';
import * as profile from '../src/profile.ts';

// Execute the real component effects; replace only storage, browser navigation and network.
// React's renderer is not under test: hook updates are observed, not reimplemented.
const code = ts.transpileModule(fs.readFileSync(new URL('../src/components/ReportEntryPage.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const user = { id: 901, phone: '13800000001', openid: 'synthetic', nickname: 'Synthetic', is_member: false, member_type: null, balance_cents: 0 };
const token = `synthetic.${Buffer.from(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 })).toString('base64url')}.fixture`;

function subject({ consented = true, returned = true } = {}) {
  const originalFetch = globalThis.fetch;
  let finishIdentity!: (response: Response) => void;
  const identity = new Promise<Response>(resolve => { finishIdentity = resolve; });
  const paths: string[] = [];
  const writes: unknown[] = [];
  const navigations: string[] = [];
  const updates: unknown[][] = [];
  const effects: Array<() => void | (() => void)> = [];
  const listeners = new Map<string, Set<(event: unknown) => void>>();
  let cleared = 0;
  const browserEvents = {
    addEventListener(name: string, listener: (event: unknown) => void) { const set = listeners.get(name) || new Set(); set.add(listener); listeners.set(name, set); },
    removeEventListener(name: string, listener: (event: unknown) => void) { listeners.get(name)?.delete(listener); },
  };
  globalThis.fetch = (async (url: string) => {
    const path = String(url); paths.push(path);
    if (path === '/api/v1/auth/h5/me') return identity;
    if (path === '/api/v1/me/tcm-report-consent') return Response.json({ consented, version: 'tcm-report-access-v2-original', notice: 'Legacy synthetic notice' });
    if (path === '/api/v1/me/tcm-reports?limit=20&offset=0') return Response.json({ items: [{ report_id: 'SYNTHETIC-NEW', title: '检测报告', reported_at: '2026-10-14T10:00:00+08:00' }], limit: 20, offset: 0, has_more: false });
    if (path === '/api/v1/me/tcm-reports/SYNTHETIC-NEW') return Response.json({ report_id: 'SYNTHETIC-NEW', title: '检测报告', reported_at: '2026-10-14T10:00:00+08:00', physiques: [], heart_rate: null, blood_oxygen: null, moisture: null, original_report_url: 'https://yk.qianmaitcm.com/print_smart_healthcare/#/discriminateRingReport?reportId=SYNTHETIC-NEW' });
    throw new Error(`Unexpected network operation: ${path}`);
  }) as typeof fetch;
  const hooks = {
    useRef: (value: unknown) => ({ current: value }),
    useState(value: unknown) {
      const initial = typeof value === 'function' ? value() : value;
      const changes: unknown[] = []; updates.push(changes);
      return [initial, (next: unknown) => changes.push(typeof next === 'function' ? next(initial) : next)];
    },
    useEffect: (effect: () => void | (() => void)) => effects.push(effect),
  };
  const modules: Record<string, unknown> = {
    react: hooks,
    'react/jsx-runtime': { jsx: (_type: unknown, props: unknown) => props, jsxs: (_type: unknown, props: unknown) => props },
    'lucide-react': {},
    '../api': api,
    '../customerAuth': { ...auth, readCustomerAuth: () => ({ token, user }), writeCustomerAuth: (value: unknown) => writes.push(value), clearCustomerAuth: () => { cleared++; } },
    '../tcmReports': { ...reports, openOriginalReport: (url: string) => navigations.push(url) },
    '../returnEntry': entry,
    '../profile': profile,
    './RecordLoginDialog': { default: () => null },
    './ReportViewNotice': { default: () => null },
  };
  const exports: { default?: () => unknown } = {};
  const context = vm.createContext({ exports, AbortController, URLSearchParams,
    require: (name: string) => { if (!(name in modules)) throw new Error(`Unexpected component dependency: ${name}`); return modules[name]; },
    document: { ...browserEvents, visibilityState: 'visible', referrer: '' },
    window: { ...browserEvents, performance: { getEntriesByType: () => [{ type: 'back_forward' }] }, location: { search: '?store=1&view=reports', origin: 'http://synthetic.local' }, history: { state: { hxy_report_original_opened: returned, hxy_report_entry_back: false }, length: 3, replaceState() {} }, setInterval: () => 1, clearInterval() {} },
  });
  new vm.Script(code, { filename: 'ReportEntryPage.actual-component.js' }).runInContext(context);
  exports.default!();
  const cleanups = effects.map(effect => effect()).filter((cleanup): cleanup is () => void => typeof cleanup === 'function');
  return {
    paths, writes, navigations, updates,
    centerLoads: () => paths.filter(path => path.startsWith('/api/v1/me/tcm-reports?')).length,
    cleared: () => cleared,
    dispatch: (name: string, event: unknown = {}) => { for (const listener of listeners.get(name) || []) listener(event); },
    resolveIdentity: (result: typeof user | Response = user) => finishIdentity(result instanceof Response ? result : Response.json(result)),
    unmount: () => cleanups.forEach(cleanup => cleanup()),
    close: () => { cleanups.forEach(cleanup => cleanup()); globalThis.fetch = originalFetch; },
  };
}

const drain = async () => { for (let turn = 0; turn < 12; turn++) await new Promise<void>(resolve => setImmediate(resolve)); };

test('an existing verified session without DIY consent directly opens its latest report without consent calls', async () => {
  const page = subject({ consented: false, returned: false });
  try {
    page.resolveIdentity(); await drain();
    assert.deepEqual(page.navigations, ['https://yk.qianmaitcm.com/print_smart_healthcare/#/discriminateRingReport?reportId=SYNTHETIC-NEW']);
    assert.deepEqual(page.paths.filter(path => path.includes('tcm-report-consent')), []);
  } finally { page.close(); }
});

test('pending identity refresh + persisted pageshow loads the report center once without reopening the provider', async () => {
  const page = subject();
  try {
    page.dispatch('focus');
    page.dispatch('pageshow', { persisted: true });
    page.resolveIdentity(); await drain();
    assert.equal(page.paths.filter(path => path.endsWith('/auth/h5/me')).length, 1);
    assert.equal(page.centerLoads(), 1);
    assert.equal(page.writes.length, 1);
    assert.equal(page.cleared(), 0);
    assert.deepEqual(page.navigations, []);
  } finally { page.close(); }
});

for (const [name, response] of [
  ['expired session', Response.json({ detail: 'Synthetic expired identity' }, { status: 401 })],
  ['changed phone', { ...user, phone: '13800000002' }],
] as const) {
  test(`concurrent restored view rejects ${name} and never queries or opens a report`, async () => {
    const page = subject();
    try {
      page.dispatch('pageshow', { persisted: true });
      page.resolveIdentity(response); await drain();
      assert.equal(page.centerLoads(), 0);
      assert.equal(page.writes.length, 0);
      assert.equal(page.cleared(), 1);
      assert.deepEqual(page.navigations, []);
    } finally { page.close(); }
  });
}

test('logout/unmount while the shared identity refresh is pending drops late results', async () => {
  const page = subject();
  try {
    page.dispatch('pageshow', { persisted: true });
    page.unmount(); page.resolveIdentity(); await drain();
    assert.equal(page.centerLoads(), 0);
    assert.equal(page.writes.length, 0);
    assert.deepEqual(page.navigations, []);
  } finally { page.close(); }
});

test('a newer persisted restore cancels the older restore continuation', async () => {
  const page = subject();
  try {
    page.dispatch('pageshow', { persisted: true });
    page.dispatch('pageshow', { persisted: true });
    page.resolveIdentity(); await drain();
    assert.equal(page.centerLoads(), 1);
    assert.deepEqual(page.navigations, []);
  } finally { page.close(); }
});
