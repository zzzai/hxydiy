import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import { createRequire } from 'node:module';
import ts from 'typescript';
import * as api from '../src/api.ts';
import * as intent from '../src/visitFeedback.ts';
import * as copy from '../src/customerCopy.ts';
import * as entry from '../src/returnEntry.ts';

const require = createRequire(import.meta.url);
const React = require('react');
const { create, act } = require('react-test-renderer');
const drain = async () => { for (let n = 0; n < 5; n++) await act(async () => { await new Promise(resolve => setImmediate(resolve)); }); };
type Call = { path: string; options: RequestInit; body: Record<string, unknown> };
type Handler = (call: Call, count: number) => Response | Promise<Response>;
const tokenResponse = (token = 'synthetic-entry') => Response.json({ visit_feedback_token: token, store_id: 1, store_name: '测试门店' });
const submittedResponse = () => Response.json({ id: 1, feedback_type: 'visit_feedback', submitted: true, rating: 4, tags: [], note: '', created_at: '2026-10-23T00:00:00Z' });
const failure = (code: string, status = 400) => Response.json({ detail: { code, message: 'Synthetic error' } }, { status });

async function subject({ search = '?store=1&view=feedback', entryHandler = (() => tokenResponse()) as Handler, submitHandler = (() => submittedResponse()) as Handler, root = false } = {}) {
  const originalFetch = globalThis.fetch;
  const calls: Call[] = [];
  const loaded: string[] = [];
  const location = new URL(`https://synthetic.invalid/${search}`);
  const history = { state: null, replaceState(_state: unknown, _title: string, url: string) { location.href = new URL(url, location).href; } };
  globalThis.fetch = async (input, options = {}) => {
    const call = { path: String(input), options, body: JSON.parse(String(options.body || '{}')) }; calls.push(call);
    assert.equal(options.method, 'POST');
    assert.equal(options.credentials, 'include');
    assert.equal(new Headers(options.headers).get('Authorization'), null);
    if (call.path === '/api/v1/visit-feedback/store-entry') {
      assert.deepEqual(call.body, { store_id: 1 });
      return entryHandler(call, calls.filter(item => item.path === call.path).length);
    }
    if (call.path === '/api/v1/visit-feedback') {
      assert.deepEqual(Object.keys(call.body).sort(), ['note', 'rating', 'tags', 'visit_feedback_token']);
      assert.ok(new Headers(options.headers).get('Idempotency-Key'));
      return submitHandler(call, calls.filter(item => item.path === call.path).length);
    }
    assert.fail(`Unexpected request (no seat, cart, order or identity calls allowed): ${call.path}`);
  };
  const modules: Record<string, unknown> = {
    react: React, 'react/jsx-runtime': require('react/jsx-runtime'), 'lucide-react': require('lucide-react'),
    '../api': api, '../visitFeedback': intent, '../customerCopy': copy, '../returnEntry': entry,
    './returnEntry': entry, './styles.css': {}, 'framer-motion': { MotionConfig: ({ children }: any) => children },
  };
  function load(path: string) {
    const exports = {};
    const code = ts.transpileModule(fs.readFileSync(new URL(path, import.meta.url), 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
    }).outputText;
    new vm.Script(code).runInContext(vm.createContext({ exports, URL, URLSearchParams, Error, crypto,
      window: { location, history }, document: { getElementById: () => ({}) },
      require: (name: string) => {
        if (name === './components/StoreFeedbackPage') return load('../src/components/StoreFeedbackPage.tsx');
        if (name === './App' || name === './components/ReportEntryPage') {
          loaded.push(name); return { __esModule: true, default: () => React.createElement('p', null, name) };
        }
        assert.ok(name in modules, name); return modules[name];
      },
    }));
    return exports as { default: any };
  }
  let app: any;
  try {
    await act(async () => {
      if (root) {
        modules['react-dom/client'] = { createRoot: () => ({ render: (tree: any) => { app = create(tree); } }) };
        load('../src/main.tsx');
      } else app = create(React.createElement(load('../src/components/StoreFeedbackPage.tsx').default));
    });
    await drain();
  } catch (error) { globalThis.fetch = originalFetch; throw error; }
  const button = (label: string) => app.root.findAllByType('button').find((item: any) => item.props['aria-label'] === label || item.children.includes(label));
  return {
    app, calls, loaded, location, button,
    submissions: () => calls.filter(call => call.path === '/api/v1/visit-feedback'),
    text: () => JSON.stringify(app.toJSON()),
    async click(label: string) { await act(async () => button(label).props.onClick()); await drain(); },
    async note(value: string) { await act(async () => app.root.findByType('textarea').props.onChange({ target: { value } })); },
    async close() { await act(async () => app.unmount()); globalThis.fetch = originalFetch; },
  };
}

