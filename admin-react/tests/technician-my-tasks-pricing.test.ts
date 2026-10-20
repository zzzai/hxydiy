import assert from 'node:assert/strict';
import test from 'node:test';
import {
  technicianPriceLabel,
  technicianPricedItemRows,
  technicianPriceMode,
  technicianPriceModeLabel,
  technicianPriceTotalValue,
  technicianPricingSummary,
} from '../src/technician/technicianMobile.ts';

const items = [
  { id: 1, type: 'project', name: '舒享精油 SPA', quantity: 1 },
  { id: 2, type: 'project', name: '草本泡脚', quantity: 2 },
];

const lines = [
  { line_index: 0, name: '舒享精油 SPA', quantity: 1, store_line_total_cents: 19900, member_line_total_cents: 15900, group_line_total_cents: 14000 },
  { line_index: 1, name: '草本泡脚', quantity: 2, store_line_total_cents: 3960, member_line_total_cents: 3160, group_line_total_cents: 2800 },
];

function rendered(rows: ReturnType<typeof technicianPricedItemRows>, total: ReturnType<typeof technicianPriceTotalValue>, summary: string): string {
  return JSON.stringify({ rows, total, summary });
}

test('会员价订单逐项与合计只显示会员价', () => {
  const pricing = { applied_price_type: 'member' as const, store_total_cents: 23860, member_total_cents: 19060, lines };
  const rows = technicianPricedItemRows(items, pricing);
  assert.deepEqual(rows.map((row) => [row.name, row.amount_cents, row.pending_label]), [
    ['舒享精油 SPA', 15900, null],
    ['草本泡脚', 3160, null],
  ]);
  const total = technicianPriceTotalValue('member', pricing);
  assert.deepEqual(total, { amount_cents: 19060, pending_label: null });
  assert.equal(rows.reduce((sum, row) => sum + (row.amount_cents ?? 0), 0), total.amount_cents);
  const summary = technicianPricingSummary(pricing);
  assert.equal(summary, '会员价 ¥190.60');
  assert.doesNotMatch(rendered(rows, total, summary), /门店|团购|非会员|238\.60|23860/);
});

test('门店价订单逐项与合计只显示门店价', () => {
  const pricing = { applied_price_type: 'store' as const, store_total_cents: 23860, member_total_cents: 19060, lines };
  const rows = technicianPricedItemRows(items, pricing);
  assert.deepEqual(rows.map((row) => [row.name, row.amount_cents, row.pending_label]), [
    ['舒享精油 SPA', 19900, null],
    ['草本泡脚', 3960, null],
  ]);
  const total = technicianPriceTotalValue('store', pricing);
  assert.deepEqual(total, { amount_cents: 23860, pending_label: null });
  assert.equal(rows.reduce((sum, row) => sum + (row.amount_cents ?? 0), 0), total.amount_cents);
  const summary = technicianPricingSummary(pricing);
  assert.equal(summary, '门店价 ¥238.60');
  assert.doesNotMatch(rendered(rows, total, summary), /会员|团购|非会员|190\.60|19060|15900|3160/);
});

test('团购价订单有团购金额时逐项与合计只显示团购价', () => {
  const pricing = { applied_price_type: 'group' as const, store_total_cents: 23860, member_total_cents: 19060, group_total_cents: 16800, lines };
  const rows = technicianPricedItemRows(items, pricing);
  assert.deepEqual(rows.map((row) => [row.name, row.amount_cents, row.pending_label]), [
    ['舒享精油 SPA', 14000, null],
    ['草本泡脚', 2800, null],
  ]);
  const total = technicianPriceTotalValue('group', pricing);
  assert.deepEqual(total, { amount_cents: 16800, pending_label: null });
  assert.equal(rows.reduce((sum, row) => sum + (row.amount_cents ?? 0), 0), total.amount_cents);
  const summary = technicianPricingSummary(pricing);
  assert.equal(summary, '团购价 ¥168');
  assert.doesNotMatch(rendered(rows, total, summary), /会员|门店|非会员|19060|23860|15900|19900/);
});

