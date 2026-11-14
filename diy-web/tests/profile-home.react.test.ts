import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import { createRequire } from 'node:module';
import ts from 'typescript';
import * as api from '../src/api.ts';
import * as profile from '../src/profile.ts';
import * as copy from '../src/customerCopy.ts';
import * as customerAuth from '../src/customerAuth.ts';
import * as domain from '../src/domain.ts';

const require = createRequire(import.meta.url);
const React = require('react');
const { create, act } = require('react-test-renderer');
const drain = async () => { for (let n = 0; n < 4; n++) await act(async () => { await new Promise(resolve => setImmediate(resolve)); }); };
const auth = (token = 'synthetic-a') => ({ token, user: { id: token === 'synthetic-a' ? 1 : 2, openid: 'synthetic', phone: '13000000000', nickname: '示例会员', is_member: true, member_type: 'annual', member_expire_at: '2099-08-19T00:00:00Z', balance_cents: 0 } });
const record = (id = 'record-1', pending = true) => ({ id, status: 'confirmed', items: [{ project_id: 1, name: '现煮草本泡', quantity: 1 }], submitted_at: '2026-10-24T04:00:00Z', service_completed_at: '2026-10-24T05:00:00Z', can_evaluate: true, evaluated: !pending, occupancy_status: 'released', store_total_cents: 2990, member_total_cents: 2590 });
const textOf = (node: any): string => typeof node === 'string' ? node : (node.children || []).map(textOf).join('');