test('feedback root skips App initialization and never reuses stale seat or identity query parameters', async () => {
  const page = await subject({ root: true, search: '?store=1&view=feedback&seat=old&session=old&token=old&room=old' });
  try {
    assert.deepEqual(page.loaded, []);
    assert.deepEqual(page.calls.map(call => call.path), ['/api/v1/visit-feedback/store-entry']);
    assert.equal(page.location.search, '?store=1&view=feedback');
    assert.equal(page.button('提交评价').props.disabled, true);
    assert.equal(page.app.root.findAllByType('a').length, 0);
    for (let n = 1; n <= 5; n++) assert.equal(page.button(`${n}星`).props['aria-pressed'], false);
  } finally { await page.close(); }
});

for (const [view, expected] of [['menu', './App'], ['reports', './components/ReportEntryPage'], ['return', './components/ReportEntryPage']]) {
  test(`${view} root preserves its existing destination and never requests feedback access`, async () => {
    const page = await subject({ root: true, search: `?store=1&view=${view}` });
    try { assert.deepEqual(page.loaded, [expected]); assert.deepEqual(page.calls, []); }
    finally { await page.close(); }
  });
}

test('no store identifier is guessed for an invalid or missing feedback entry', async () => {
  for (const store of ['', '0', '-1', 'wrong', '1.5']) {
    const page = await subject({ search: `?view=feedback&store=${store}` });
    try { assert.deepEqual(page.calls, []); assert.match(page.text(), /重新扫描门店二维码/); assert.equal(page.button('提交评价'), undefined); }
    finally { await page.close(); }
  }
});

test('optional tags remain limited to three, rating change resets them, and note stays optional', async () => {
  const page = await subject();
  try {
    await page.click('4星');
    for (const tag of ['手法专业', '环境舒适', '沟通细致', '力度合适']) await page.click(tag);
    assert.equal(page.app.root.findAllByProps({ 'aria-pressed': true }).length, 4);
    await page.click('2星');
    assert.equal(page.app.root.findAllByProps({ 'aria-pressed': true }).length, 1);
    assert.equal(page.app.root.findByType('textarea').props.maxLength, 300);
    await page.click('提交评价');
    assert.equal(page.submissions()[0].body.rating, 2);
    assert.deepEqual(page.submissions()[0].body.tags, []);
    assert.equal(page.submissions()[0].body.note, '');
  } finally { await page.close(); }
});

test('success alone reveals clean menu and report-center links without login or seat data', async () => {
  const page = await subject();
  try {
    await page.click('4星'); await page.note('谢谢'); await page.click('提交评价');
    assert.match(page.text(), /感谢您的评价/);
    assert.deepEqual(page.app.root.findAllByType('a').map((link: any) => [link.children.join(''), link.props.href]), [
      ['返回菜单', 'https://synthetic.invalid/?store=1&view=menu&page=projects'],
      ['查看检测报告', 'https://synthetic.invalid/?store=1&view=reports'],
    ]);
    assert.equal(page.app.root.findAllByType('textarea').length, 0);
  } finally { await page.close(); }
});

test('network failure preserves the draft and key; editing attempted content starts a new intent', async () => {
  const page = await subject({ submitHandler: () => { throw new TypeError('Failed to fetch'); } });
  try {
    await page.click('4星'); await page.note('合成测试'); await page.click('提交评价');
    assert.equal(page.app.root.findByType('textarea').props.value, '合成测试');
    assert.equal(page.app.root.findAllByType('a').length, 0);
    await page.click('提交评价');
    const key = (index: number) => new Headers(page.submissions()[index].options.headers).get('Idempotency-Key');
    assert.equal(key(0), key(1));
    await page.note('修改后的合成测试'); await page.click('提交评价');
    assert.notEqual(key(1), key(2));
  } finally { await page.close(); }
});