test('团购价订单缺少团购金额时显示待确认，不误用会员价或门店价', () => {
  const withoutGroupLines = lines.map(({ group_line_total_cents, ...rest }) => rest);
  const pricing = { applied_price_type: 'group' as const, store_total_cents: 23860, member_total_cents: 19060, lines: withoutGroupLines };
  const rows = technicianPricedItemRows(items, pricing);
  assert.deepEqual(rows.map((row) => [row.name, row.amount_cents, row.pending_label]), [
    ['舒享精油 SPA', null, '团购价待确认'],
    ['草本泡脚', null, '团购价待确认'],
  ]);
  const total = technicianPriceTotalValue('group', pricing);
  assert.deepEqual(total, { amount_cents: null, pending_label: '团购价待确认' });
  const summary = technicianPricingSummary(pricing);
  assert.equal(summary, '团购价待确认');
  assert.doesNotMatch(rendered(rows, total, summary), /¥|会员价|门店价/);
});

test('缺失或未知 applied_price_type 时不显示误导性金额', () => {
  const pricing = { store_total_cents: 23860, member_total_cents: 19060, lines };
  assert.equal(technicianPriceMode(pricing), 'unknown');
  assert.equal(technicianPriceModeLabel('unknown'), '价格类型待确认');
  const rows = technicianPricedItemRows(items, pricing);
  assert.deepEqual(rows.map((row) => [row.amount_cents, row.pending_label]), [
    [null, null],
    [null, null],
  ]);
  const total = technicianPriceTotalValue('unknown', pricing);
  assert.deepEqual(total, { amount_cents: null, pending_label: null });
  const summary = technicianPricingSummary(pricing);
  assert.equal(summary, '价格类型待确认');
  assert.doesNotMatch(rendered(rows, total, summary), /¥|会员价|门店价|团购价/);
});

test('无 pricing 时只回退项目名，不把缺失价格伪造成 0', () => {
  const rows = technicianPricedItemRows(items, null);
  assert.deepEqual(rows.map((row) => [row.name, row.amount_cents, row.pending_label]), [
    ['舒享精油 SPA', null, null],
    ['草本泡脚', null, null],
  ]);
  assert.equal(technicianPricingSummary(null), '');
  assert.equal(technicianPriceLabel(rows[0].amount_cents), '—');
});

test('pricing 存在但缺少 lines 时仍回退项目名，合计口径不变', () => {
  const rows = technicianPricedItemRows(items, { applied_price_type: 'member', member_total_cents: 19060, store_total_cents: 23860, lines: [] });
  assert.deepEqual(rows.map((row) => [row.name, row.amount_cents]), [['舒享精油 SPA', null], ['草本泡脚', null]]);
  assert.deepEqual(technicianPriceTotalValue('member', { member_total_cents: 19060, store_total_cents: 23860 }), { amount_cents: 19060, pending_label: null });
});

test('价格行兼容旧字段名、异常数量与非法金额', () => {
  const rows = technicianPricedItemRows(
    [{ name: '荷小推', quantity: 0 }],
    { applied_price_type: 'member', member_total_cents: null, lines: [{ line_index: 0, name: '', quantity: 0, member_line_price_cents: 8900 }] },
  );
  assert.deepEqual(rows.map((row) => [row.name, row.quantity, row.amount_cents]), [['荷小推', 1, 8900]]);
  assert.equal(technicianPricingSummary({ applied_price_type: 'member', member_total_cents: null }), '会员价 —');

  const invalid = technicianPricedItemRows([{ name: '项目' }], { applied_price_type: 'store', lines: [{ line_index: 0, name: '项目', store_line_total_cents: -1 }] });
  assert.deepEqual(invalid.map((row) => row.amount_cents), [null]);
});

test('本单计价口径文案覆盖会员价、门店价、团购价与未知', () => {
  assert.equal(technicianPriceModeLabel(technicianPriceMode({ applied_price_type: 'member' })), '会员价');
  assert.equal(technicianPriceModeLabel(technicianPriceMode({ applied_price_type: 'store' })), '门店价');
  assert.equal(technicianPriceModeLabel(technicianPriceMode({ applied_price_type: 'group' })), '团购价');
  assert.equal(technicianPriceModeLabel(technicianPriceMode({ applied_price_type: null })), '价格类型待确认');
  assert.equal(technicianPriceModeLabel(technicianPriceMode(undefined)), '价格类型待确认');
});
