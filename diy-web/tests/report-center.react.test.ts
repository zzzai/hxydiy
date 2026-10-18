import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import { createRequire } from 'node:module';
import ts from 'typescript';
import * as api from '../src/api.ts';
import * as auth from '../src/customerAuth.ts';
import * as reports from '../src/tcmReports.ts';
import * as entry from '../src/returnEntry.ts';
import * as profile from '../src/profile.ts';

const require = createRequire(import.meta.url);
const React = require('react');
const { create, act } = require('react-test-renderer');
const code = ts.transpileModule(fs.readFileSync(new URL('../src/components/ReportEntryPage.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const user = { id: 901, phone: '13800000001', openid: 'synthetic', nickname: 'Synthetic', is_member: false, member_type: null, balance_cents: 0 };
const token = `synthetic.${Buffer.from(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 })).toString('base64url')}.fixture`;
const report = { report_id: 'SYNTHETIC-NEW', title: '检测报告', reported_at: '2026-10-18T01:00:00Z' };
const reportUrl = 'https://yk.qianmaitcm.com/print_smart_healthcare/#/discriminateRingReport?reportId=SYNTHETIC-NEW';
const drain = async () => { for (let n = 0; n < 5; n++) await act(async () => { await new Promise(resolve => setImmediate(resolve)); }); };

// Keep React, report resolution, identity checks and URL validation real.
// Replace only HTTP, storage, navigation and the separately tested SMS dialog.
async function subject({ view = 'reports', loggedIn = true, opened = false, navigation = 'navigate', rows = [report], listStatus = 200, detailUrl = reportUrl, identity = user } = {}) {
  const originals = Object.fromEntries(['fetch', 'document', 'localStorage'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  const paths: string[] = [];
  const navigations: string[] = [];
  const storage = new Map<string, string>();
  const location = new URL(`https://synthetic.invalid/?store=1&view=${view}&seat=old&token=old`);
  const history = { state: opened ? { hxy_report_original_opened: true, hxy_report_entry_back: false } : {}, length: 1,
    replaceState(next: object, _title: string, url?: string) { this.state = next; if (url) location.href = url; },
    pushState() { assert.fail('Report entry must not insert synthetic history'); }, back() {},
  };
  const browserEvents = { addEventListener() {}, removeEventListener() {} };
  const document = { ...browserEvents, referrer: '', visibilityState: 'visible', createElement() {
    return { href: '', target: '', referrerPolicy: '', click() {
      assert.equal(this.target, '_self'); assert.equal(this.referrerPolicy, 'no-referrer');
      assert.equal(history.state.hxy_report_original_opened, true);
      navigations.push(this.href);
    } };
  } };
  Object.defineProperty(globalThis, 'document', { configurable: true, value: document });
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value), removeItem: (key: string) => storage.delete(key),
  } });
  if (loggedIn) auth.writeCustomerAuth({ token, user });
  globalThis.fetch = async (input, options = {}) => {
    const path = String(input); paths.push(path);
    assert.equal(options.method || 'GET', 'GET');
    if (path === '/api/v1/auth/h5/me') return Response.json(identity);
    if (path === '/api/v1/me/tcm-reports?limit=20&offset=0') return listStatus === 200
      ? Response.json({ items: rows, limit: 20, offset: 0, has_more: false })
      : Response.json({ detail: { code: listStatus === 401 ? 'UNAUTHORIZED' : 'TCM_UNAVAILABLE', message: 'Synthetic failure' } }, { status: listStatus });
    if (path === '/api/v1/me/tcm-reports/SYNTHETIC-NEW') return Response.json({ ...report, physiques: [], heart_rate: null, blood_oxygen: null, moisture: null, original_report_url: detailUrl });
    throw new Error(`Unexpected HTTP: ${path}`);
  };
  function Login() { return null; }
  const modules: Record<string, unknown> = {
    react: React, 'react/jsx-runtime': require('react/jsx-runtime'), 'lucide-react': require('lucide-react'),
    '../api': api, '../customerAuth': auth, '../profile': profile, '../tcmReports': reports, '../returnEntry': entry,
    './RecordLoginDialog': { default: Login },
  };
  const exports: { default?: () => unknown } = {};
  new vm.Script(code).runInContext(vm.createContext({ exports, AbortController, URLSearchParams, Error, TypeError, document,
    window: { ...browserEvents, location, history, performance: { getEntriesByType: () => [{ type: navigation }] }, setInterval: () => 1, clearInterval() {} },
    require: (name: string) => { assert.ok(name in modules, name); return modules[name]; },
  }));
  let app: any;
  await act(async () => { app = create(React.createElement(exports.default)); }); await drain();
  return {
    app, paths, navigations, location,
    center: () => app.root.findAllByProps({ className: 'report-entry-results' }).length === 1,
    text: () => JSON.stringify(app.toJSON()),
    async click(className: string) { await act(async () => app.root.findByProps({ className }).props.onClick()); await drain(); },
    async login() { await act(async () => app.root.findByType(Login).props.onSuccess({ token, user })); await drain(); },
    async changeNumber() { await act(async () => app.root.findAllByType('button').find((item: any) => item.children.includes('换个号码')).props.onClick()); await drain(); },
    async close() {
      await act(async () => app.unmount());
      for (const [key, descriptor] of Object.entries(originals)) {
        if (descriptor) Object.defineProperty(globalThis, key, descriptor);
        else Reflect.deleteProperty(globalThis, key);
      }
    },
  };
}

for (const navigation of ['navigate', 'reload', 'back_forward']) {
  test(`reports mode stays at the center on ${navigation}, including an existing opened marker`, async () => {
    const page = await subject({ navigation, opened: navigation !== 'navigate' });
    try {
      assert.deepEqual(page.navigations, []);
      assert.equal(page.center(), true);
      assert.deepEqual(page.paths, ['/api/v1/auth/h5/me', '/api/v1/me/tcm-reports?limit=20&offset=0']);
      assert.equal(page.location.search, '?store=1&view=reports');
      assert.match(page.app.root.findByProps({ className: 'report-entry-menu' }).props.href, /view=menu&page=projects/);
    } finally { await page.close(); }
  });
}

test('anonymous reports login and change-number login stay at the center until explicit View report', async () => {
  const page = await subject({ loggedIn: false });
  try {
    assert.deepEqual(page.paths, []);
    await page.login();
    assert.equal(page.center(), true); assert.deepEqual(page.navigations, []);
    await page.changeNumber();
    assert.equal(page.center(), false);
    await page.login();
    assert.equal(page.center(), true); assert.deepEqual(page.navigations, []);
    await page.click('report-entry-primary');
    assert.deepEqual(page.navigations, [reportUrl]);
    assert.equal(page.paths.filter(path => path.endsWith('/SYNTHETIC-NEW')).length, 1);
  } finally { await page.close(); }
});

for (const loggedIn of [true, false]) {
  test(`legacy return preserves direct entry and canonical mode with loggedIn=${loggedIn}`, async () => {
    const page = await subject({ view: 'return', loggedIn });
    try {
      if (!loggedIn) { assert.deepEqual(page.navigations, []); await page.login(); }
      assert.deepEqual(page.navigations, [reportUrl]);
      assert.equal(page.location.search, '?store=1&view=return');
    } finally { await page.close(); }
  });
}

for (const [navigation, expected] of [['back_forward', 0], ['reload', 1]] as const) {
  test(`legacy return ${navigation} retains its existing navigation policy`, async () => {
    const page = await subject({ view: 'return', opened: true, navigation });
    try { assert.equal(page.navigations.length, expected); assert.equal(page.location.search, '?store=1&view=return'); }
    finally { await page.close(); }
  });
}

test('empty reports stay visible without guessing a destination', async () => {
  const page = await subject({ rows: [] });
  try { assert.equal(page.center(), true); assert.match(page.text(), /暂时没有检测报告/); assert.deepEqual(page.navigations, []); }
  finally { await page.close(); }
});

test('provider errors show an error and never open a report', async () => {
  const page = await subject({ listStatus: 503 });
  try { assert.match(page.text(), /暂时不可用/); assert.deepEqual(page.navigations, []); }
  finally { await page.close(); }
});

test('changed identity stops before any report read', async () => {
  const page = await subject({ identity: { ...user, phone: '13800000002' } });
  try { assert.equal(page.center(), false); assert.deepEqual(page.paths, ['/api/v1/auth/h5/me']); assert.deepEqual(page.navigations, []); }
  finally { await page.close(); }
});

test('a clicked invalid provider URL is rejected without navigation', async () => {
  const page = await subject({ opened: true, detailUrl: 'https://invalid.example/report' });
  try { await page.click('report-entry-primary'); assert.match(page.text(), /地址暂不可用/); assert.deepEqual(page.navigations, []); }
  finally { await page.close(); }
});