test('synchronous double taps make one request and freeze edits until completion', async () => {
  let finish!: (response: Response) => void;
  const page = await subject({ submitHandler: () => new Promise(resolve => { finish = resolve; }) });
  try {
    await page.click('4星');
    const submit = page.button('提交评价').props.onClick;
    await act(async () => { void submit(); void submit(); }); await drain();
    assert.equal(page.submissions().length, 1);
    assert.equal(page.app.root.findByType('textarea').props.disabled, true);
    assert.equal(page.button('1星').props.disabled, true);
    await act(async () => finish(submittedResponse())); await drain();
    assert.match(page.text(), /感谢您的评价/);
  } finally { await page.close(); }
});

test('expired token renews once with the same draft and key; repeated expiry never loops', async () => {
  const page = await subject({ entryHandler: (_call, count) => tokenResponse(`entry-${count}`), submitHandler: () => failure('VISIT_FEEDBACK_TOKEN_EXPIRED', 401) });
  try {
    await page.click('4星'); await page.note('保留草稿'); await page.click('提交评价');
    assert.equal(page.submissions().length, 2);
    const [first, second] = page.submissions();
    assert.equal(first.body.visit_feedback_token, 'entry-1');
    assert.equal(second.body.visit_feedback_token, 'entry-2');
    assert.equal(new Headers(first.options.headers).get('Idempotency-Key'), new Headers(second.options.headers).get('Idempotency-Key'));
    assert.equal(second.body.note, '保留草稿');
    assert.equal(page.app.root.findByType('textarea').props.value, '保留草稿');
    assert.equal(page.app.root.findAllByType('a').length, 0);
  } finally { await page.close(); }
});

test('entry failure is explicitly retryable without requesting any other customer API', async () => {
  const page = await subject({ entryHandler: (_call, count) => count === 1 ? failure('UNAVAILABLE', 503) : tokenResponse() });
  try {
    assert.match(page.text(), /暂时无法打开评价/);
    await page.click('重试'); await page.click('4星'); await page.click('提交评价');
    assert.match(page.text(), /感谢您的评价/);
  } finally { await page.close(); }
});

test('rate limiting never renews or resends automatically and preserves customer input', async () => {
  const page = await subject({ submitHandler: () => failure('FEEDBACK_RATE_LIMITED', 429) });
  try {
    await page.click('4星'); await page.note('稍后再试'); await page.click('提交评价');
    assert.equal(page.calls.length, 2);
    assert.match(page.text(), /请稍后再试/);
    assert.equal(page.app.root.findByType('textarea').props.value, '稍后再试');
  } finally { await page.close(); }
});

test('the unselected submit handler cannot bypass required rating', async () => {
  const page = await subject();
  try { await page.click('提交评价'); assert.equal(page.submissions().length, 0); }
  finally { await page.close(); }
});

test('successful token renewal submits the retained draft once and shows success', async () => {
  const page = await subject({ entryHandler: (_call, count) => tokenResponse(`entry-${count}`), submitHandler: (_call, count) => count === 1 ? failure('VISIT_FEEDBACK_TOKEN_INVALID', 403) : submittedResponse() });
  try {
    await page.click('4星'); await page.note('保留内容'); await page.click('提交评价');
    assert.equal(page.submissions().length, 2);
    assert.equal(page.submissions()[1].body.note, '保留内容');
    assert.match(page.text(), /感谢您的评价/);
  } finally { await page.close(); }
});

test('failed renewal preserves the complete draft and the idempotency key on manual retry', async () => {
  const page = await subject({ entryHandler: (_call, count) => count === 2 ? failure('UNAVAILABLE', 503) : tokenResponse(`entry-${count}`), submitHandler: (_call, count) => count <= 2 ? failure('VISIT_FEEDBACK_TOKEN_EXPIRED', 401) : submittedResponse() });
  try {
    await page.click('4星'); await page.click('环境舒适'); await page.note('保留内容'); await page.click('提交评价');
    assert.equal(page.submissions().length, 1);
    assert.equal(page.button('4星').props['aria-pressed'], true);
    assert.equal(page.button('环境舒适').props['aria-pressed'], true);
    assert.equal(page.app.root.findByType('textarea').props.value, '保留内容');
    await page.click('提交评价');
    const requests = page.submissions();
    assert.equal(requests.length, 3);
    assert.equal(new Set(requests.map(call => new Headers(call.options.headers).get('Idempotency-Key'))).size, 1);
    assert.match(page.text(), /感谢您的评价/);
  } finally { await page.close(); }
});