async function subject({ sessions = [record()], load = undefined as undefined | ((token: string) => Promise<any[]>), save = async () => ({ id: 1 }), consumption = null as any, membership = null as any } = {}) {
  const saved: unknown[] = [], scroll: string[] = [], coupons: string[] = [];
  let rows = sessions;
  const storage = { getItem: () => null, setItem() {}, removeItem() {} };
  const modules: Record<string, unknown> = {
    react: React, 'react/jsx-runtime': require('react/jsx-runtime'), 'lucide-react': require('lucide-react'), 'qrcode.react': { QRCodeSVG: () => null },
    '../api': { ...api, getMySelectionSessions: (token: string) => load ? load(token) : Promise.resolve(rows), getMyCoupons: async (token: string) => { coupons.push(token); return []; }, submitCustomerFeedback: async (...args: any[]) => { saved.push(args); const result = await save(); rows = rows.map(row => row.id === args[0] ? { ...row, evaluated: true } : row); return result; } },
    '../profile': profile, '../domain': domain, '../customerCopy': copy,
    '../guestCoupon': { bindPendingGuestCoupons: async () => undefined, GUEST_COUPON_KEY_PREFIX: 'hxy_coupon_guest_' },
    '../customerAuth': { ...customerAuth, clearCustomerAuth() {} },
    './MembershipBanner': { __esModule: true, default: () => null }, './useCustomerMembership': { useCustomerMembership: () => membership ?? { data: null, loading: false, error: '', retry() {} } }, './useCustomerConsumption': { useCustomerConsumption: () => consumption ?? { data: null, bills: [], loading: false, loadingMore: false, hasMore: false, error: '', retry() {}, loadMore() {} } }, './MyReports': { __esModule: true, default: () => React.createElement('p', null, '报告页面') },
    './CustomerReturnTools': { ProfileReturnTools: () => null, ReturnDialog: ({ panel }: any) => panel ? React.createElement('div', { role: 'dialog', 'aria-label': panel === 'save' ? '服务号入口' : panel === 'tuesday' ? '超级星期二' : '联系门店' }, panel) : null },
  };
  function loadComponent(name: string): any {
    const exports = {};
    const compiled = ts.transpileModule(fs.readFileSync(new URL(`../src/components/${name}.tsx`, import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
    new vm.Script(compiled).runInContext(vm.createContext({ exports, URL, URLSearchParams, Error, console, localStorage: storage,
      window: { location: new URL('https://synthetic.invalid/?store=1&view=menu&page=projects'), confirm: () => false, setTimeout, clearTimeout, setInterval, clearInterval, matchMedia: () => ({ matches: true }) },
      require: (path: string) => { if (path.endsWith('.css')) return {}; if (path === './FeedbackDialog') return { __esModule: true, default: loadComponent('FeedbackDialog') }; assert.ok(path in modules, path); return modules[path]; },
    }));
    return (exports as any).default;
  }
  const Profile = loadComponent('ProfilePage');
  let currentAuth = auth();
  let app: any;
  const props = () => ({ open: true, auth: currentAuth, onClose() {}, onAuthChange() {}, storeId: 1 });
  await act(async () => { app = create(React.createElement(Profile, props()), { createNodeMock: (element: any) => element.props.id === 'profile-records' ? { scrollIntoView: () => scroll.push('scroll'), focus: () => scroll.push('focus') } : null }); });
  await drain();
  const button = (label: string) => app.root.findAllByType('button').find((node: any) => node.props['aria-label'] === label || (node.props['aria-label'] || '').startsWith(label + '，') || textOf(node) === label);
  return { app, saved, scroll, coupons, button, text: () => JSON.stringify(app.toJSON()),
    async click(label: string) { const target = button(label); assert.ok(target, `Missing action: ${label}`); await act(async () => target.props.onClick({ stopPropagation() {} })); await drain(); },
    async changeIdentity(token: string) { currentAuth = auth(token); await act(async () => app.update(React.createElement(Profile, props()))); await drain(); },
    async close() { await act(async () => app.unmount()); },
  };
}

test('pending feedback moves focus to a visible filtered record list', async () => {
  const page = await subject({ sessions: [record(), record('done', false)] });
  try { await page.click('待评价'); assert.ok(page.scroll.includes('scroll')); assert.ok(page.scroll.includes('focus')); assert.ok(page.button('去评价')); assert.equal(page.app.root.findAllByProps({ className: 'profile-record-main' }).length, 1); }
  finally { await page.close(); }
});

test('profile does not present a capped list as lifetime savings or a complete order count', async () => {
  const page = await subject({ sessions: Array.from({ length: 50 }, (_, i) => record(`r-${i}`, i === 0)) });
  try { await page.click('服务记录'); assert.doesNotMatch(page.text(), /累计会员省|下单记录/); assert.match(page.text(), /最近50条/); assert.equal(page.app.root.findAllByProps({ className: 'profile-record-main' }).length, 3); assert.deepEqual(page.coupons, ['synthetic-a']); }
  finally { await page.close(); }
});

test('an empty pending filter gives an explicit result and moves focus', async () => {
  const page = await subject({ sessions: [record('done', false)] });
  try { await page.click('待评价'); assert.match(page.text(), /目前没有待评价的服务/); assert.ok(page.scroll.includes('focus')); }
  finally { await page.close(); }
});

test('feedback failures stay visible and preserve the written suggestion for retry', async () => {
  let attempts = 0;
  const page = await subject({ save: async () => { if (++attempts === 1) throw new Error('网络暂时不稳定'); return { id: 1 }; } });
  try {
    await page.click('待评价'); await page.click('去评价'); await page.click('4星');
    await act(async () => page.app.root.findByType('textarea').props.onChange({ target: { value: '合成测试建议' } }));
    await page.click('提交评价'); assert.match(page.text(), /网络暂时不稳定/); assert.equal(page.app.root.findByType('textarea').props.value, '合成测试建议');
    await page.click('提交评价'); assert.match(page.text(), /感谢您的评价/); assert.equal(page.saved.length, 2);
  } finally { await page.close(); }
});

test('rapid duplicate feedback clicks create only one submission', async () => {
  let finish!: (value: { id: number }) => void;
  const page = await subject({ save: () => new Promise(resolve => { finish = resolve; }) });
  try {
    await page.click('待评价'); await page.click('去评价'); await page.click('5星');
    const submit = page.button('提交评价').props.onClick;
    await act(async () => { submit(); submit(); }); assert.equal(page.saved.length, 1);
    await act(async () => finish({ id: 1 })); await drain(); assert.match(page.text(), /感谢您的评价/);
  } finally { await page.close(); }
});

test('changing account immediately hides the previous account record and open feedback', async () => {
  const page = await subject({ load: token => token === 'synthetic-a' ? Promise.resolve([record('private-a')]) : new Promise(() => {}) });
  try { await page.click('待评价'); await page.click('去评价'); await page.changeIdentity('synthetic-b'); assert.equal(page.app.root.findAllByType('textarea').length, 0); assert.equal(page.app.root.findAllByProps({ className: 'profile-record-main' }).length, 0); }
  finally { await page.close(); }
});


test('a record loading failure can be retried without losing the current account', async () => {
  let attempt = 0;
  const page = await subject({ load: async () => { if (++attempt === 1) throw new Error('服务记录暂时未能加载'); return [record()]; } });
  try {
    assert.match(page.text(), /服务记录暂时未能加载/); await page.click('重新加载'); await page.click('服务记录');
    assert.equal(page.app.root.findAllByProps({ className: 'profile-record-main' }).length, 1);
    assert.doesNotMatch(page.text(), /服务记录暂时未能加载/);
  } finally { await page.close(); }
});

test('a late submission from the old account cannot mark the new account record as evaluated', async () => {
  let finish!: (value: { id: number }) => void;
  const page = await subject({ load: async token => [{ ...record(token), items: [{ project_id: 1, name: token === 'synthetic-a' ? '前一个账号服务' : '新账号服务', quantity: 1 }] }], save: () => new Promise(resolve => { finish = resolve; }) });
  try {
    await page.click('待评价'); await page.click('去评价'); await page.click('5星');
    await act(async () => { page.button('提交评价').props.onClick(); });
    await page.changeIdentity('synthetic-b');
    await act(async () => finish({ id: 1 })); await drain(); await page.click('服务记录');
    assert.match(page.text(), /新账号服务/); assert.doesNotMatch(page.text(), /前一个账号服务|感谢您的评价/);
    assert.ok(page.button('去评价')); assert.equal(page.saved.length, 1);
  } finally { await page.close(); }
});


test('home keeps records collapsed and all six shortcuts work without showing record rows', async () => {
  const page = await subject();
  try {
    for (const action of ['服务记录', '待评价', '检测报告', '服务号', '联系门店', '超级星期二']) assert.ok(page.button(action));
    assert.equal(page.app.root.findAllByProps({ className: 'profile-record-main' }).length, 0);
    await page.click('服务记录'); assert.equal(page.app.root.findAllByProps({ className: 'profile-record-main' }).length, 1);
    await page.click('收起'); assert.equal(page.app.root.findAllByProps({ className: 'profile-record-main' }).length, 0);
    await page.click('服务号'); assert.equal(page.app.root.findAllByProps({ 'aria-label': '服务号入口' }).length, 1);
    await page.click('超级星期二'); assert.equal(page.app.root.findAllByProps({ 'aria-label': '超级星期二' }).length, 1);
    assert.equal(page.app.root.findAllByProps({ className: 'profile-record-main' }).length, 0);
  } finally { await page.close(); }
});


function makeConsumption(hasMore: boolean) {
  const bills = [
    { id: 1, source_bill_no: 'SYN-V1', bill_type: 'service', bill_status: 'normal_settled', store_id: 1, currency: 'CNY', occurred_at: '2026-11-01T00:00:00Z', settled_at: null, store_price_total_cents: 30000, settled_total_cents: 24000, coupon_payment_cents: 9000, card_principal_debit_cents: 15000, card_bonus_debit_cents: 0, cash_payment_cents: 0, other_payment_cents: 0, savings: { status: 'verified', amount_cents: 6000, reason: null }, lines: [{ description: '合成服务', quantity: 1, store_price_cents: 30000, settled_cents: 24000 }] },
    { id: 2, source_bill_no: 'SYN-UNKNOWN', bill_type: 'service', bill_status: 'normal_settled', store_id: 1, currency: 'CNY', occurred_at: '2026-11-02T00:00:00Z', settled_at: null, store_price_total_cents: 11900, settled_total_cents: 7900, coupon_payment_cents: 0, card_principal_debit_cents: 7900, card_bonus_debit_cents: 0, cash_payment_cents: 0, other_payment_cents: 0, savings: { status: 'unknown', amount_cents: null, reason: 'payment_breakdown_unknown_or_incomplete' }, lines: [{ description: '合成服务', quantity: 1, store_price_cents: 11900, settled_cents: 7900 }] },
  ];
  return {
    data: {
      coverage: { source: 'meiguanjia_export', store_ids: [1], history: 'returned', applied_batch_count: 1, complete: true, query_range_start: '2026-11-01T00:00:00Z', query_range_end: '2026-11-14T00:00:00Z', observed_at: '2026-11-14T00:00:00Z', coverage_gaps: null, conflict_bill_groups: 0, note: 'n' },
      bills,
      pagination: { offset: 0, limit: 20, total: 2, has_more: hasMore },
      savings: { status: 'verified', amount_cents: 6000, bill_count: 1, note: 'n' },
      generated_at: '2026-11-14T00:00:00Z', read_only: true,
    },
    bills, loading: false, loadingMore: false, hasMore, error: '', retry() {}, loadMore() {},
  };
}

test('consumption history shows verified/unknown savings and coverage without misleading zero', async () => {
  const page = await subject({ consumption: makeConsumption(false) });
  try {
    const text = page.text();
    assert.match(text, /累计消费优惠/);
    assert.match(text, /优惠未核实/);
    assert.match(text, /统计覆盖期/);
    assert.doesNotMatch(text, /加载更多/);
  } finally { await page.close(); }
});

test('consumption history renders a load-more button when more pages exist', async () => {
  const page = await subject({ consumption: makeConsumption(true) });
  try {
    assert.match(page.text(), /加载更多/);
    assert.ok(page.app.root.findByProps({ className: 'profile-consumption-more' }));
  } finally { await page.close(); }
});


function memberBill(id: number, overrides: any = {}) {
  return {
    id, source_bill_no: `SYN-${id}`, bill_type: 'service', bill_status: 'normal_settled', store_id: 1, currency: 'CNY',
    occurred_at: '2026-11-01T00:00:00Z', settled_at: null, store_price_total_cents: 24000, settled_total_cents: 24000,
    coupon_payment_cents: 0, card_principal_debit_cents: 24000, card_bonus_debit_cents: 0, cash_payment_cents: 0, other_payment_cents: 0,
    savings: { status: 'verified', amount_cents: 6000, reason: null },
    lines: [{ description: '合成服务', quantity: 1, store_price_cents: 24000, settled_cents: 24000 }],
    ...overrides,
  };
}

function memberConsumption(bills: any[], opts: any = {}) {
  const complete = 'complete' in opts ? opts.complete : true;
  const rangeStart = 'rangeStart' in opts ? opts.rangeStart : '2026-11-01T00:00:00Z';
  const rangeEnd = 'rangeEnd' in opts ? opts.rangeEnd : '2026-11-14T00:00:00Z';
  return {
    data: {
      coverage: { source: 'meiguanjia_export', store_ids: [1], history: 'returned', applied_batch_count: 1, complete, query_range_start: rangeStart, query_range_end: rangeEnd, observed_at: '2026-11-14T00:00:00Z', coverage_gaps: opts.coverageGaps ?? null, conflict_bill_groups: opts.conflictGroups ?? 0, note: 'n' },
      bills,
      pagination: { offset: 0, limit: 20, total: bills.length, has_more: opts.hasMore ?? false },
      savings: { status: opts.savingsStatus ?? 'verified', amount_cents: opts.savingsAmount ?? null, bill_count: opts.savingsAmount != null ? 1 : null, note: 'n' },
      generated_at: '2026-11-14T00:00:00Z', read_only: true,
    },
    bills, loading: false, loadingMore: false, hasMore: opts.hasMore ?? false, error: '', retry() {}, loadMore() {},
  };
}

test('member source money shows exact cents (1499 => ¥14.99, never ¥15.0)', async () => {
  const b = memberBill(1, { settled_total_cents: 1499, savings: { status: 'verified', amount_cents: 1499, reason: null }, lines: [{ description: '合成服务', quantity: 1, store_price_cents: 1499, settled_cents: 1499 }] });
  const page = await subject({ consumption: memberConsumption([b], { savingsAmount: 1499 }) });
  try {
    const text = page.text();
    assert.match(text, /¥14\.99/);
    assert.doesNotMatch(text, /¥15\.0/);
  } finally { await page.close(); }
});

test('non-CNY member amounts never use the yuan symbol', async () => {
  const b = memberBill(1, { currency: 'USD', settled_total_cents: 1499, savings: { status: 'unknown', amount_cents: null, reason: 'currency=USD_no_conversion_evidence' }, lines: [{ description: '合成服务', quantity: 1, store_price_cents: 1499, settled_cents: 1499 }] });
  const page = await subject({ consumption: memberConsumption([b], { savingsAmount: null, savingsStatus: 'unverified' }) });
  try {
    const text = page.text();
    assert.match(text, /USD 14\.99/);
    assert.doesNotMatch(text, /¥14\.99/);
  } finally { await page.close(); }
});

test('null savings stays unverified and is never rendered as zero', async () => {
  const b = memberBill(1, { savings: { status: 'unknown', amount_cents: null, reason: 'payment_breakdown_unknown_or_incomplete' } });
  const page = await subject({ consumption: memberConsumption([b], { savingsAmount: null, savingsStatus: 'unverified' }) });
  try {
    const text = page.text();
    assert.match(text, /优惠未核实/);
    assert.doesNotMatch(text, /¥0\.00/);
  } finally { await page.close(); }
});

test('coverage with declared gaps is visibly incomplete', async () => {
  const page = await subject({ consumption: memberConsumption([memberBill(1)], { complete: false, coverageGaps: true }) });
  try {
    assert.match(page.text(), /存在缺失，覆盖不完整/);
  } finally { await page.close(); }
});

test('disjoint coverage shows incomplete without fabricating a gap', async () => {
  const page = await subject({ consumption: memberConsumption([memberBill(1)], { complete: false, coverageGaps: false }) });
  try {
    assert.match(page.text(), /覆盖不完整/);
    assert.doesNotMatch(page.text(), /存在缺失/);
  } finally { await page.close(); }
});

test('a zero balance against an active stored card shows a display-only review note', async () => {
  const membership = {
    data: {
      identity: { is_member: true, member_type: 'stored', member_expire_at: null, note: 'n' },
      cards: [{ id: 1, card_type: 'stored', card_type_label: '储值会员卡', status: 'active', usable: true, store_id: 1, store_name: '紫薇壹号店', started_at: '2026-01-01T00:00:00Z', expires_at: null, source: 'meiguanjia_export', observed_at: '2026-11-09T00:00:00Z', balance: { status: 'observed', amount_cents: 0, principal_cents: null, bonus_cents: null, real_time: false, observed_at: '2026-11-10T00:00:00Z', split: 'unverified', semantics: 'eligible_applied_balance_observation_total_not_principal', evidence: 'balance_snapshot', reconciliation: 'zero_balance_against_active_card_review', original: { amount_cents: 15000, observed_at: '2026-11-09T00:00:00Z' } }, benefits: [], benefits_note: 'n' }],
      card_count: 1,
      coverage: { source: 'meiguanjia_export', store_ids: [1], card_snapshot: 'returned', history: 'unverified', history_reason: 'n', as_of: '2026-11-09T00:00:00Z' },
      consumption: { status: 'unverified', amount_cents: null, bill_count: null, coverage: null, label: '未核实', note: 'n' },
      savings: { status: 'unverified', amount_cents: null, coverage: null, label: '累计消费优惠未核实', note: 'n' },
      generated_at: '2026-11-14T00:00:00Z', read_only: true,
    },
    loading: false, error: '', retry() {},
  };
  const page = await subject({ membership });
  try {
    assert.match(page.text(), /余额观测为 0，状态待门店核实/);
    assert.match(page.text(), /状态待门店核实/);
    assert.doesNotMatch(page.text(), /· 当前可用/);
  } finally { await page.close(); }
});


test('unknown coverage (complete null) is visibly unknown, not complete', async () => {
  const page = await subject({ consumption: memberConsumption([memberBill(1)], { complete: null }) });
  try {
    assert.match(page.text(), /覆盖未核实/);
    assert.doesNotMatch(page.text(), /覆盖完整/);
  } finally { await page.close(); }
});

test('missing coverage dates render unknown dates even when bills are empty', async () => {
  const page = await subject({ consumption: memberConsumption([], { complete: null, rangeStart: null, rangeEnd: null }) });
  try {
    assert.match(page.text(), /统计覆盖期：/);
    assert.match(page.text(), /未记录/);
    assert.match(page.text(), /覆盖未核实/);
    assert.doesNotMatch(page.text(), /覆盖完整/);
  } finally { await page.close(); }
});
